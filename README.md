# Reddit UBC Reporter

AWS Lambda-based serverless application for reporting Reddit UBC content with sentiment analysis using Amazon Bedrock, built with AWS SAM (Serverless Application Model).

## Features

- **Separated Architecture**: Four independent Lambda functions for better separation of concerns
  - **Reddit Fetcher Function**: Fetches Reddit posts and stores in S3
  - **Analyzer Function**: Performs sentiment analysis using Bedrock
  - **Summarizer Function**: Generates summaries using Bedrock
  - **Emailer Function**: Sends email notifications via Postmark
- **Reddit Integration**: Automatically fetches posts from Reddit (default: r/UBC) from the last week
  - Uses Reddit API (PRAW) to retrieve post data
  - Stores posts in S3 under `raw_data/` prefix
  - Independent EventBridge schedule for data fetching
- **Dual-Model Architecture**: Uses separate models for categorization and summarization
  - **Categorization**: Uses Llama models (default) to categorize sentiment of posts
  - **Summarization**: Uses Claude models (default) to generate comprehensive summaries
- **Flexible Model Selection**: Choose different Bedrock models for each task
- **Multi-Model Support**: Supports Claude (v2/v3), Llama 2/3, and Amazon Titan models
- **Automatic Processing**: Processes Reddit posts from the last 7 days
- **Sentiment Categories**: Categorizes text as Positive, Negative, Neutral, or Mixed
- **Comprehensive Summaries**: Generates summaries with main themes, key insights, and overall tone
- **Results Storage**: Saves analysis results back to S3
- **Independent EventBridge Schedules**: Separate schedules for fetching and analysis
- **Manual Invocation**: Can be invoked on-demand via AWS CLI

## Project Structure

```
ubc-reddit-reporter/
├── src/
│   ├── __init__.py
│   ├── reddit_fetcher.py  # Reddit fetcher Lambda function
│   ├── analyzer.py        # Analyzer Lambda function
│   ├── summarizer.py      # Summarizer Lambda function
│   └── emailer.py         # Emailer Lambda function
├── tests/                  # Unit tests
│   ├── __init__.py
│   └── test_app.py
├── events/                 # Event test files
│   ├── reddit-fetcher-event.json  # Reddit fetcher event
│   ├── analyzer-event.json        # Analyzer event
│   ├── summarizer-event.json      # Summarizer event
│   └── emailer-event.json         # Emailer event
├── scripts/                # Utility scripts
│   └── invoke-lambda.sh   # Script to invoke deployed functions
├── template.yaml           # SAM template defining AWS resources
├── samconfig.toml          # SAM CLI configuration
├── requirements.txt        # Python dependencies
├── .env.example           # Example environment variables
├── .gitignore             # Git ignore rules
├── Makefile               # Make commands for common tasks
└── README.md              # This file
```

## Prerequisites

- [AWS CLI](https://aws.amazon.com/cli/) installed and configured
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html) installed
- Python 3.11 or higher
- Docker (for local testing)

## Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/Vin-dictive/ubc-reddit-reporter
   cd ubc-reddit-reporter
   ```

2. **Create conda env**
   ```bash
   conda create -n ubc-reddit-reporter python=3.11 
   conda activate ubc-reddit-reporter
   ```

3. **Install dependencies**
   Make sure to uncomment in requirements.txt Testing dependencies
   ```bash
   pip install -r src/requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your actual credentials
   ```

5. **Build the SAM application**
   ```bash
   sam build
   ```

6. **Deploy to AWS**
   ```bash
   sam deploy --guided
   ```
   The `--guided` flag will prompt you for configuration values on first deployment.

## AWS Resources

The SAM template creates the following AWS resources:

### Lambda Functions

1. **Reddit Fetcher Function**: `RedditFetcherFunction`
   - Runtime: Python 3.11
   - Memory: 512 MB
   - Timeout: 300 seconds (5 minutes)
   - Handler: `reddit_fetcher.lambda_handler`
   - Trigger: EventBridge scheduled event (weekly by default)
   - Permissions: S3 read/write access
   - Function: Fetches Reddit posts and stores them in S3

2. **Analyzer Function**: `AnalyzerFunction`
   - Runtime: Python 3.11
   - Memory: 512 MB
   - Timeout: 900 seconds (15 minutes)
   - Handler: `analyzer.lambda_handler`
   - Trigger: EventBridge scheduled event (weekly by default)
   - Permissions: S3 read/write access + Bedrock model invocation
   - Function: Performs sentiment categorization

3. **Summarizer Function**: `SummarizerFunction`
   - Runtime: Python 3.11
   - Memory: 512 MB
   - Timeout: 900 seconds (15 minutes)
   - Handler: `summarizer.lambda_handler`
   - Trigger: Manual invocation only
   - Permissions: S3 read/write access + Bedrock model invocation
   - Function: Generates comprehensive summaries using Bedrock

4. **Emailer Function**: `EmailerFunction`
   - Runtime: Python 3.11
   - Memory: 256 MB
   - Timeout: 300 seconds (5 minutes)
   - Handler: `emailer.lambda_handler`
   - Trigger: Manual invocation only
   - Permissions: S3 read access
   - Function: Sends email notifications via Postmark API

### Other Resources

- **S3 Bucket**: `DataBucket`
  - Stores application data (raw Reddit posts and analysis results)
  - Versioning enabled
  - Lifecycle policy (deletes old versions after 30 days)
  - Private access only

- **IAM Roles**:
  - `RedditFetcherExecutionRole`: S3 access only
  - `AnalyzerExecutionRole`: S3 access + Bedrock permissions

- **EventBridge Rules**:
  - `RedditFetchSchedule`: Triggers Reddit fetcher function
  - `AnalysisSchedule`: Triggers analyzer function

## Local Development

### Test locally with SAM CLI

1. **Test Reddit fetcher function**
   ```bash
   sam local invoke RedditFetcherFunction -e events/reddit-fetcher-event.json
   
   # Or use Make command
   make invoke-reddit-fetcher
   ```

2. **Test analyzer function**
   ```bash
   sam local invoke AnalyzerFunction -e events/analyzer-event.json
   
   # Or use Make command
   make invoke-analyzer
   ```

3. **Test summarizer function**
   ```bash
   sam local invoke SummarizerFunction -e events/summarizer-event.json
   
   # Or use Make command
   make invoke-summarizer
   ```

4. **Test emailer function**
   ```bash
   sam local invoke EmailerFunction -e events/emailer-event.json
   
   # Or use Make command
   make invoke-emailer
   ```

**Note**: Reddit Fetcher and Analyzer functions are triggered by EventBridge schedules in production. Summarizer and Emailer functions are manual invocation only. For local testing, use the event files provided in the `events/` directory.

## Environment Variables

Create a `.env` file (based on `.env.example`) with your configuration:

- `AWS_REGION`: AWS region for deployment
- `AWS_ACCOUNT_ID`: Your AWS account ID
- `LOG_LEVEL`: Logging level (INFO, DEBUG, etc.)
- `CATEGORIZATION_MODEL_ID`: Bedrock model ID for sentiment categorization (default: `meta.llama3-8b-instruct-v1:0`)
- `SUMMARIZATION_MODEL_ID`: Bedrock model ID for text summarization (default: `anthropic.claude-3-sonnet-20240229-v1:0`)
- `BEDROCK_REGION`: AWS region for Bedrock (defaults to AWS_REGION)
- `REDDIT_CLIENT_ID`: Reddit API Client ID (required for Reddit integration)
- `REDDIT_CLIENT_SECRET`: Reddit API Client Secret (required for Reddit integration)
- `REDDIT_USER_AGENT`: Reddit API User Agent string (default: `ubc-reddit-reporter/1.0`)
- `REDDIT_SUBREDDIT`: Subreddit name to fetch posts from (default: `UBC`)
- `POSTMARK_SERVER_TOKEN`: Postmark API server token for sending emails
- `FROM_EMAIL`: Email address to send from (default: `sender@example.com`)
- `TO_EMAIL`: Email address to send to (default: `recipient@example.com`)
- `TEMPLATE_ALIAS`: Postmark template alias to use (default: `comment-notification`)

### Model Selection Guide

#### For Categorization (Sentiment Analysis)
**Recommended: Llama Models** (fast, efficient, cost-effective)
- `meta.llama3-8b-instruct-v1:0` (default - recommended for categorization)
- `meta.llama3-70b-instruct-v1:0` (more capable)
- `meta.llama2-13b-chat-v1`
- `meta.llama2-70b-chat-v1`

**Alternative: Claude Models**
- `anthropic.claude-3-haiku-20240307-v1:0` (fast, cheaper)
- `anthropic.claude-3-sonnet-20240229-v1:0`
- `anthropic.claude-3-opus-20240229-v1:0` (most capable)

#### For Summarization
**Recommended: Claude Models** (excellent for summarization)
- `anthropic.claude-3-sonnet-20240229-v1:0` (default - recommended for summarization)
- `anthropic.claude-3-opus-20240229-v1:0` (best quality, most capable)
- `anthropic.claude-3-haiku-20240307-v1:0` (faster, cheaper)
- `anthropic.claude-v2:1` or `anthropic.claude-v2`

**Alternative: Llama Models**
- `meta.llama3-70b-instruct-v1:0`
- `meta.llama3-8b-instruct-v1:0`
- `meta.llama2-70b-chat-v1`

**Titan Models** (available for both tasks)
- `amazon.titan-text-express-v1`
- `amazon.titan-text-agile-v1`
- `amazon.titan-text-lite-v1`

**Note**: 
- Never commit the `.env` file to git. It's already in `.gitignore`.
- Ensure the selected Bedrock models are available in your AWS region.
- You may need to enable the models in the Bedrock console before use.
- Different models have different costs - Llama is generally cheaper for categorization tasks.

## Deployment

### First Deployment

```bash
sam deploy --guided
```

This will:
1. Prompt for stack name
2. Prompt for AWS region
3. Prompt for categorization model ID (default: `anthropic.claude-3-sonnet-20240229-v1:0`)
4. Prompt for summarization model ID (default: `us.anthropic.claude-sonnet-4-5-20250929-v1:0`)
5. Prompt for Reddit fetch schedule (default: `rate(7 days)`)
6. Prompt to enable Reddit fetch schedule (default: `true`)
7. Prompt for analysis schedule (default: `rate(7 days)`)
8. Prompt to enable analysis schedule (default: `true`)
9. Prompt for Reddit Client ID (optional, leave empty if not using Reddit API)
10. Prompt for Reddit Client Secret (optional, leave empty if not using Reddit API)
11. Prompt for Reddit User Agent (default: `scraper`)
12. Prompt for Reddit Subreddit (default: `UBC`)
13. Prompt for Postmark Server Token (default: provided token)
14. Prompt for From Email (default: `sender@example.com`)
15. Prompt for To Email (default: `recipient@example.com`)
16. Prompt for Template Alias (default: `comment-notification`)
17. Prompt for confirm changeset
18. Create S3 bucket for deployment artifacts
19. Deploy the stack

### Deploy with Custom Models, Schedules, and Reddit Credentials

```bash
sam deploy \
  --parameter-overrides \
    CategorizationModelId=meta.llama3-70b-instruct-v1:0 \
    SummarizationModelId=anthropic.claude-3-opus-20240229-v1:0 \
    RedditFetchSchedule="rate(1 day)" \
    AnalysisSchedule="cron(0 0 ? * SUN *)" \
    EnableRedditFetchSchedule="true" \
    EnableAnalysisSchedule="true" \
    RedditClientId=your-reddit-client-id \
    RedditClientSecret=your-reddit-client-secret \
    RedditUserAgent="scraper" \
    RedditSubreddit=UBC
