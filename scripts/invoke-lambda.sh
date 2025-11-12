#!/bin/bash
# Script to manually invoke Lambda functions
# Usage: ./scripts/invoke-lambda.sh <FunctionName> [event-type]
# Example: ./scripts/invoke-lambda.sh RedditFetcherFunction reddit-fetcher
# Example: ./scripts/invoke-lambda.sh AnalyzerFunction analyzer

set -e

FUNCTION_NAME_PARAM=${1:-}
EVENT_TYPE=${2:-}

if [ -z "$FUNCTION_NAME_PARAM" ]; then
  echo "Usage: ./scripts/invoke-lambda.sh <FunctionName> [event-type]"
  echo ""
  echo "Available functions:"
  echo "  - RedditFetcherFunction (event: reddit-fetcher)"
  echo "  - AnalyzerFunction (event: analyzer)"
  echo ""
  echo "Examples:"
  echo "  ./scripts/invoke-lambda.sh RedditFetcherFunction reddit-fetcher"
  echo "  ./scripts/invoke-lambda.sh AnalyzerFunction analyzer"
  exit 1
fi

STACK_NAME=${STACK_NAME:-ubc-reddit-reporter}
REGION=${AWS_REGION:-us-west-2}

echo "Invoking Lambda function: $FUNCTION_NAME_PARAM"
echo "Stack: $STACK_NAME"
echo "Region: $REGION"
echo ""

# Map function parameter to output key
if [ "$FUNCTION_NAME_PARAM" = "RedditFetcherFunction" ]; then
  OUTPUT_KEY="RedditFetcherFunction"
  DEFAULT_EVENT="reddit-fetcher"
elif [ "$FUNCTION_NAME_PARAM" = "AnalyzerFunction" ]; then
  OUTPUT_KEY="AnalyzerFunction"
  DEFAULT_EVENT="analyzer"
else
  # Try to use the parameter as-is (might be full function name)
  OUTPUT_KEY="$FUNCTION_NAME_PARAM"
  DEFAULT_EVENT="analyzer"
fi

# Get function name from CloudFormation stack outputs
FUNCTION_NAME=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey==\`${OUTPUT_KEY}\`].OutputValue" \
  --output text 2>/dev/null)

if [ -z "$FUNCTION_NAME" ] || [ "$FUNCTION_NAME" = "None" ]; then
  echo "Error: Could not find function name for $OUTPUT_KEY."
  echo "Make sure the stack is deployed and STACK_NAME is correct."
  echo "Current STACK_NAME: $STACK_NAME"
  echo ""
  echo "Trying to get function name directly..."
  # Try to get function name directly (in case it's the full ARN or name)
  FUNCTION_NAME="$FUNCTION_NAME_PARAM"
fi

echo "Function name: $FUNCTION_NAME"
echo ""

# Determine event file
EVENT_TYPE=${EVENT_TYPE:-$DEFAULT_EVENT}

if [ "$EVENT_TYPE" = "reddit-fetcher" ]; then
  EVENT_FILE="events/reddit-fetcher-event.json"
elif [ "$EVENT_TYPE" = "analyzer" ]; then
  EVENT_FILE="events/analyzer-event.json"
else
  EVENT_FILE="events/${EVENT_TYPE}-event.json"
fi

# Check if event file exists
if [ ! -f "$EVENT_FILE" ]; then
  echo "Warning: Event file not found: $EVENT_FILE"
  echo "Using default empty event: {}"
  EVENT_PAYLOAD='{"source":"aws.events"}'
else
  echo "Using event file: $EVENT_FILE"
  EVENT_PAYLOAD="file://$EVENT_FILE"
fi

# Invoke the function
echo "Invoking function..."
RESPONSE_FILE=$(mktemp)

if [ "$EVENT_PAYLOAD" = '{"source":"aws.events"}' ]; then
  aws lambda invoke \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION" \
    --payload "$EVENT_PAYLOAD" \
    "$RESPONSE_FILE" \
    > /dev/null
else
  aws lambda invoke \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION" \
    --payload "$EVENT_PAYLOAD" \
    "$RESPONSE_FILE" \
    > /dev/null
fi

# Check if jq is available for pretty printing
if command -v jq &> /dev/null; then
  echo ""
  echo "Response:"
  echo "=========="
  cat "$RESPONSE_FILE" | jq
else
  echo ""
  echo "Response:"
  echo "=========="
  cat "$RESPONSE_FILE"
  echo ""
  echo "Tip: Install 'jq' for pretty JSON output: brew install jq (macOS) or apt-get install jq (Linux)"
fi

# Cleanup
rm "$RESPONSE_FILE"

echo ""
echo "Done! Check CloudWatch Logs for detailed execution logs."

