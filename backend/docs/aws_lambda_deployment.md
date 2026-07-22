# AWS Lambda Backend Deployment

The FastAPI backend runs through Mangum in a container-image Lambda. The API,
brainstorm worker, and scrape worker reuse one `linux/amd64` image. Application
records, async jobs, and extension tasks use one DynamoDB table:

```text
linkedin_post_generator_<stage>_app
```

The Chrome extension is the production scraping engine. The legacy Playwright
implementation remains available with `SCRAPE_ENGINE=playwright` on a machine
that can run Chrome; the existing headed Playwright flow is not suitable for
Lambda.

## Deploy

Docker Desktop must be running. Configure AWS once, then set deployment secrets
in the current PowerShell session:

```powershell
aws configure --profile Team-GV-Zain
$env:AWS_PROFILE="Team-GV-Zain"
$env:AWS_DEFAULT_REGION="us-east-2"
$env:GOOGLE_API_KEY="..."
$env:GROQ_API_KEY="..."
$env:ANTHROPIC_API_KEY="..."
$env:TAVILY_API_KEY="..."
$env:SCRAPE_ENGINE="extension"
$env:DOCKER_DEFAULT_PLATFORM="linux/amd64"
$env:BUILDX_NO_DEFAULT_ATTESTATIONS="1"

cd backend
npm install -g serverless
serverless deploy --stage dev --region us-east-2
```

Serverless builds and pushes the ECR image. A separate ECR login, `docker push`,
or one image build per Lambda is not normally required. If Lambda reports an
unsupported image manifest, keep the two Docker variables above and run the
same command once with `--force`. The image must be single-platform amd64, not
an ARM or multi-platform image/index.

Test the URL printed by Serverless:

```powershell
curl https://YOUR_HTTP_API_ID.execute-api.us-east-2.amazonaws.com/health
```

## One-time migration

The first single-table deployment creates the `_app` table but does not copy
legacy data. Migrate the four retained legacy tables once:

```powershell
cd backend
$env:AWS_PROFILE="Team-GV-Zain"
uv run python scripts/migrate_dynamodb_to_single_table.py --prefix linkedin_post_generator_dev --region us-east-2
```

The migration is idempotent. Verify the application before deleting legacy
tables; this stack retains them and does not destroy the source records.

## Extension production setup

1. Reload or install the updated extension.
2. In Extension options, use the deployed API URL as Backend URL.
3. Set Application user ID to the same ID used by the frontend.
4. Keep Chrome signed in to the intended LinkedIn account.
5. Set `NEXT_PUBLIC_ENABLE_SCRAPING=true` in the deployed frontend.

Extension tasks and heartbeats are stored under `PK=EXTENSION#{user_id}`, so
separate application users do not claim each other's work. This routing is not
authentication; authentication is intentionally deferred.

## Timing settings

```text
SCRAPE_INTER_CREATOR_DELAY_MIN_SECONDS=0
SCRAPE_INTER_CREATOR_DELAY_MAX_SECONDS=240
SCRAPE_LONG_BREAK_EVERY_CREATORS=10
SCRAPE_LONG_BREAK_MIN_SECONDS=300
SCRAPE_LONG_BREAK_MAX_SECONDS=600
EXTENSION_SCRAPE_TASK_TIMEOUT_SECONDS=300
EXTENSION_SCRAPE_TASK_LEASE_SECONDS=120
```

The normal random delay runs between creators. Before creator 11, 21, 31, and
so on, the configured longer random break also runs. Set the `EVERY` value to
`0` to disable long breaks.

AWS Lambda has a hard 15-minute execution limit. Extension payloads and status
are persisted in DynamoDB, but the current scrape worker still waits for each
creator sequentially. Keep each production batch small enough that task waits
and configured delays stay below 15 minutes. Large batches with periodic
5-10 minute breaks require a future SQS or Step Functions continuation flow;
Lambda timeout cannot be increased beyond 900 seconds.

## Redeployment checklist

- Backend: deploy now because Python, IAM, environment, workers, and DynamoDB
  resources changed. One `serverless deploy` updates all Lambda functions.
- Frontend: redeploy once because brainstorming now polls its async job every
  60 seconds.
- Extension: reload the unpacked extension because it now sends `user_id`.
- Later deployments are only needed after relevant code, dependency,
  `serverless.yml`, or environment changes.
