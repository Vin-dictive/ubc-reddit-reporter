import json
import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.app import lambda_handler


@pytest.fixture
def lambda_context():
    """Mock Lambda context"""
    context = Mock()
    context.function_name = "test-function"
    context.function_version = "1"
    context.invoked_function_arn = "arn:aws:lambda:us-west-2:123456789012:function:test-function"
    context.memory_limit_in_mb = 128
    return context


@pytest.fixture
def api_event():
    """Mock API Gateway event"""
    return {
        "httpMethod": "GET",
        "path": "/report",
        "queryStringParameters": None,
        "headers": {},
        "body": None,
        "isBase64Encoded": False
    }


@patch.dict(os.environ, {"BUCKET_NAME": "test-bucket", "LOG_LEVEL": "INFO"})
@patch("src.app.s3_client")
def test_lambda_handler_success(mock_s3_client, api_event, lambda_context):
    """Test successful Lambda function execution"""
    # Mock S3 put_object
    mock_s3_client.put_object.return_value = {}
    
    # Invoke handler
    response = lambda_handler(api_event, lambda_context)
    
    # Assertions
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["status"] == "success"
    assert "timestamp" in body
    assert body["bucket_name"] == "test-bucket"
    
    # Verify S3 put_object was called
    mock_s3_client.put_object.assert_called_once()


@patch.dict(os.environ, {"BUCKET_NAME": "test-bucket", "LOG_LEVEL": "INFO"})
@patch("src.app.s3_client")
def test_lambda_handler_s3_error(mock_s3_client, api_event, lambda_context):
    """Test Lambda function with S3 error"""
    # Mock S3 put_object to raise an error
    mock_s3_client.put_object.side_effect = Exception("S3 error")
    
    # Invoke handler
    response = lambda_handler(api_event, lambda_context)
    
    # Assertions
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["status"] == "success"
    assert "s3_error" in body


@patch.dict(os.environ, {"BUCKET_NAME": "", "LOG_LEVEL": "INFO"})
def test_lambda_handler_no_bucket(api_event, lambda_context):
    """Test Lambda function without bucket name"""
    # Invoke handler
    response = lambda_handler(api_event, lambda_context)
    
    # Assertions
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["status"] == "success"


@patch.dict(os.environ, {"BUCKET_NAME": "test-bucket", "LOG_LEVEL": "INFO"})
@patch("src.app.s3_client")
def test_lambda_handler_with_query_params(mock_s3_client, api_event, lambda_context):
    """Test Lambda function with query parameters"""
    # Mock S3 put_object
    mock_s3_client.put_object.return_value = {}
    
    # Add query parameters
    api_event["queryStringParameters"] = {"param1": "value1", "param2": "value2"}
    
    # Invoke handler
    response = lambda_handler(api_event, lambda_context)
    
    # Assertions
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["query_params"] == {"param1": "value1", "param2": "value2"}


@patch.dict(os.environ, {"BUCKET_NAME": "test-bucket", "LOG_LEVEL": "INFO"})
def test_lambda_handler_exception(api_event, lambda_context):
    """Test Lambda function with unexpected exception"""
    # Mock an error by patching datetime
    with patch("src.app.datetime") as mock_datetime:
        mock_datetime.utcnow.side_effect = Exception("Unexpected error")
        
        # Invoke handler
        response = lambda_handler(api_event, lambda_context)
        
        # Assertions
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["status"] == "error"