```

**Note**: Reddit credentials are optional. If not provided, the Reddit Fetcher function will fail but the Analyzer can still work with existing S3 data.

### Schedule Options

Both functions run automatically on separate schedules. You can configure each independently:

**Reddit Fetch Schedule:**
- `rate(7 days)` - Every 7 days from deployment time (default)
- `rate(1 day)` - Daily fetching (recommended for active subreddits)
- `cron(0 0 ? * SUN *)` - Every Sunday at midnight UTC
- `cron(0 9 ? * MON *)` - Every Monday at 9:00 AM UTC

**Analysis Schedule:**
- `rate(7 days)` - Every 7 days from deployment time (default)
- `rate(1 day)` - Daily analysis
- `cron(0 0 ? * SUN *)` - Every Sunday at midnight UTC
- `cron(0 9 ? * MON *)` - Every Monday at 9:00 AM UTC

**Recommended Configuration:**
- Fetch Reddit data daily: `RedditFetchSchedule="rate(1 day)"`
- Analyze weekly: `AnalysisSchedule="rate(7 days)"`

See [AWS EventBridge Schedule Expressions](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-create-rule-schedule.html) for more options.

### Disable Scheduled Execution

To disable scheduled execution for either function:

```bash
# Disable Reddit fetcher schedule
sam deploy \
  --parameter-overrides \
    EnableRedditFetchSchedule="false"

