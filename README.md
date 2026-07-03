---
title: LinkedIn Post Generator API
sdk: docker
app_port: 7860
---

# LinkedIn Post Generator API

## Local Development

Run these services in separate terminals from the project root.

### Start DynamoDB Local

Docker Desktop must be running before this command works. If DynamoDB Local is
not reachable, API routes that need saved data return HTTP 503.

```bash
docker compose -f docker-compose.dynamodb.yml up -d
```

### Start FastAPI Backend

The API runs on `http://localhost:7860` and exposes docs at
`http://localhost:7860/docs`.

```bash
uv run uvicorn app.api.main:app --reload --host 127.0.0.1 --port 7860
```

### Start Streamlit UI

The UI runs on `http://localhost:8501` and calls the FastAPI backend at
`http://localhost:7860` by default.

```bash
uv run streamlit run streamlit_ui/app.py --server.port 8501
```

To point the UI at a different API URL:

```bash
$env:LINKEDIN_API_BASE_URL="http://localhost:7860"
uv run streamlit run streamlit_ui/app.py --server.port 8501
```

### Quick Checks

```bash
curl http://localhost:7860/health
curl http://localhost:8501
aws dynamodb list-tables --endpoint-url http://localhost:8000
```

### Stop Services

If FastAPI or Streamlit are running in foreground terminals, press `Ctrl+C` in
each terminal.

Stop DynamoDB Local:

```bash
docker compose -f docker-compose.dynamodb.yml stop
```

Stop FastAPI and Streamlit by port in PowerShell:

```powershell
Get-NetTCPConnection -LocalPort 7860 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Get-NetTCPConnection -LocalPort 8501 -State Listen | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

Remove the DynamoDB Local container instead of only stopping it:

```bash
docker compose -f docker-compose.dynamodb.yml down
```

## Hugging Face Spaces Deployment

This repo is configured for a Docker Space with `app_port: 7860`.

Inside the Space container:

- Streamlit runs publicly on `0.0.0.0:7860`
- FastAPI runs internally on `127.0.0.1:8001`
- DynamoDB Local runs internally on `127.0.0.1:8000`
- Streamlit calls FastAPI through `LINKEDIN_API_BASE_URL=http://127.0.0.1:8001`

The Docker image starts all services with:

```bash
bash scripts/start_hf_space.sh
```

Deploy to the existing Space remote:

```bash
git push hf fastapi-dev:main
```

The Space URL is:

```text
https://huggingface.co/spaces/ZainZia/linkedin-post-generator
```

### Space Secrets

Do not commit `.env`. Add runtime secrets in the Space settings instead:

```text
GOOGLE_API_KEY
GROQ_API_KEY
ANTHROPIC_API_KEY
TAVILY_API_KEY
DEFAULT_LLM_PROVIDER
DEFAULT_LLM_MODEL
LINKEDIN_AUTOMATION_MODE
LINKEDIN_HEADLESS
```

### DynamoDB Persistence

DynamoDB Local stores data in `/data/dynamodb` when `/data` is available and
writable. Attach persistent storage to the Space if you want users, threads,
creators, and activities to survive Space restarts.

If no persistent `/data` volume is attached, the app still works, but database
files are written to `/tmp/dynamodb` and can be lost when the Space sleeps,
restarts, or rebuilds.

## LinkedIn Burner Session Bootstrap

The app does not automate LinkedIn login. For burner mode, create the isolated
Playwright session once:

```bash
uv run python scripts/bootstrap_linkedin_session.py
```

Log in manually in the opened browser window with a burner account only. After
that, set `LINKEDIN_AUTOMATION_MODE=burner` and the API will reuse the isolated
session in `schema/local_db/playwright/linkedin_burner_profile`.
