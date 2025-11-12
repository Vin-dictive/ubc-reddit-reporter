import os
import io
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

import boto3
import pandas as pd
import numpy as np
from tqdm import tqdm
from jinja2 import Template
from pydantic import BaseModel, Field


from reddit_fetcher import fetch_reddit_posts
from llm_classifier import classify_text

# ================== Logging ==================
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

tqdm.pandas()

# ================== AWS S3 ==================
s3_client = boto3.client("s3")
bedrock_client = boto3.client('bedrock-runtime', region_name=os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "us-east-1")))
bucket_name = os.environ.get("BUCKET_NAME")
bedrock_region = os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "us-east-1"))

# ================== Folders ==================
OUTPUT_FOLDER = Path("reddit_data")
CLASSIFIED_FOLDER = Path("reddit_data_classified")
SUMMARY_OUTPUT_FOLDER = Path("summaries")
PROMPTS_DIR = Path("prompts")

OUTPUT_FOLDER.mkdir(exist_ok=True, parents=True)
CLASSIFIED_FOLDER.mkdir(exist_ok=True, parents=True)
SUMMARY_OUTPUT_FOLDER.mkdir(exist_ok=True, parents=True)

# ================== LLM & Output Models ==================
class SummaryResponse(BaseModel):
    summary: str = Field(description="A concise summary of the posts for the given category.")

# ================== LLM Initialization =================
def invoke_bedrock_model(prompt: str, model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0") -> str:
    """Invoke Bedrock model directly with boto3."""
    if model_id.startswith("anthropic.claude"):
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": prompt}]
        })
    else:
        body = json.dumps({"prompt": prompt, "max_gen_len": 1000})
    
    response = bedrock_client.invoke_model(
        modelId=model_id,
        body=body,
        contentType="application/json"
    )
    
    result = json.loads(response['body'].read())
    
    if model_id.startswith("anthropic.claude"):
        return result['content'][0]['text']
    elif model_id.startswith("meta.llama"):
        return result['generation']
    else:
        return str(result)

# ================== Helper Functions =================
def format_comments(comments) -> str:
    if comments is None or (isinstance(comments, float) and np.isnan(comments)):
        return "No comments"
    if isinstance(comments, np.ndarray):
        comments = comments.tolist()
    if isinstance(comments, list):
        if len(comments) == 0:
            return "No comments"
        formatted = []
        for i, comment in enumerate(comments[:10], 1):
            if isinstance(comment, dict):
                comment_text = comment.get("text", comment.get("body", str(comment)))
            else:
                comment_text = str(comment)
            comment_text = comment_text.strip()
            if len(comment_text) > 200:
                comment_text = comment_text[:200] + "..."
            formatted.append(f"  - {comment_text}")
        if len(comments) > 10:
            formatted.append(f"  ... and {len(comments) - 10} more comments")
        return "\n".join(formatted)
    return str(comments)[:500]

def format_posts_for_prompt(df: pd.DataFrame, category: str, title_col="Title",
                           content_col="Post_Text", comments_col="Comments") -> str:
    category_posts = df[df['category'] == category].copy()
    if len(category_posts) == 0:
        return ""
    posts_list = []
    for idx, row in category_posts.iterrows():
        title = row.get(title_col, "No title")
        content = row.get(content_col, "No content") if pd.notna(row.get(content_col)) else "No content"
        comments = format_comments(row.get(comments_col))
        post_text = f"""Post {len(posts_list) + 1}:
Title: {title}
Content: {content}
Comments:
{comments}"""
        posts_list.append(post_text)
    return "\n\n" + "\n\n---\n\n".join(posts_list)

def render_prompt(prompt_file: str, posts_data: str) -> str:
    with open(prompt_file, "r", encoding="utf-8") as f:
        template = Template(f.read())
    return template.render(posts=posts_data)

def summarize_posts(posts_data: str, model_id: str, prompt_file: str) -> SummaryResponse:
    rendered_prompt = render_prompt(prompt_file, posts_data)
    full_prompt = f"{rendered_prompt}\n\nRespond with JSON format: {{\"summary\": \"text\"}}"
    output_text = invoke_bedrock_model(full_prompt, model_id)
    try:
        result = json.loads(output_text.strip())
        return SummaryResponse(summary=result.get("summary", output_text.strip()))
    except Exception:
        return SummaryResponse(summary=output_text.strip())

