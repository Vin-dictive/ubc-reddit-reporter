import json
import os
import io
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

import boto3
import pandas as pd
from jinja2 import Template
from pydantic import BaseModel, Field


# ================== Logging Setup ==================
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# ================== AWS Clients ===================
s3_client = boto3.client('s3')
bedrock_client = boto3.client(
    'bedrock-runtime',
    region_name=os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "us-east-1"))
)

bucket_name = os.environ.get("BUCKET_NAME")
bedrock_region = os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "us-east-1"))

# ================== Bedrock Config =================
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID",
    "anthropic.claude-3-sonnet-20240229-v1:0"
)

# ================== Structured Output Models =======
class CategoryResponse(BaseModel):
    category: str = Field(description="Predicted category name from the predefined list.")


# ================== Helper Functions ==============
def render_prompt(prompt_file: str, content: str) -> str:
    """
    Render Jinja2 prompt template located under src/prompts/.
    Handles both local and deployed Lambda directory structures.
    """
    base_dir = os.path.dirname(__file__)
    possible_paths = [
        os.path.join(base_dir, "prompts", os.path.basename(prompt_file)),        # e.g. src/prompts/prompt_template.jinja
        os.path.join(base_dir, "src", "prompts", os.path.basename(prompt_file)), # for zip/Lambda
        os.path.join(os.getcwd(), "src", "prompts", os.path.basename(prompt_file)),
        prompt_file  # fallback if absolute path passed
    ]

    for path in possible_paths:
        if os.path.exists(path):
            logger.info(f"Using prompt file: {path}")
            with open(path, "r", encoding="utf-8") as f:
                template = Template(f.read())
            return template.render(content=content)

    raise FileNotFoundError(f"Prompt file not found. Tried paths: {possible_paths}")


def invoke_bedrock_model(prompt: str, model_id: str = BEDROCK_MODEL_ID) -> str:
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


def classify_text(content: str, model_id: str, prompt_file: str) -> CategoryResponse:
    """
    Classify text using a Bedrock model with Jinja2 prompts.
    Automatically resolves prompt from src/prompts/.
    """
    rendered_prompt = render_prompt(prompt_file, content)
    full_prompt = f"{rendered_prompt}\n\nRespond with JSON format: {{\"category\": \"category_name\"}}"

    output_text = invoke_bedrock_model(full_prompt, model_id)

    try:
        result = json.loads(output_text.strip())
        return CategoryResponse(category=result.get("category", "Unknown"))
    except Exception:
        cleaned = output_text.strip().split("\n")[0]
        return CategoryResponse(category=cleaned)


# ================== S3 & Parquet Utilities =========
def list_parquet_files_from_s3(bucket: str, prefix: str = "raw_data/") -> List[str]:
    """List parquet files in S3 bucket under prefix."""
    files = []
    paginator = s3_client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".parquet"):
                files.append(obj["Key"])
    return files


def read_parquet_from_s3(bucket: str, key: str) -> pd.DataFrame:
    """Read parquet file from S3 into DataFrame."""
    response = s3_client.get_object(Bucket=bucket, Key=key)
    buffer = io.BytesIO(response['Body'].read())
    df = pd.read_parquet(buffer, engine="pyarrow")
    return df


def write_parquet_to_s3(df: pd.DataFrame, bucket: str, key: str):
    """Write DataFrame as parquet to S3."""
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)
    s3_client.put_object(Bucket=bucket, Key=key, Body=buffer)
    logger.info(f"Uploaded {len(df)} rows to s3://{bucket}/{key}")


# ================== Lambda Handler =================
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler to classify text from Parquet files in S3 using Bedrock LLM.
    Combines available text columns (e.g., Title, Post_Text) dynamically.
    """
    try:
        logger.info(f"Event received: {json.dumps(event)}")
        if not bucket_name:
            raise ValueError("BUCKET_NAME environment variable not set")

        parquet_files = list_parquet_files_from_s3(bucket_name, prefix="reddit_parquet/")
        if not parquet_files:
            logger.warning("No parquet files found in S3")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "status": "success",
                    "message": "No files found"
                })
            }

        # Prompt file always located under src/prompts/
        prompt_file = os.environ.get("PROMPT_FILE", "classify_post.jinja")
        results = []

        for key in parquet_files:
            try:
                df = read_parquet_from_s3(bucket_name, key)
                if df.empty:
                    logger.warning(f"File {key} is empty, skipping")
                    continue

                # Determine available text columns
                text_columns = [col for col in ["Title", "Post_Text", "Body", "content"] if col in df.columns]
                if not text_columns:
                    logger.warning(f"No text columns found in {key}, skipping")
                    continue

                combined_texts = df[text_columns].fillna('').agg('. '.join, axis=1).str.strip()

                classifications = []
                for content in combined_texts:
                    if not content:
                        continue
                    category_response = classify_text(content, BEDROCK_MODEL_ID, prompt_file)
                    classifications.append({
                        "combined_text": content,
                        "category": category_response.category
                    })

                if classifications:
                    result_df = pd.DataFrame(classifications)
                    now = datetime.utcnow()
                    result_key = f"classifications/{key.split('/')[-1].replace('.parquet','')}_{now.strftime('%Y%m%d%H%M%S')}.parquet"
                    write_parquet_to_s3(result_df, bucket_name, result_key)
                    results.append(result_key)

            except Exception as e:
                logger.error(f"Error processing file {key}: {str(e)}", exc_info=True)
                continue

        return {
            "statusCode": 200,
            "body": json.dumps({
                "status": "success",
                "processed_files": len(results),
                "s3_keys": results,
                "timestamp": datetime.utcnow().isoformat()
            }, indent=2)
        }

    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
        }
