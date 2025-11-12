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

# Initialize AWS clients
s3_client = boto3.client('s3')
bucket_name = os.environ.get('BUCKET_NAME')
bedrock_region = os.environ.get('BEDROCK_REGION', os.environ.get('AWS_REGION', 'us-west-2'))
bedrock_client = boto3.client('bedrock-runtime', region_name=bedrock_region)

# Bedrock model configuration - separate models for categorization and summarization
CATEGORIZATION_MODEL_ID = os.environ.get('CATEGORIZATION_MODEL_ID', 'meta.llama3-8b-instruct-v1:0')
SUMMARIZATION_MODEL_ID = os.environ.get('SUMMARIZATION_MODEL_ID', 'anthropic.claude-3-sonnet-20240229-v1:0')

# Sentiment categories
SENTIMENT_CATEGORIES = {
    'POSITIVE': 'Positive',
    'NEGATIVE': 'Negative',
    'NEUTRAL': 'Neutral',
    'MIXED': 'Mixed'
}


def get_text_files_from_last_week(bucket: str, prefix: str = 'raw_data/') -> List[Dict[str, Any]]:
    """
    Retrieve text files from S3 bucket from the last 7 days.
    Reads from raw_data/ prefix where Reddit posts are stored.
    
    Args:
        bucket: S3 bucket name
        prefix: S3 prefix to search for text files (default: 'raw_data/')
        
    Returns:
        List of dictionaries with 'key', 'content', and 'last_modified' for each file
    """
    text_files = []
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    
    try:
        # List objects in the bucket with the given prefix
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
        
        for page in pages:
            if 'Contents' not in page:
                continue
                
            for obj in page['Contents']:
                # Check if file was modified in the last week
                if obj['LastModified'].replace(tzinfo=None) >= one_week_ago:
                    key = obj['Key']
                    # Only process JSON files (Reddit posts are stored as JSON)
                    if key.endswith('.json') and 'summary' not in key:
                        try:
                            # Get object content
                            response = s3_client.get_object(Bucket=bucket, Key=key)
                            post_data = json.loads(response['Body'].read().decode('utf-8'))
                            
                            # Extract content from Reddit post data
                            content = post_data.get('content', '')
                            if not content:
                                # Fallback to title and selftext
                                content = f"{post_data.get('title', '')}\n\n{post_data.get('selftext', '')}".strip()
                            
                            text_files.append({
                                'key': key,
                                'content': content,
                                'last_modified': obj['LastModified'].isoformat(),
                                'post_data': post_data  # Include full post data for reference
                            })
                            logger.debug(f"Retrieved file: {key}")
                        except Exception as e:
                            logger.error(f"Error reading file {key}: {str(e)}")
                            continue
                            
    except ClientError as e:
        logger.error(f"Error listing S3 objects: {str(e)}")
        raise
    
    logger.info(f"Found {len(text_files)} text files from the last week in {prefix}")
    return text_files


def categorize_sentiment_with_bedrock(text: str, model_id: str) -> Dict[str, Any]:
    """
    Categorize sentiment of text using Amazon Bedrock.
    
    Args:
        text: Text to analyze
        model_id: Bedrock model ID to use for categorization
        
    Returns:
        Dictionary with sentiment categorization results
    """
    # Determine the API format based on model ID
    if model_id.startswith('anthropic.claude'):
        return _categorize_sentiment_claude(text, model_id)
    elif model_id.startswith('meta.llama'):
        return _categorize_sentiment_llama(text, model_id)
    elif model_id.startswith('amazon.titan'):
        return _categorize_sentiment_titan(text, model_id)
    else:
        # Default to Llama format
        logger.warning(f"Unknown model format for {model_id}, using Llama format")
        return _categorize_sentiment_llama(text, model_id)