# ================== S3 Utilities =================
def list_parquet_files_from_s3(bucket: str, prefix: str = "raw_data/"):
    paginator = s3_client.get_paginator("list_objects_v2")
    files = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet"):
                files.append(obj["Key"])
    return files

def read_parquet_from_s3(bucket: str, key: str) -> pd.DataFrame:
    response = s3_client.get_object(Bucket=bucket, Key=key)
    buffer = io.BytesIO(response["Body"].read())
    return pd.read_parquet(buffer, engine="pyarrow")

def write_text_to_s3(text: str, bucket: str, key: str):
    s3_client.put_object(Bucket=bucket, Key=key, Body=text.encode("utf-8"))
    logger.info(f"Saved text summary to s3://{bucket}/{key}")

# ================== Reddit Fetch & Classify =================
def get_parquet_filename(subreddit: str, start_date: datetime, end_date: datetime):
    start_str = start_date.strftime("%Y_%m_%d")
    end_str = end_date.strftime("%Y_%m_%d")
    return f"{subreddit}_{end_str}_{start_str}.parquet"

def classify_posts(df: pd.DataFrame, llm_model, title_col="Title", content_col="Post_Text"):
    if 'category' not in df.columns or df['category'].isnull().all():
        tqdm.pandas()
        combined_texts = (df[title_col].fillna('') + ". " + df[content_col].fillna('')).str.strip()
        df['category'] = combined_texts.progress_apply(
            lambda t: classify_text(content=t, llm_model=llm_model, prompt_file=str(PROMPTS_DIR / "classify_post.jinja")).category
        )
    return df

# ================== Main Processing =================
def process_all_data(subreddit: str = "ubc", days_back: int = 7, llm_model=None):
    today = datetime.now(timezone.utc)
    old = today - timedelta(days=days_back)

    parquet_file = OUTPUT_FOLDER / get_parquet_filename(subreddit, old, today)
    classified_file = CLASSIFIED_FOLDER / parquet_file.name

    # Fetch Reddit data
    if parquet_file.exists():
        df = pd.read_parquet(parquet_file)
    else:
        df = fetch_reddit_posts([subreddit], days_back=days_back, manual_date=today, output_folder=str(OUTPUT_FOLDER))
        df.to_parquet(parquet_file, index=False)

    # Classify posts
    if llm_model is None:
        llm_model = get_ollama_model()
    df = classify_posts(df, llm_model)
    df.to_parquet(classified_file, index=False)

    # Summarize per category
    category_prompt_map = {
        "Computer Science": "Computer_Science.jinja",
        "Social": "Social_Events.jinja",
        "General Academics": "General_Academics.jinja",
        "General Sciences": "General_Sciences.jinja",
        "Mental Health and Wellbeing": "Mental_Health_and_Wellbeing.jinja",
        "Math and Statistics": "Math_and_Statistics.jinja",
        "Campus Spaces": "Campus_Spaces.jinja",
        "Career": "Career.jinja",
        "Business and Econ": "Business_and_Econ.jinja",
        "Housing and Residence": "Housing_and_Residence.jinja",
        "Admin and Logistics": "Admin_and_Logistics.jinja",
        "Arts and Humanities": "Arts_and_Humanities.jinja",
        "Rants": "Rants_and_Complaints.jinja",
        "Advice and Tips": "Advice_and_Tips.jinja",
    }

    from summary_pipeline import process_all_prompts  # your existing summarization code
    summaries = process_all_prompts(
        df=df,
        category_prompt_map=category_prompt_map,
        prompts_dir=str(PROMPTS_DIR),
        llm_model=llm_model,
        output_dir=str(SUMMARY_OUTPUT_FOLDER),
        verbose=False
    )
    return summaries

# ================== Lambda Handler =================
def lambda_handler(event: Dict[str, Any], context: Any):
    model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")
    summaries = process_all_data(subreddit="ubc", days_back=7, model_id=model_id)
    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "success",
            "summaries": summaries,
            "timestamp": datetime.utcnow().isoformat()
        }, indent=2)
    }