# Disable analyzer schedule
sam deploy \
  --parameter-overrides \
    EnableAnalysisSchedule="false"

# Disable both
sam deploy \
  --parameter-overrides \
    EnableRedditFetchSchedule="false" \
    EnableAnalysisSchedule="false"
```

### Subsequent Deployments

```bash
sam build
sam deploy
```

### Update Configuration

Edit `samconfig.toml` to modify deployment settings, or use command-line parameters.

## Execution Methods

### 1. Scheduled Execution (Automatic)

Both functions run automatically on separate EventBridge schedules:

#### Reddit Fetcher Function
- **Default Schedule**: Every 7 days (`rate(7 days)`)
- **Enabled by default**: Yes
- **Function**: Fetches Reddit posts from the last week
- **Output**: Stores posts in S3 under `raw_data/` prefix
- **Logs**: Available in CloudWatch Logs

#### Analyzer Function
- **Default Schedule**: Every 7 days (`rate(7 days)`)
- **Enabled by default**: Yes
- **Function**: Analyzes posts from S3 using Bedrock models
- **Output**: Saves analysis results to S3 in `reports/` prefix
- **Logs**: Available in CloudWatch Logs

**Note**: You can configure different schedules for each function. For example, fetch Reddit data daily but analyze weekly.

### 2. Manual Invocation Methods

You can invoke the function manually in several ways:

#### Option A: AWS CLI Lambda Invoke (Direct invocation)

Invoke the Lambda functions directly using AWS CLI:

**Invoke Reddit Fetcher:**
```bash
# Get the function name from stack outputs
REDDIT_FETCHER=$(aws cloudformation describe-stacks \
  --stack-name ubc-reddit-reporter \
  --query 'Stacks[0].Outputs[?OutputKey==`RedditFetcherFunction`].OutputValue' \
  --output text)

# Invoke Reddit fetcher
aws lambda invoke \
  --function-name $REDDIT_FETCHER \
  --payload '{"source":"aws.events"}' \
  response.json

cat response.json | jq
```

**Invoke Analyzer:**
```bash
# Get the function name from stack outputs
ANALYZER=$(aws cloudformation describe-stacks \
  --stack-name ubc-reddit-reporter \
  --query 'Stacks[0].Outputs[?OutputKey==`AnalyzerFunction`].OutputValue' \
  --output text)

# Invoke analyzer
aws lambda invoke \
  --function-name $ANALYZER \
  --payload '{"source":"aws.events"}' \
  response.json

cat response.json | jq
```

**Invoke Summarizer:**
```bash
# Get the function name from stack outputs
SUMMARIZER=$(aws cloudformation describe-stacks \
  --stack-name ubc-reddit-reporter \
  --query 'Stacks[0].Outputs[?OutputKey==`SummarizerFunction`].OutputValue' \
  --output text)

# Invoke summarizer
aws lambda invoke \
  --function-name $SUMMARIZER \
  --payload '{"source":"aws.events"}' \
  response.json

cat response.json | jq
```

**Invoke Emailer:**
```bash
# Get the function name from stack outputs
EMAILER=$(aws cloudformation describe-stacks \
  --stack-name ubc-reddit-reporter \
  --query 'Stacks[0].Outputs[?OutputKey==`EmailerFunction`].OutputValue' \
  --output text)

# Invoke emailer
aws lambda invoke \
  --function-name $EMAILER \
  --payload '{"source":"aws.events"}' \
  response.json

