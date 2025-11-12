import json
import os
import logging
import boto3
from datetime import datetime, timedelta
from typing import Dict, Any, List
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Reddit API
try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False
    logger.warning("PRAW not available. Reddit integration will be disabled.")

# Initialize AWS clients
s3_client = boto3.client('s3')
bucket_name = os.environ.get('BUCKET_NAME')

# Reddit API configuration
REDDIT_CLIENT_ID = os.environ.get('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.environ.get('REDDIT_CLIENT_SECRET')
REDDIT_USER_AGENT = os.environ.get('REDDIT_USER_AGENT', 'scraper')
REDDIT_SUBREDDIT = os.environ.get('REDDIT_SUBREDDIT', 'UBC')


def fetch_reddit_posts_from_last_week(subreddit_name: str = REDDIT_SUBREDDIT) -> List[Dict[str, Any]]:
    """
    Fetch Reddit posts from the last week using PRAW.
    
    Args:
        subreddit_name: Name of the subreddit to fetch posts from
        
    Returns:
        List of dictionaries containing post data
    """
    if not PRAW_AVAILABLE:
        raise ImportError("PRAW library is not installed. Install it with: pip install praw")
    
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        raise ValueError("Reddit API credentials not configured. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables.")
    
    try:
        # Initialize Reddit API client
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT
        )
        
        # Get subreddit
        subreddit = reddit.subreddit(subreddit_name)
        logger.info(f"Fetching posts from r/{subreddit_name}")
        
        # Calculate timestamp for one week ago
        one_week_ago = datetime.utcnow() - timedelta(days=7)
        one_week_ago_timestamp = one_week_ago.timestamp()
        
        posts = []
        
        # Fetch posts from the last week
        # Use 'new' sorting to get recent posts
        for submission in subreddit.new(limit=1000):  # Limit to avoid rate limits
            # Check if post is from the last week
            if submission.created_utc >= one_week_ago_timestamp:
                # Extract post data
                post_data = {
                    'id': submission.id,
                    'title': submission.title,
                    'selftext': submission.selftext,
                    'author': str(submission.author) if submission.author else '[deleted]',
                    'created_utc': submission.created_utc,
                    'created_datetime': datetime.utcfromtimestamp(submission.created_utc).isoformat(),
                    'score': submission.score,
                    'num_comments': submission.num_comments,
                    'url': submission.url,
                    'permalink': submission.permalink,
                    'subreddit': str(submission.subreddit),
                    'is_self': submission.is_self,
                    'link_flair_text': submission.link_flair_text,
                    # Combine title and selftext for analysis
                    'content': f"{submission.title}\n\n{submission.selftext}".strip()
                }
                posts.append(post_data)
            else:
                # Posts are sorted by new, so if we hit an old post, we can break
                break
        
        logger.info(f"Fetched {len(posts)} posts from r/{subreddit_name} from the last week")
        return posts
        
    except Exception as e:
        logger.error(f"Error fetching Reddit posts: {str(e)}", exc_info=True)
        raise


def store_reddit_posts_in_s3(posts: List[Dict[str, Any]], bucket: str, prefix: str = 'raw_data/') -> List[str]:
    """
    Store Reddit posts in S3 under the specified prefix.
    Uses post ID to ensure uniqueness - will overwrite if post already exists.
    
    Args:
        posts: List of post dictionaries
        bucket: S3 bucket name
        prefix: S3 prefix to store posts under
        
    Returns:
        List of S3 keys where posts were stored
    """
    stored_keys = []
    current_date = datetime.utcnow().strftime('%Y-%m-%d')
    stored_count = 0
    skipped_count = 0
    
    try:
        # Store each post as a separate JSON file
        for post in posts:
            # Create S3 key with date and post ID (post ID ensures uniqueness)
            post_date = datetime.utcfromtimestamp(post['created_utc']).strftime('%Y-%m-%d')
            key = f"{prefix}{post_date}/post_{post['id']}.json"
            
            try:
                # Store post data as JSON
                s3_client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=json.dumps(post, indent=2),
                    ContentType='application/json'
                )
                stored_keys.append(key)
                stored_count += 1
                logger.debug(f"Stored post {post['id']} to s3://{bucket}/{key}")
            except ClientError as e:
                logger.error(f"Error storing post {post['id']} to S3: {str(e)}")
                skipped_count += 1
                continue
        
        # Also store a summary file with all posts metadata
        summary_key = f"{prefix}{current_date}/summary_{datetime.utcnow().strftime('%H%M%S')}.json"
        summary = {
            'date': current_date,
            'timestamp': datetime.utcnow().isoformat(),
            'total_posts': len(posts),
            'stored_count': stored_count,
            'skipped_count': skipped_count,
            'posts': [{'id': p['id'], 'title': p['title'], 'created_datetime': p['created_datetime'], 'score': p.get('score', 0)} for p in posts]
        }
        s3_client.put_object(
            Bucket=bucket,
            Key=summary_key,
            Body=json.dumps(summary, indent=2),
            ContentType='application/json'
        )
        stored_keys.append(summary_key)
        
        logger.info(f"Stored {stored_count} posts to S3 under prefix: {prefix} (skipped: {skipped_count})")
        return stored_keys
        
    except ClientError as e:
        logger.error(f"Error storing posts to S3: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error processing posts for S3: {str(e)}")
        raise


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function for Reddit data fetching.
    
    Fetches Reddit posts from the last week and stores them in S3.
    Triggered by EventBridge scheduled event.
    
    Args:
        event: Lambda event data (EventBridge scheduled event)
        context: Lambda context object
        
    Returns:
        Response dictionary with status and results
    """
    try:
        logger.info(f"Event received: {json.dumps(event)}")
        
        if not bucket_name:
            raise ValueError("BUCKET_NAME environment variable is not set")
        
        # Fetch Reddit posts from the last week
        if not PRAW_AVAILABLE:
            raise ImportError("PRAW library is not installed. Install it with: pip install praw")
        
        if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
            raise ValueError("Reddit API credentials not configured. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables.")
        
        logger.info("Fetching Reddit posts from the last week...")
        posts = fetch_reddit_posts_from_last_week(REDDIT_SUBREDDIT)
        
        if not posts:
            logger.warning("No Reddit posts found from the last week")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "status": "success",
                    "message": "No Reddit posts found from the last week",
                    "timestamp": datetime.utcnow().isoformat(),
                    "bucket_name": bucket_name,
                    "subreddit": REDDIT_SUBREDDIT,
                    "posts_fetched": 0,
                    "posts_stored": 0
                })
            }
        
        # Store posts in S3
        logger.info(f"Storing {len(posts)} posts in S3...")
        stored_keys = store_reddit_posts_in_s3(posts, bucket_name, prefix='raw_data/')
        
        result = {
            "status": "success",
            "message": "Reddit posts fetched and stored successfully",
            "timestamp": datetime.utcnow().isoformat(),
            "bucket_name": bucket_name,
            "subreddit": REDDIT_SUBREDDIT,
            "posts_fetched": len(posts),
            "posts_stored": len([k for k in stored_keys if 'summary' not in k]),
            "s3_keys": stored_keys[:10],  # Include first 10 keys for reference
            "total_s3_files": len(stored_keys)
        }
        
        logger.info(f"Reddit fetcher completed: {len(posts)} posts fetched, {len(stored_keys)} files stored")
        
        return {
            "statusCode": 200,
            "body": json.dumps(result, indent=2)
        }
        
    except Exception as e:
        logger.error(f"Error in Reddit fetcher: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
        }