def summarize_texts_with_bedrock(texts: List[str], model_id: str) -> Dict[str, Any]:
    """
    Summarize a collection of texts using Amazon Bedrock.
    
    Args:
        texts: List of text strings to summarize
        model_id: Bedrock model ID to use for summarization
        
    Returns:
        Dictionary with summarization results
    """
    # Combine texts for summarization (with length limits)
    combined_text = "\n\n---\n\n".join(texts[:50])  # Limit to 50 texts to avoid token limits
    
    # Determine the API format based on model ID
    if model_id.startswith('anthropic.claude'):
        return _summarize_claude(combined_text, model_id, len(texts))
    elif model_id.startswith('meta.llama'):
        return _summarize_llama(combined_text, model_id, len(texts))
    elif model_id.startswith('amazon.titan'):
        return _summarize_titan(combined_text, model_id, len(texts))
    else:
        # Default to Claude format
        logger.warning(f"Unknown model format for {model_id}, using Claude format")
        return _summarize_claude(combined_text, model_id, len(texts))


def _categorize_sentiment_claude(text: str, model_id: str) -> Dict[str, Any]:
    """Categorize sentiment using Claude models (messages API)."""
    prompt = f"""Analyze the sentiment of the following text and categorize it as one of: Positive, Negative, Neutral, or Mixed.

Text: {text}

Respond with a JSON object in this exact format:
{{
    "sentiment": "Positive|Negative|Neutral|Mixed",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}"""

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    })
    
    try:
        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        
        response_body = json.loads(response['body'].read())
        
        if 'content' in response_body and len(response_body['content']) > 0:
            content_text = response_body['content'][0].get('text', '')
            return _parse_categorization_response(content_text)
        else:
            raise ValueError("Unexpected response format from Claude")
            
    except ClientError as e:
        logger.error(f"Error invoking Bedrock model {model_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error processing Bedrock response: {str(e)}")
        raise


def _categorize_sentiment_llama(text: str, model_id: str) -> Dict[str, Any]:
    """Categorize sentiment using Llama models."""
    prompt = f"""<s>[INST] Analyze the sentiment of the following text and categorize it as one of: Positive, Negative, Neutral, or Mixed.

Text: {text}

Respond with a JSON object in this exact format:
{{
    "sentiment": "Positive|Negative|Neutral|Mixed",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}
[/INST]"""

    body = json.dumps({
        "prompt": prompt,
        "max_gen_len": 512,
        "temperature": 0.1,
        "top_p": 0.9
    })
    
    try:
        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        
        response_body = json.loads(response['body'].read())
        generation = response_body.get('generation', '')
        return _parse_categorization_response(generation)
            
    except ClientError as e:
        logger.error(f"Error invoking Bedrock model {model_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error processing Bedrock response: {str(e)}")
        raise


def _categorize_sentiment_titan(text: str, model_id: str) -> Dict[str, Any]:
    """Categorize sentiment using Amazon Titan models."""
    prompt = f"""Analyze the sentiment of the following text and categorize it as one of: Positive, Negative, Neutral, or Mixed.

Text: {text}

Respond with a JSON object in this exact format:
{{
    "sentiment": "Positive|Negative|Neutral|Mixed",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}"""

    body = json.dumps({
        "inputText": prompt,
        "textGenerationConfig": {
            "maxTokenCount": 512,
            "temperature": 0.1,
            "topP": 0.9
        }
    })
    
    try:
        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        
        response_body = json.loads(response['body'].read())
        results = response_body.get('results', [])
        
        if results and len(results) > 0:
            output_text = results[0].get('outputText', '')
            return _parse_categorization_response(output_text)
        else:
            raise ValueError("Unexpected response format from Titan")
            
    except ClientError as e:
        logger.error(f"Error invoking Bedrock model {model_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error processing Bedrock response: {str(e)}")
        raise


def _summarize_claude(text: str, model_id: str, total_texts: int) -> Dict[str, Any]:
    """Summarize texts using Claude models (messages API)."""
    prompt = f"""Please provide a comprehensive summary of the following collection of texts from posts over the last week.

Total number of posts: {total_texts}

Texts:
{text}

Provide a summary that includes:
1. Main themes and topics discussed
2. Key insights or trends
3. Notable patterns or observations
4. Overall tone and sentiment

Respond with a JSON object in this format:
{{
    "summary": "comprehensive summary text",
    "main_themes": ["theme1", "theme2", ...],
    "key_insights": ["insight1", "insight2", ...],
    "overall_tone": "description of overall tone"
}}"""

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2048,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    })
    
    try:
        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        
        response_body = json.loads(response['body'].read())
        
        if 'content' in response_body and len(response_body['content']) > 0:
            content_text = response_body['content'][0].get('text', '')
            return _parse_summarization_response(content_text, total_texts)
        else:
            raise ValueError("Unexpected response format from Claude")
            
    except ClientError as e:
        logger.error(f"Error invoking Bedrock model {model_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error processing Bedrock response: {str(e)}")
        raise