cat response.json | jq
```

**Benefits:**
- Direct Lambda invocation
- Faster execution
- Useful for testing and debugging
- Can invoke functions independently

#### Option B: AWS Console

1. Go to AWS Lambda Console
2. Find your function:
   - `ubc-reddit-reporter-RedditFetcherFunction-<id>` (for Reddit fetching)
   - `ubc-reddit-reporter-AnalyzerFunction-<id>` (for analysis)
3. Click "Test" tab
4. Create a new test event:
   - Event name: `scheduled-event-test`
   - Event JSON: Use the content from `events/reddit-fetcher-event.json` or `events/analyzer-event.json`
5. Click "Test" to invoke the function
6. View results in the execution results panel

**Benefits:**
- Visual interface
- Easy to test different event formats
- View logs directly in the console
- Good for debugging

#### Option C: Programmatic Invocation (Python example)

```python
import boto3
import json

# Initialize Lambda client
lambda_client = boto3.client('lambda', region_name='us-west-2')

# Invoke Reddit Fetcher
reddit_fetcher_name = 'ubc-reddit-reporter-RedditFetcherFunction-<id>'
response = lambda_client.invoke(
    FunctionName=reddit_fetcher_name,
    InvocationType='RequestResponse',
    Payload=json.dumps({"source": "aws.events"})
)
result = json.loads(response['Payload'].read())
print("Reddit Fetcher:", json.dumps(result, indent=2))

# Invoke Analyzer
analyzer_name = 'ubc-reddit-reporter-AnalyzerFunction-<id>'
response = lambda_client.invoke(
    FunctionName=analyzer_name,
    InvocationType='RequestResponse',
    Payload=json.dumps({"source": "aws.events"})
)
result = json.loads(response['Payload'].read())
print("Analyzer:", json.dumps(result, indent=2))
```

#### Option D: Using the Provided Script (Easiest)

Use the provided script to invoke the deployed functions:

```bash
# Invoke Reddit Fetcher
./scripts/invoke-lambda.sh RedditFetcherFunction reddit-fetcher

# Invoke Analyzer
./scripts/invoke-lambda.sh AnalyzerFunction analyzer

# Invoke Summarizer
./scripts/invoke-lambda.sh SummarizerFunction summarizer

# Invoke Emailer
./scripts/invoke-lambda.sh EmailerFunction emailer

# Or use Make commands
make invoke-reddit-fetcher-remote  # Reddit fetcher
make invoke-analyzer-remote         # Analyzer
make invoke-summarizer-remote       # Summarizer
make invoke-emailer-remote          # Emailer
```

**Prerequisites:**
- AWS CLI configured with appropriate credentials
- Stack name set (default: `ubc-reddit-reporter`)
- Functions deployed

**Benefits:**
- Simple one-command invocation
- Automatically gets function name from stack
- Handles both functions
- Pretty-prints JSON response if `jq` is installed

### Which Method Should You Use?

- **AWS CLI**: Best for command-line usage, scripting, or quick testing
- **AWS Console**: Best for debugging, testing different event formats, or one-off invocations
- **Programmatic (boto3)**: Best for integrating with other Python applications or AWS services
- **Script (`invoke-lambda.sh`)**: Best for quick manual invocations after deployment

### How It Works

The system consists of two independent Lambda functions that work together:

#### Reddit Fetcher Function (runs on its own schedule)

1. **Reddit Data Fetching**:
   - Fetches posts from the configured subreddit (default: r/UBC) from the last 7 days
   - Uses Reddit API (PRAW) to retrieve post data including title, content, author, scores, etc.
   - Stores each post as a JSON file in S3 under `raw_data/YYYY-MM-DD/post_*.json`
   - Also creates a summary file with post metadata
   - Runs independently on EventBridge schedule

#### Analyzer Function (runs on its own schedule)

1. **Data Retrieval**: Retrieves Reddit posts from S3 (prefix: `raw_data/`) from the last 7 days
   - Reads posts that were stored by the Reddit Fetcher function
   - Extracts content (title + selftext) from each post for analysis

2. **Categorization**: Each post is analyzed using the **categorization model** (default: Llama) to determine sentiment
   - Sentiment is categorized as: **Positive**, **Negative**, **Neutral**, or **Mixed**
   - Each categorization includes confidence score and reasoning

3. **Summarization**: All posts are combined and summarized using the **summarization model** (default: Claude)
   - Generates comprehensive summary with main themes, key insights, and overall tone

4. **Aggregation**: Sentiment categorizations are aggregated with distribution and percentages

5. **Storage**: Results are saved to S3 in `reports/` prefix

**Workflow:**
- Reddit Fetcher runs first (fetches and stores data)
- Analyzer runs afterward (reads stored data and analyzes)
- Both functions can run on different schedules (e.g., fetch daily, analyze weekly)

### S3 Bucket Structure

```
s3://your-bucket/
├── raw_data/                       # Reddit posts (fetched from Reddit API)
│   ├── 2024-11-11/
│   │   ├── post_abc123.json       # Individual Reddit post
│   │   ├── post_def456.json
│   │   └── summary_143022.json    # Summary of all posts for the day
│   └── 2024-11-12/
│       ├── post_ghi789.json
│       └── summary_090000.json
└── reports/                        # Output analysis reports
    └── 2024-11-11/
        └── analysis-143022.json    # Contains both categorization and summarization
