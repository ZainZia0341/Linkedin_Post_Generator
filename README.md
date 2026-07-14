# LinkedIn Post Generator

Monorepo for the LinkedIn Post Generator project.

- `backend/` contains the FastAPI app, DynamoDB repository, scraping code,
  current backend docs, tests, Docker files, and the old Streamlit UI.
- `frontend/` is reserved for the upcoming Next.js web app.

The Streamlit app is still present under `backend/streamlit_ui`, but it is now a
legacy/dev UI. The product UI should be built in `frontend/`.

## Local Development

Run backend commands from the backend folder:

```bash
cd backend
```

### Start DynamoDB Local

Docker Desktop must be running before this command works. DynamoDB Local stores
its files in `backend/dynamodb_localdb`.

```bash
docker compose -f docker-compose.dynamodb.yml up -d
```

The compose file also starts DynamoDB Admin:

```text
http://localhost:8001
```

### Start FastAPI Backend

The API runs on `http://localhost:7860` and exposes docs at
`http://localhost:7860/docs`.

```bash
uv run uvicorn app.api.main:app --reload --host 127.0.0.1 --port 7860
```

### Start Legacy Streamlit UI

This UI is kept for now but should not be treated as the future frontend.

```bash
uv run streamlit run streamlit_ui/app.py --server.port 8501
```

To point Streamlit at a different API URL:

```powershell
$env:LINKEDIN_API_BASE_URL="http://localhost:7860"
uv run streamlit run streamlit_ui/app.py --server.port 8501
```

### Quick Checks

Run these from `backend/`:

```bash
curl http://localhost:7860/health
aws dynamodb list-tables --endpoint-url http://localhost:8000
```

If Streamlit is running:

```bash
curl http://localhost:8501
```

### Stop Services

If FastAPI or Streamlit are running in foreground terminals, press `Ctrl+C` in
each terminal.

Stop DynamoDB Local and DynamoDB Admin:

```bash
docker compose -f docker-compose.dynamodb.yml stop
```

Remove the containers without deleting local DB files:

```bash
docker compose -f docker-compose.dynamodb.yml down
```

Do not use `down -v` if you want to keep local database data.

Stop FastAPI and Streamlit by port in PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 7860 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Get-NetTCPConnection -LocalPort 8501 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

## Backend Tests

Run from `backend/`:

```bash
uv run python -m compileall app streamlit_ui test scripts
uv run pytest
```

## AWS Lambda Backend Deployment

The FastAPI backend can be deployed as a Lambda container image through
`backend/serverless.yml`. This deployment creates DynamoDB tables in AWS and
keeps Playwright scraping disabled in Lambda; run scraping locally and point the
local backend at the AWS DynamoDB tables when you need to ingest LinkedIn data.

See:

```text
backend/docs/aws_lambda_deployment.md
```

## Frontend

The `frontend/` folder is ready for the Next.js app. The first frontend planning
draft is:

```text
frontend/docs/first_plan_draft.md
```

When the Next.js project is initialized, frontend commands should be run from
`frontend/`.

### Start Next.js Frontend

Install dependencies once:

```bash
cd frontend
npm install
```

Start the dev server:

```bash
npm run dev
```

Open:

```text
http://localhost:3000
```

The frontend proxies API requests through Next.js to FastAPI. By default it uses:

```text
API_BASE_URL=http://localhost:7860
NEXT_PUBLIC_DEFAULT_USER_ID=test-user-1
```

To override those values, create `frontend/.env.local` from
`frontend/.env.example`.

### Stop Next.js Frontend

If it is running in a foreground terminal, press `Ctrl+C`.

Stop by port in PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 3000 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

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
