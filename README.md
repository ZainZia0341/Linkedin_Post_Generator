# LinkedIn Post Generator

Monorepo for the LinkedIn Post Generator project.

- `backend/` contains the FastAPI app, DynamoDB repository, scraping code,
  current backend docs, tests, Docker files, and the old Streamlit UI.
- `frontend/` is reserved for the upcoming Next.js web app.

The Streamlit app is still present under `backend/streamlit_ui`, but it is now a
legacy/dev UI. The product UI should be built in `frontend/`.

## AWS Lambda Backend Deployment

The FastAPI backend deploys as a Lambda container image through
`backend/serverless.yml`. The deployment creates DynamoDB tables in AWS and
keeps Playwright scraping disabled in Lambda. Run scraping locally and point the
local backend at the AWS DynamoDB tables when you need to ingest LinkedIn data.

Full deployment notes live in:

```text
backend/docs/aws_lambda_deployment.md
```

### Normal Serverless Deploy


Run from `backend/`. Docker Desktop must be running.

```powershell
cd D:\Linkedin_Post_Generator\backend

$env:AWS_PROFILE="Team-GV-Zain"
$env:AWS_DEFAULT_REGION="us-east-2"
$env:BUILDX_NO_DEFAULT_ATTESTATIONS="1"

npx --yes serverless@3 deploy --stage dev --region us-east-2
```

### Manual ECR Login And Image Build

Use this only when you need to test or rebuild the Lambda image manually.
Do not store AWS passwords or tokens in files.

```powershell
cd D:\Linkedin_Post_Generator\backend

$env:AWS_PROFILE="Team-GV-Zain"
$env:AWS_DEFAULT_REGION="us-east-2"

aws ecr get-login-password --region us-east-2 |
docker login --username AWS --password-stdin 507881105575.dkr.ecr.us-east-2.amazonaws.com
```

Create the ECR repo if it does not already exist:

```powershell
aws ecr create-repository `
  --repository-name serverless-linkedin-post-generator-backend-dev `
  --region us-east-2
```

Build and push a Lambda-safe image:

```powershell
docker buildx build `
  --provenance=false `
  --sbom=false `
  --platform linux/amd64 `
  -f Dockerfile.lambda `
  -t 507881105575.dkr.ecr.us-east-2.amazonaws.com/serverless-linkedin-post-generator-backend-dev:latest `
  --push .
```

Check the pushed image manifest:

```powershell
aws ecr batch-get-image `
  --repository-name serverless-linkedin-post-generator-backend-dev `
  --image-ids imageTag=latest `
  --region us-east-2 `
  --query "images[0].imageManifestMediaType" `
  --output text
```

Expected good output:

```text
application/vnd.docker.distribution.manifest.v2+json
```

After the image check, deploy with Serverless:

```powershell
npx --yes serverless@3 deploy --stage dev --region us-east-2
```

## Local Development Commands

### DynamoDB Local

Run from `backend/`. DynamoDB Local stores files in `backend/dynamodb_localdb`.
The compose file also starts DynamoDB Admin at `http://localhost:8001`.

Start:

```powershell
cd D:\Linkedin_Post_Generator\backend
docker compose -f docker-compose.dynamodb.yml up -d
```

Stop containers:

```powershell
docker compose -f docker-compose.dynamodb.yml stop
```

Remove containers without deleting local DB files:

```powershell
docker compose -f docker-compose.dynamodb.yml down
```

Do not use `down -v` if you want to keep local database data.

### FastAPI Backend

The API runs on `http://localhost:7860` and exposes docs at
`http://localhost:7860/docs`.

Start:

```powershell
cd D:\Linkedin_Post_Generator\backend
uv run uvicorn app.api.main:app --reload --host 127.0.0.1 --port 7860
```

Stop by port:

```powershell
Get-NetTCPConnection -LocalPort 7860 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

### Next.js Frontend

Start:

```powershell
cd D:\Linkedin_Post_Generator\frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

Stop by port:

```powershell
Get-NetTCPConnection -LocalPort 3000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

### Quick Checks

```powershell
curl http://localhost:7860/health
aws dynamodb list-tables --endpoint-url http://localhost:8000
```

### Legacy Streamlit UI

This UI is kept for dev/reference only. The Next.js app in `frontend/` is the
main product UI.

Start:

```powershell
cd D:\Linkedin_Post_Generator\backend
$env:LINKEDIN_API_BASE_URL="http://localhost:7860"
uv run streamlit run streamlit_ui/app.py --server.port 8501
```

Open:

```text
http://localhost:8501
```

Stop by port:

```powershell
Get-NetTCPConnection -LocalPort 8501 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

## Backend Tests

Run from `backend/`:

```bash
uv run python -m compileall app streamlit_ui test scripts
uv run pytest
```

## Frontend

The `frontend/` folder contains the Next.js app. The first frontend planning
draft is:

```text
frontend/docs/first_plan_draft.md
```

The frontend proxies API requests through Next.js to FastAPI. By default it uses:

```text
API_BASE_URL=http://localhost:7860
NEXT_PUBLIC_DEFAULT_USER_ID=test-user-1
```

To override those values, create `frontend/.env.local` from
`frontend/.env.example`.

### Frontend Checks

Run from `frontend/`:

```bash
npm run typecheck
npm run build
```

## LinkedIn Burner Session Bootstrap

The app does not automate LinkedIn login. For burner mode, create the isolated
Playwright session once from `backend/`:

```bash
uv run python scripts/bootstrap_linkedin_session.py
```

Log in manually in the opened browser window with a burner account only. After
that, set `LINKEDIN_AUTOMATION_MODE=burner` in `backend/.env` and the API will
reuse the isolated session in:

```text
backend/schema/local_db/playwright/linkedin_burner_profile
```

## Hugging Face Spaces Deployment

The Docker app files now live under `backend/`.

For a Docker-based deployment, build from `backend/` or configure the platform to
use `backend/Dockerfile` as the Dockerfile and `backend/` as the build context.

The existing backend Docker image starts:

- Streamlit publicly on `0.0.0.0:7860`
- FastAPI internally on `127.0.0.1:8001`
- DynamoDB Local internally on `127.0.0.1:8000`

Deployment secrets should not be committed. Keep local secrets in
`backend/.env`; configure production secrets in the hosting platform.


# vercel Production link (main)
https://linkedin-post-generator-lyart.vercel.app

# vercel Preview link (dev)
https://linkedin-post-generator-git-dev-zain-zias-projects.vercel.app/dashboard

# Lambda backend url dev
https://ysshbf0inb.execute-api.us-east-2.amazonaws.com

