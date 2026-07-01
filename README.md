---
title: LinkedIn Post Generator API
sdk: docker
app_port: 7860
---

docker compose -f docker-compose.dynamodb.yml stop

docker compose -f docker-compose.dynamodb.yml start

aws dynamodb list-tables --endpoint-url http://localhost:8000

aws dynamodb scan --table-name linkedin_post_generator_users --endpoint-url http://localhost:8000

# LinkedIn Post Generator API

Start DynamoDB Local:

```bash
docker compose -f docker-compose.dynamodb.yml up -d
```

Docker Desktop must be running before this command works. If DynamoDB Local is
not reachable, API routes that need saved data return HTTP 503.

Run the FastAPI app:

```bash
uv run uvicorn app.api.main:app --reload --port 7860
```

Open the API docs:

```text
http://localhost:7860/docs
```

## LinkedIn Burner Session Bootstrap

The app does not automate LinkedIn login. For burner mode, create the isolated
Playwright session once:

```bash
uv run python scripts/bootstrap_linkedin_session.py
```

Log in manually in the opened browser window with a burner account only. After
that, set `LINKEDIN_AUTOMATION_MODE=burner` and the API will reuse the isolated
session in `schema/local_db/playwright/linkedin_burner_profile`.