```

### Response Format

```json
{
  "status": "success",
  "message": "Categorization and summarization completed",
  "timestamp": "2024-11-11T14:30:22.123456",
  "bucket_name": "your-bucket",
  "models_used": {
    "categorization_model": "meta.llama3-8b-instruct-v1:0",
    "summarization_model": "anthropic.claude-3-sonnet-20240229-v1:0"
  },
  "categorization": {
    "overall_sentiment": "Positive",
    "sentiment_distribution": {
      "positive": 5,
      "negative": 2,
      "neutral": 3,
      "mixed": 1
    },
    "total_texts_analyzed": 11,
    "average_confidence": 0.85,
    "sentiment_percentages": {
      "positive": 45.45,
      "negative": 18.18,
      "neutral": 27.27,
      "mixed": 9.09
    },
    "details": [
      {
        "sentiment": "POSITIVE",
        "confidence": 0.9,
        "reasoning": "The text expresses positive emotions and satisfaction",
        "file_key": "texts/2024-11-11/text1.txt",
        "file_last_modified": "2024-11-11T10:00:00"
      }
    ]
  },
  "summarization": {
    "summary": "The posts from the last week show a generally positive sentiment...",
    "main_themes": [
      "Theme 1: Academic discussions",
      "Theme 2: Campus events",
      "Theme 3: Student life"
    ],
    "key_insights": [
      "Insight 1: Increased engagement with academic topics",
      "Insight 2: Positive feedback on recent events"
    ],
    "overall_tone": "Positive and engaging",
    "total_texts_summarized": 11
  },
  "s3_result_key": "reports/2024-11-11/analysis-143022.json"
}
```

## Testing

### Unit Tests

```bash
# Install test dependencies
pip install pytest pytest-mock

# Run tests
pytest tests/
```

### Integration Tests

Test the deployed functions using any of the manual invocation methods:

**Option 1: Using the provided script**
```bash
# Invoke Reddit fetcher
./scripts/invoke-lambda.sh RedditFetcherFunction reddit-fetcher

# Invoke analyzer
./scripts/invoke-lambda.sh AnalyzerFunction analyzer

# Or use Make commands
make invoke-reddit-fetcher-remote
make invoke-analyzer-remote
```

**Option 2: AWS CLI direct invocation**
```bash
# Get function names from stack outputs
REDDIT_FETCHER=$(aws cloudformation describe-stacks \
  --stack-name ubc-reddit-reporter \
  --query 'Stacks[0].Outputs[?OutputKey==`RedditFetcherFunction`].OutputValue' \
  --output text)

ANALYZER=$(aws cloudformation describe-stacks \
  --stack-name ubc-reddit-reporter \
  --query 'Stacks[0].Outputs[?OutputKey==`AnalyzerFunction`].OutputValue' \
  --output text)

# Invoke Reddit fetcher
aws lambda invoke \
  --function-name $REDDIT_FETCHER \
  --payload file://events/reddit-fetcher-event.json \
  response.json && cat response.json | jq

# Invoke analyzer
aws lambda invoke \
  --function-name $ANALYZER \
  --payload file://events/analyzer-event.json \
  response.json && cat response.json | jq