def _summarize_llama(text: str, model_id: str, total_texts: int) -> Dict[str, Any]:
    """Summarize texts using Llama models."""
    prompt = f"""<s>[INST] Please provide a comprehensive summary of the following collection of texts from posts over the last week.

Total number of posts: {total_texts}

Texts:
{text}

Provide a summary that includes:
1. Main themes and topics discussed
2. Key insights or trends
3. Notable patterns or observations
4. Overall tone and sentiment

Respond with a JSON object in this format:
{{
    "summary": "comprehensive summary text",
    "main_themes": ["theme1", "theme2", ...],
    "key_insights": ["insight1", "insight2", ...],
    "overall_tone": "description of overall tone"
}}
[/INST]"""

    body = json.dumps({
        "prompt": prompt,
        "max_gen_len": 2048,
        "temperature": 0.3,
        "top_p": 0.9
    })
    
    try:
        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        
        response_body = json.loads(response['body'].read())
        generation = response_body.get('generation', '')
        return _parse_summarization_response(generation, total_texts)
            
    except ClientError as e:
        logger.error(f"Error invoking Bedrock model {model_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error processing Bedrock response: {str(e)}")
        raise


def _summarize_titan(text: str, model_id: str, total_texts: int) -> Dict[str, Any]:
    """Summarize texts using Amazon Titan models."""
    prompt = f"""Please provide a comprehensive summary of the following collection of texts from posts over the last week.

Total number of posts: {total_texts}

Texts:
{text}

Provide a summary that includes:
1. Main themes and topics discussed
2. Key insights or trends
3. Notable patterns or observations
4. Overall tone and sentiment

Respond with a JSON object in this format:
{{
    "summary": "comprehensive summary text",
    "main_themes": ["theme1", "theme2", ...],
    "key_insights": ["insight1", "insight2", ...],
    "overall_tone": "description of overall tone"
}}"""

    body = json.dumps({
        "inputText": prompt,
        "textGenerationConfig": {
            "maxTokenCount": 2048,
            "temperature": 0.3,
            "topP": 0.9
        }
    })
    
    try:
        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=body,
            contentType='application/json',
            accept='application/json'
        )
        
        response_body = json.loads(response['body'].read())
        results = response_body.get('results', [])
        
        if results and len(results) > 0:
            output_text = results[0].get('outputText', '')
            return _parse_summarization_response(output_text, total_texts)
        else:
            raise ValueError("Unexpected response format from Titan")
            
    except ClientError as e:
        logger.error(f"Error invoking Bedrock model {model_id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error processing Bedrock response: {str(e)}")
        raise


def _parse_categorization_response(text: str) -> Dict[str, Any]:
    """Parse sentiment categorization from text response."""
    try:
        # Try to extract JSON from the response
        json_start = text.find('{')
        json_end = text.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            sentiment_result = json.loads(text[json_start:json_end])
            # Normalize sentiment to uppercase
            if 'sentiment' in sentiment_result:
                sentiment_result['sentiment'] = sentiment_result['sentiment'].upper()
            # Ensure confidence is a float
            if 'confidence' in sentiment_result:
                sentiment_result['confidence'] = float(sentiment_result['confidence'])
            return sentiment_result
    except json.JSONDecodeError:
        pass
    
    # Fallback: parse from text
    text_lower = text.lower()
    sentiment = 'NEUTRAL'
    confidence = 0.5
    
    if any(word in text_lower for word in ['positive', 'good', 'great', 'excellent', 'happy']):
        sentiment = 'POSITIVE'
        confidence = 0.7
    elif any(word in text_lower for word in ['negative', 'bad', 'poor', 'terrible', 'sad']):
        sentiment = 'NEGATIVE'
        confidence = 0.7
    elif any(word in text_lower for word in ['mixed', 'both', 'conflicting']):
        sentiment = 'MIXED'
        confidence = 0.6
    
    return {
        "sentiment": sentiment,
        "confidence": confidence,
        "reasoning": "Parsed from text response (JSON parsing failed)"
    }


