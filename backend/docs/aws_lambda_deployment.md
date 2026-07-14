# AWS Lambda Backend Deployment

This backend is prepared for a container-image Lambda behind API Gateway HTTP
API. The Lambda serves FastAPI through Mangum and uses DynamoDB tables created
by `serverless.yml`.

Playwright scraping is intentionally disabled in the deployed Lambda. Run
scraping locally and point local backend env vars at the AWS DynamoDB tables so
the deployed API can read the saved creator/activity data.

## AWS Setup

Configure credentials locally. Do not commit AWS keys.

```powershell
aws configure --profile Team-GV-Zain
$env:AWS_PROFILE="Team-GV-Zain"
$env:AWS_DEFAULT_REGION="us-east-2"
```

Set provider secrets in your shell before deploy, or replace these with SSM /
Secrets Manager variables later:

```powershell
$env:GOOGLE_API_KEY="..."
$env:GROQ_API_KEY="..."
$env:ANTHROPIC_API_KEY="..."
$env:TAVILY_API_KEY="..."
```

## Deploy Backend

Docker must be running because Serverless builds and pushes an ECR image.

```powershell
cd backend
npm install -g serverless
serverless deploy --stage dev --region us-east-2
```

After deploy, copy the HTTP API endpoint from the Serverless output and test:

```powershell
curl https://YOUR_HTTP_API_ID.execute-api.us-east-2.amazonaws.com/health
```

The stack creates these DynamoDB tables:

```text
linkedin_post_generator_dev_users
linkedin_post_generator_dev_threads
linkedin_post_generator_dev_creators
linkedin_post_generator_dev_activities
```

## Local Scraping Into AWS DynamoDB

Use this when you want local Playwright scraping to populate the deployed
DynamoDB tables.

```powershell
cd backend
$env:AWS_PROFILE="Team-GV-Zain"
$env:AWS_DEFAULT_REGION="us-east-2"
$env:APP_ENV="dev"
$env:DYNAMODB_TABLE_PREFIX="linkedin_post_generator_dev"
$env:SCRAPING_ENABLED="true"
Remove-Item Env:\DYNAMODB_ENDPOINT_URL -ErrorAction SilentlyContinue
uv run uvicorn app.api.main:app --reload --host 127.0.0.1 --port 7860
```

Then run scraping from the local frontend or call the local scrape endpoints.
The saved data lands in AWS DynamoDB and is readable by the deployed Lambda API.

## Vercel Frontend Env

For Vercel, set:

```text
API_BASE_URL=https://YOUR_HTTP_API_ID.execute-api.us-east-2.amazonaws.com
NEXT_PUBLIC_DEFAULT_USER_ID=test-user-1
NEXT_PUBLIC_ENABLE_SCRAPING=false
```

`NEXT_PUBLIC_ENABLE_SCRAPING=false` keeps the deployed frontend from trying to
run Playwright-backed scrape actions through Lambda.