```

## Monitoring

### CloudWatch Logs

View execution logs:
- **Reddit Fetcher**: Check CloudWatch Logs for `RedditFetcherFunction`
- **Analyzer**: Check CloudWatch Logs for `AnalyzerFunction`
- Logs include detailed execution information and results

### CloudWatch Metrics

Monitor function performance:
- Invocation count
- Duration
- Error count
- Throttles

### CloudWatch Alarms

Set up alarms for:
- Error rate (recommended: alert if errors > 0)
- Duration (recommended: alert if duration > 240 seconds)
- Failed invocations

### EventBridge Rules

Monitor the scheduled events:
- **Reddit Fetch Rule**: View EventBridge rule for `RedditFetchSchedule`
- **Analysis Rule**: View EventBridge rule for `AnalysisSchedule`
- Check rule state (enabled/disabled) for each
- View rule execution history
- Monitor rule invocations and failures
- Set up CloudWatch Alarms for failed invocations

## Cleanup

To delete all AWS resources:

```bash
sam delete
```

**Note**: The S3 bucket has `DeletionPolicy: Retain`, so it won't be deleted automatically. You'll need to manually empty and delete it if desired.

## Security Best Practices

1. **Never commit credentials**: The `.env` file is in `.gitignore`
2. **Use IAM roles**: The Lambda function uses an IAM role, not hardcoded credentials
3. **S3 bucket security**: The bucket blocks all public access
4. **Environment variables**: Sensitive data should use AWS Systems Manager Parameter Store or AWS Secrets Manager
5. **Least privilege**: IAM roles follow the principle of least privilege
6. **Bedrock access**: Ensure Bedrock models are enabled in your AWS account and region
7. **Cost monitoring**: Monitor Bedrock API usage and costs in CloudWatch

## Reddit API Setup

To enable Reddit data fetching, you need to set up a Reddit API application:

1. **Create a Reddit API Application**:
   - Go to https://www.reddit.com/prefs/apps
   - Click "create another app" or "create app"
   - Fill in the form:
     - **Name**: `ubc-reddit-reporter` (or any name)
     - **App type**: Select "script"
     - **Description**: Optional
     - **About URL**: Optional
     - **Redirect URI**: `http://localhost:8080` (required but not used for script type)
   - Click "create app"

2. **Get Your Credentials**:
   - **Client ID**: The string under your app name (looks like: `abc123def456ghi`)
   - **Client Secret**: The "secret" field (looks like: `xyz789_secret_key_abc123`)
   - **User Agent**: Use format: `ubc-reddit-reporter/1.0` (platform:username:version)

3. **Configure in Environment Variables**:
   - Set `REDDIT_CLIENT_ID` to your Client ID
   - Set `REDDIT_CLIENT_SECRET` to your Client Secret
   - Set `REDDIT_USER_AGENT` (default: `ubc-reddit-reporter/1.0`)
   - Set `REDDIT_SUBREDDIT` to the subreddit name (default: `UBC`)

4. **Reddit API Rate Limits**:
   - Reddit API has rate limits (60 requests per minute for script apps)
   - The function fetches up to 1000 posts per execution
   - If you hit rate limits, the function will log errors but continue with existing S3 data

**Note**: If Reddit API credentials are not configured, the function will skip Reddit fetching and use existing data in S3.

## Bedrock Setup

Before deploying, ensure you have:

1. **Enabled Bedrock models** in your AWS account:
   - Go to AWS Bedrock Console
   - Navigate to "Model access"
   - Request access to the models you want to use
   - Wait for approval (usually instant for most models)

2. **Verified model availability** in your region:
   - Different models are available in different regions
   - Claude models: us-west-2, us-west-2, ap-southeast-1, etc.
   - Check AWS documentation for region availability

3. **Configured model IDs** in your deployment:
   - Set `CategorizationModelId` and `SummarizationModelId` parameters during SAM deployment
   - Or modify `CATEGORIZATION_MODEL_ID` and `SUMMARIZATION_MODEL_ID` in `.env` for local testing
   - Defaults: Llama for categorization, Claude for summarization

4. **Configured Reddit credentials** (optional):
   - Set `RedditClientId` and `RedditClientSecret` parameters during SAM deployment
   - Or modify `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` in `.env` for local testing
   - If not configured, the function will use existing data in S3

## Contributing

1. Create a feature branch
2. Make your changes
3. Add tests
4. Submit a pull request


## Support

For issues and questions, please open an issue on GitHub.