def _parse_summarization_response(text: str, total_texts: int) -> Dict[str, Any]:
    """Parse summarization from text response."""
    try:
        # Try to extract JSON from the response
        json_start = text.find('{')
        json_end = text.rfind('}') + 1
        if json_start >= 0 and json_end > json_start:
            summary_result = json.loads(text[json_start:json_end])
            # Ensure required fields exist
            if 'summary' not in summary_result:
                summary_result['summary'] = text
            if 'main_themes' not in summary_result:
                summary_result['main_themes'] = []
            if 'key_insights' not in summary_result:
                summary_result['key_insights'] = []
            if 'overall_tone' not in summary_result:
                summary_result['overall_tone'] = "Not specified"
            summary_result['total_texts_summarized'] = total_texts
            return summary_result
    except json.JSONDecodeError:
        pass
    
    # Fallback: return text as summary
    return {
        "summary": text,
        "main_themes": [],
        "key_insights": [],
        "overall_tone": "Not specified",
        "total_texts_summarized": total_texts
    }


def categorize_sentiments(analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Categorize and summarize sentiment analyses.
    
    Args:
        analyses: List of sentiment analysis results
        
    Returns:
        Dictionary with sentiment categorization summary
    """
    sentiment_counts = {
        'POSITIVE': 0,
        'NEGATIVE': 0,
        'NEUTRAL': 0,
        'MIXED': 0
    }
    
    total_confidence = 0.0
    sentiment_details = []
    
    for analysis in analyses:
        sentiment = analysis.get('sentiment', 'NEUTRAL').upper()
        if sentiment in sentiment_counts:
            sentiment_counts[sentiment] += 1
        else:
            sentiment_counts['NEUTRAL'] += 1
        
        confidence = analysis.get('confidence', 0.5)
        total_confidence += confidence
        
        sentiment_details.append({
            'sentiment': sentiment,
            'confidence': confidence,
            'reasoning': analysis.get('reasoning', '')
        })
    
    total = len(analyses)
    avg_confidence = total_confidence / total if total > 0 else 0.0
    
    # Determine overall sentiment
    max_count = max(sentiment_counts.values())
    overall_sentiment = [k for k, v in sentiment_counts.items() if v == max_count][0]
    
    return {
        'overall_sentiment': SENTIMENT_CATEGORIES.get(overall_sentiment, 'Neutral'),
        'sentiment_distribution': {
            'positive': sentiment_counts['POSITIVE'],
            'negative': sentiment_counts['NEGATIVE'],
            'neutral': sentiment_counts['NEUTRAL'],
            'mixed': sentiment_counts['MIXED']
        },
        'total_texts_analyzed': total,
        'average_confidence': round(avg_confidence, 2),
        'sentiment_percentages': {
            'positive': round(sentiment_counts['POSITIVE'] / total * 100, 2) if total > 0 else 0,
            'negative': round(sentiment_counts['NEGATIVE'] / total * 100, 2) if total > 0 else 0,
            'neutral': round(sentiment_counts['NEUTRAL'] / total * 100, 2) if total > 0 else 0,
            'mixed': round(sentiment_counts['MIXED'] / total * 100, 2) if total > 0 else 0
        },
        'details': sentiment_details
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler function for Reddit post analysis.
    
    Reads Reddit posts from S3 and performs sentiment categorization and summarization.
    Triggered by EventBridge scheduled event.
    
    Args:
        event: Lambda event data (EventBridge scheduled event)
        context: Lambda context object
        
    Returns:
        Response dictionary with status and analysis results
    """
    try:
        logger.info(f"Event received: {json.dumps(event)}")
        
        if not bucket_name:
            raise ValueError("BUCKET_NAME environment variable is not set")
        
        # Get text files from S3 from the last week (from raw_data/)
        logger.info("Retrieving text files from S3 (raw_data/)...")
        text_files = get_text_files_from_last_week(bucket_name, prefix='raw_data/')
        
        if not text_files:
            logger.warning("No text files found in S3 from the last week")
            return {
                "statusCode": 200,
                "body": json.dumps({
                    "status": "success",
                    "message": "No text files found in the last week",
                    "timestamp": datetime.utcnow().isoformat(),
                    "bucket_name": bucket_name,
                    "categorization": {
                        "total_texts_analyzed": 0,
                        "overall_sentiment": "N/A"
                    },
                    "summarization": {
                        "total_texts_summarized": 0
                    }
                })
            }
        
        # Step 1: Categorize sentiment for each text file using categorization model
        logger.info(f"Categorizing sentiment for {len(text_files)} text files using model: {CATEGORIZATION_MODEL_ID}")
        sentiment_analyses = []
        texts_for_summarization = []
        
        for file_info in text_files:
            try:
                # Truncate text if too long (Bedrock has token limits)
                text = file_info['content']
                max_length = 5000  # Adjust based on model limits
                if len(text) > max_length:
                    text = text[:max_length] + "..."
                    logger.warning(f"Text truncated for file {file_info['key']}")
                
                # Categorize sentiment
                analysis = categorize_sentiment_with_bedrock(text, CATEGORIZATION_MODEL_ID)
                analysis['file_key'] = file_info['key']
                analysis['file_last_modified'] = file_info['last_modified']
                sentiment_analyses.append(analysis)
                logger.info(f"Categorized sentiment for {file_info['key']}: {analysis.get('sentiment', 'UNKNOWN')}")
                
                # Collect texts for summarization (store first 1000 chars per text)
                texts_for_summarization.append(text[:1000])
                
            except Exception as e:
                logger.error(f"Error categorizing sentiment for {file_info['key']}: {str(e)}")
                # Continue with other files even if one fails
                continue
        
        # Step 2: Summarize all texts using summarization model
        logger.info(f"Summarizing {len(texts_for_summarization)} texts using model: {SUMMARIZATION_MODEL_ID}")
        summarization_result = {}
        
        if texts_for_summarization:
            try:
                summarization_result = summarize_texts_with_bedrock(texts_for_summarization, SUMMARIZATION_MODEL_ID)
                logger.info("Summarization completed successfully")
            except Exception as e:
                logger.error(f"Error during summarization: {str(e)}")
                summarization_result = {
                    "summary": f"Error during summarization: {str(e)}",
                    "main_themes": [],
                    "key_insights": [],
                    "overall_tone": "Error",
                    "total_texts_summarized": len(texts_for_summarization)
                }
        else:
            summarization_result = {
                "summary": "No texts available for summarization",
                "main_themes": [],
                "key_insights": [],
                "overall_tone": "N/A",
                "total_texts_summarized": 0
            }
        
        # Step 3: Aggregate sentiment categorization
        categorization = categorize_sentiments(sentiment_analyses)
        
        # Prepare result
        result = {
            "status": "success",
            "message": "Categorization and summarization completed",
            "timestamp": datetime.utcnow().isoformat(),
            "bucket_name": bucket_name,
            "models_used": {
                "categorization_model": CATEGORIZATION_MODEL_ID,
                "summarization_model": SUMMARIZATION_MODEL_ID
            },
            "categorization": categorization,
            "summarization": summarization_result
        }
        
        # Save results to S3
        try:
            result_key = f"reports/{datetime.utcnow().strftime('%Y-%m-%d')}/analysis-{datetime.utcnow().strftime('%H%M%S')}.json"
            s3_client.put_object(
                Bucket=bucket_name,
                Key=result_key,
                Body=json.dumps(result, indent=2),
                ContentType='application/json'
            )
            logger.info(f"Results saved to S3: s3://{bucket_name}/{result_key}")
            result["s3_result_key"] = result_key
        except Exception as e:
            logger.error(f"Error saving results to S3: {str(e)}")
            result["s3_error"] = str(e)
        
        logger.info(f"Analysis completed: {categorization['total_texts_analyzed']} posts analyzed")
        
        return {
            "statusCode": 200,
            "body": json.dumps(result, indent=2)
        }
        
    except Exception as e:
        logger.error(f"Error in analyzer: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
        }

