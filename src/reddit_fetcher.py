import json
import os
import io
import logging
import boto3
import praw
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from botocore.exceptions import ClientError

# ============ Logging Setup ============
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# ============ AWS Clients ============
s3_client = boto3.client('s3')
bucket_name = os.environ.get("BUCKET_NAME")

# ============ Reddit API Config ============
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "lambda_reddit_scraper")
REDDIT_SUBREDDITS = os.environ.get("REDDIT_SUBREDDITS", "UBC").split(",")


# ============ Core Function ============

def fetch_reddit_posts(subreddit_name: str, days_back: int = 7) -> pd.DataFrame:
    """
    Fetch recent Reddit posts (and comments) from a subreddit.
    Returns a DataFrame.
    """
    if not all([REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT]):
        raise ValueError("Missing Reddit credentials in environment variables.")
    
    reddit = praw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        user_agent=REDDIT_USER_AGENT
    )

    subreddit = reddit.subreddit(subreddit_name)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_back)
    
    posts_dict = {
        "Title": [],
        "Post_Text": [],
        "Post_URL": [],
        "Comments": [],
        "Created_UTC": [],
        "Subreddit": [],
    }
    
    logger.info(f"Fetching posts from r/{subreddit_name} for last {days_back} days")
    count = 0
    for post in subreddit.new(limit=1000):
        post_time = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
        if post_time < cutoff:
            break
        
        comments = []
        try:
            post.comments.replace_more(limit=None)
            comments = [c.body for c in post.comments.list()]
        except Exception:
            pass
        
        posts_dict["Title"].append(post.title)
        posts_dict["Post_Text"].append(post.selftext)
        posts_dict["Post_URL"].append(post.url)
        posts_dict["Comments"].append(comments)
        posts_dict["Created_UTC"].append(post_time.isoformat())
        posts_dict["Subreddit"].append(subreddit_name)
        count += 1

    logger.info(f"Fetched {count} posts from r/{subreddit_name}")
    return pd.DataFrame(posts_dict)


def store_parquet_in_s3(df: pd.DataFrame, subreddit_name: str, days_back: int) -> str:
    """
    Convert DataFrame to Parquet and upload to S3.
    """
    if df.empty:
        logger.warning(f"No posts found for r/{subreddit_name}, skipping S3 upload.")
        return None

    now = datetime.now(timezone.utc)
    old_date = (now - timedelta(days=days_back)).strftime('%Y_%m_%d')
    today_date = now.strftime('%Y_%m_%d')
    
    key = f"reddit_parquet/{subreddit_name}_{today_date}_{old_date}.parquet"
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False, engine="pyarrow")
    buffer.seek(0)

    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=buffer,
            ContentType='application/octet-stream'
        )
        logger.info(f"Uploaded {len(df)} posts from r/{subreddit_name} to s3://{bucket_name}/{key}")
        return key
    except ClientError as e:
        logger.error(f"Error uploading {subreddit_name} parquet to S3: {e}")
        raise


# ============ Lambda Handler ============

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler to fetch Reddit posts from multiple subreddits
    and store them as Parquet files in S3.
    """
    logger.info(f"Event received: {json.dumps(event)}")

    if not bucket_name:
        raise ValueError("BUCKET_NAME environment variable is not set")

    try:
        days_back = int(event.get("days_back", 7))
        stored_files = []

        for subreddit_name in REDDIT_SUBREDDITS:
            df = fetch_reddit_posts(subreddit_name.strip(), days_back)
            key = store_parquet_in_s3(df, subreddit_name.strip(), days_back)
            if key:
                stored_files.append(key)

        result = {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "bucket": bucket_name,
            "subreddits": REDDIT_SUBREDDITS,
            "files_stored": stored_files,
            "total_files": len(stored_files)
        }

        logger.info(f"Successfully stored {len(stored_files)} files to S3.")
        return {"statusCode": 200, "body": json.dumps(result, indent=2)}

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
