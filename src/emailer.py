import json
import os
import logging
from datetime import datetime
from typing import Dict, Any

import boto3
import requests

# ================== Logging Setup ==================
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# ================== AWS Clients ===================
s3_client = boto3.client('s3')
bucket_name = os.environ.get("BUCKET_NAME")

# ================== Postmark Config ================
POSTMARK_SERVER_TOKEN = os.environ.get("POSTMARK_SERVER_TOKEN")
POSTMARK_API_URL = "https://api.postmarkapp.com/email/withTemplate"
FROM_EMAIL = os.environ.get("FROM_EMAIL", "sender@example.com")
TO_EMAIL = os.environ.get("TO_EMAIL", "recipient@example.com")
TEMPLATE_ALIAS = os.environ.get("TEMPLATE_ALIAS", "comment-notification")

def read_text_from_s3(bucket: str, key: str) -> str:
    """Read text file from S3."""
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        return response['Body'].read().decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to read {key} from S3: {str(e)}")
        return ""

def send_postmark_email(summary_text: str) -> Dict[str, Any]:
    """Send email using Postmark API."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": POSTMARK_SERVER_TOKEN
    }
    
    payload = {
        "From": FROM_EMAIL,
        "To": TO_EMAIL,
        "TemplateAlias": TEMPLATE_ALIAS,
        "TemplateModel": {
            "product_url": "https://reddit.com/r/UBC",
            "message": summary_text,
            "body": summary_text,
            "commenter_name": "UBC Reddit Reporter",
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "action_url": "https://reddit.com/r/UBC",
            "notifications_url": "https://reddit.com/r/UBC"
        }
    }
    
    try:
        response = requests.post(POSTMARK_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        return {"status": "success", "response": response.json()}
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to send email: {str(e)}")
        return {"status": "error", "message": str(e)}

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler to send email with summary from S3.
    """
    try:
        logger.info(f"Event received: {json.dumps(event)}")
        
        if not bucket_name:
            raise ValueError("BUCKET_NAME environment variable not set")
        
        # Read summary from S3
        summary_key = "summaries/all_categories_summary.txt"
        summary_text = read_text_from_s3(bucket_name, summary_key)
        
        if not summary_text:
            return {
                "statusCode": 404,
                "body": json.dumps({
                    "status": "error",
                    "message": "Summary file not found or empty",
                    "timestamp": datetime.utcnow().isoformat()
                })
            }
        
        # Send email
        email_result = send_postmark_email(summary_text)
        
        if email_result["status"] == "success":
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "status": "success",
                    "message": "Email sent successfully",
                    "email_response": email_result["response"],
                    "timestamp": datetime.utcnow().isoformat()
                })
            }
        else:
            return {
                "statusCode": 500,
                "body": json.dumps({
                    "status": "error",
                    "message": email_result["message"],
                    "timestamp": datetime.utcnow().isoformat()
                })
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