# Sixth Plan Draft - FastAPI App Implementation Notes

This draft documents the implementation work completed after `fifth_plan_draft.md`.
The app is now a FastAPI-first backend with DynamoDB Local persistence. Streamlit is
removed from the runtime path.

## Goal Completed In This Pass

- Removed the Streamlit app entrypoint.
- Added a FastAPI backend with OpenAPI docs at `/docs`.
- Added DynamoDB Local storage through `boto3`.
- Added user-separated data using `user_id` in all user-owned records.
- Added APIs for users, LLM provider testing, post generation, post modification,
  brainstorming, thread history, creator tracking, creator activity scraping, and
  generating a new post from a saved creator activity.
- Added local test users and a test data file.
- Updated Docker so Hugging Face or any container host can run the FastAPI app.
- Added a DynamoDB Local compose file and a repo folder named `dynamodb_localdb`.
- Kept the existing LLM, graph, formatting, writing style, and Playwright scraper
  code, but moved the external surface to API endpoints.

## Current Directory Structure

Important current folders and files:

```text
app/
  api/
    __init__.py
    main.py          # FastAPI app and route definitions
    schemas.py       # Pydantic request and response schemas
    services.py      # API business logic around existing generation/scrape code
  db/
    __init__.py
    dynamodb.py      # DynamoDB Local repository and table setup
  llms/
    ...              # Existing provider wrappers and key testing
  nodes/
    ...              # Existing graph nodes
  config.py          # App config, provider model list, DynamoDB config
  graph_state.py     # Existing post generation and chat edit graph runners
  linkedin_playwright_scraper.py
  creator_tracking.py

docs/
  first_plan_draft.md
  fifth_plan_draft.md
  sixth_plan_draft.md

dynamodb_localdb/
  .gitkeep           # Local DynamoDB files live here and are ignored by git

test/
  test_data/
    sample_users.json
  test_scripts/
    test_core_workflow.py
    test_fastapi_services.py

docker-compose.dynamodb.yml
Dockerfile
example.env
main.py              # Prints local run commands
README.md
```

The old `streamlit_ui/app.py` file was removed. The `streamlit_ui` folder can remain
empty or be deleted later.

## Runtime Commands

Start DynamoDB Local:

```powershell
docker compose -f docker-compose.dynamodb.yml up -d
```

Start the API:

```powershell
uv run uvicorn app.api.main:app --reload --port 7860
```

Open API docs:

```text
http://localhost:7860/docs
```

## Environment And Config

New or important settings in `example.env`:

```env
API_PORT=7860
API_LIST_LIMIT=10
SCRAPE_MAX_WORKERS=2

DYNAMODB_ENDPOINT_URL=http://localhost:8000
DYNAMODB_TABLE_PREFIX=linkedin_post_generator
AWS_DEFAULT_REGION=us-west-2
AWS_ACCESS_KEY_ID=dummy
AWS_SECRET_ACCESS_KEY=dummy

DEFAULT_LLM_PROVIDER=groq
DEFAULT_LLM_MODEL=openai/gpt-oss-120b
```

LinkedIn automation settings still exist:

```env
LINKEDIN_AUTOMATION_MODE=logged_out
LINKEDIN_HEADLESS=false
LINKEDIN_BROWSER_CHANNEL=chrome
LINKEDIN_BROWSER_PROFILE_DIR=
LINKEDIN_CHECK_MAX_POSTS=5
LINKEDIN_BURNER_EMAIL=
LINKEDIN_BURNER_PASSWORD=
```

Special note: for LinkedIn scraping, the most reliable mode is still a manually
bootstrapped browser profile or an already authenticated browser profile. Burner
email/password can fail if LinkedIn asks for challenges, terms updates, captcha, or
extra verification.

## DynamoDB Local Tables

Tables are created automatically on the first API request that needs the database.
The table names use `DYNAMODB_TABLE_PREFIX`.

### `linkedin_post_generator_users`

Key:

- Partition key: `user_id`

Stores:

- `user_id`
- `profile`
- `writing_style`
- `created_at`
- `updated_at`

Purpose:

- Keeps each test user profile and preferred writing style.
- Default seed users are created automatically if missing.

### `linkedin_post_generator_threads`

Key:

- Partition key: `user_id`
- Sort key: `thread_id`

Stores:

- `user_id`
- `thread_id`
- `topic`
- `topic_source`
- `original_post`
- `current_post`
- `conversation`
- `provider`
- `model`
- `source`
- `writing_style_snapshot`
- `profile_snapshot`
- `created_at`
- `updated_at`
- `generated_at`
- `modified_at`
- `modification_count`

Purpose:

- Keeps generated posts and modification conversation history separate by user.
- Modification replaces `current_post`.
- `original_post` stays as the first generated version for reference.

### `linkedin_post_generator_creators`

Key:

- Partition key: `user_id`
- Sort key: `creator_id`

Stores:

- `user_id`
- `creator_id`
- `profile_url`
- `display_name`
- `added_at`
- `updated_at`
- `last_checked_at`
- `seen_count`
- `new_count`

Purpose:

- Keeps tracked LinkedIn creators per user.
- The same creator can be tracked separately for different users.

### `linkedin_post_generator_activities`

Key:

- Partition key: `user_creator_id`
- Sort key: `post_id`

Stores:

- `user_creator_id`
- `user_id`
- `creator_id`
- `post_id`
- `post_url`
- `raw_text`
- `author_name`
- `posted_at_text`
- `fetched_at`
- `content_hash`
- `source`
- `is_new`

Purpose:

- Stores scraped creator posts without replacing old posts.
- `user_creator_id` is built as `{user_id}#{creator_id}`.
- `post_id` is taken from scraper data when available, otherwise a stable hash of
  normalized post text is used.
- When scraping runs again, the API returns only activities not already stored.

## Seed Test Users

Two users are seeded automatically when the database is initialized:

- `test-user-1`
- `test-user-2`

The same sample data is also available in:

```text
test/test_data/sample_users.json
```

Use that file when testing the add-user endpoint manually.

## API List

The OpenAPI schema is generated automatically by FastAPI at `/docs`.

### Health

`GET /health`

Returns:

```json
{
  "status": "ok"
}
```

This does not touch DynamoDB.

### Saved Actions

`GET /actions`

Returns the saved action strings used by brainstorming and post generation flows.

Examples:

- `Brainstorm post topics`
- `Create a post about a topic`
- `Change the tone of a post`
- `Add a CTA`

### LLM Providers

`GET /llms/providers`

Returns the provider and model options from `app/config.py`.

Response shape:

```json
{
  "groq": ["openai/gpt-oss-120b"],
  "gemini": ["gemini-3.5-flash"],
  "claude": ["claude-sonnet-4.6"]
}
```

The exact list comes from config.

### Test API Key

`POST /llms/test-key`

Request schema: `ApiKeyTestRequest`

```json
{
  "provider": "groq",
  "model": "openai/gpt-oss-120b",
  "api_key": "..."
}
```

Response schema: `ApiKeyTestResponse`

```json
{
  "ok": true,
  "message": "API key works.",
  "provider": "groq",
  "model": "openai/gpt-oss-120b"
}
```

How it works:

- Calls `test_provider_api_key` from the existing LLM layer.
- Does not save the key.

### Add User

`POST /users`

Request schema: `UserCreateRequest`

```json
{
  "user_id": "test-user-1",
  "profile": {
    "full_name": "Test User",
    "headline": "AI Engineer",
    "skills": ["Python", "FastAPI"]
  },
  "writing_style": {
    "name": "Clear Builder"
  }
}
```

Response schema: `UserResponse`

How it works:

- Creates or updates a user record.
- If profile is empty, a default profile is used.
- If writing style is missing, the built-in `Clear Builder` style is used.

### List Users

`GET /users?limit=10`

Response schema:

```text
list[UserResponse]
```

How it works:

- Scans the users table.
- Limit defaults to `API_LIST_LIMIT`.

### Get User

`GET /users/{user_id}`

Response schema: `UserResponse`

Returns the user profile and writing style.

### Update User

`PATCH /users/{user_id}`

Request schema: `UserUpdateRequest`

```json
{
  "profile": {
    "headline": "Backend AI Engineer"
  },
  "writing_style": {
    "name": "Story Driven"
  }
}
```

Response schema: `UserResponse`

How it works:

- Replaces only provided fields.
- Updates `updated_at`.

### User Data

`GET /users/{user_id}/data?limit=10`

Response schema: `UserDataResponse`

Returns:

- User profile and writing style.
- Tracked creators.
- Thread summaries.
- Recent creator activities.

### Generate Post

`POST /posts/generate`

Request schema: `GeneratePostRequest`

```json
{
  "user_id": "test-user-1",
  "idea": "How developers can use DynamoDB Local for faster backend testing",
  "generation_style": "Clear Builder",
  "topic_source": "manual",
  "provider": "groq",
  "model": "openai/gpt-oss-120b",
  "api_key": "optional-key"
}
```

Response schema: `ThreadResponse`

How it works:

- Loads the user profile and writing style.
- Builds an `LLMConfig` from request values, or defaults from config.
- Calls existing `run_post_generation`.
- Formats the result for LinkedIn.
- Ensures hashtags exist at the end.
- Saves a new thread in DynamoDB.
- Returns the provider and model actually used.

### Modify Post

`POST /posts/modify`

Request schema: `ModifyPostRequest`

```json
{
  "user_id": "test-user-1",
  "thread_id": "thread-id-from-generation",
  "modification_message": "Make it shorter and add a stronger CTA.",
  "provider": "groq",
  "model": "openai/gpt-oss-120b",
  "api_key": "optional-key"
}
```

Response schema: `ThreadResponse`

How it works:

- Finds the user and thread.
- Adds the modification message to the conversation.
- Calls existing `run_post_chat_edit`.
- Replaces `current_post` with the modified post.
- Increments `modification_count`.
- Updates `modified_at` and `updated_at`.

### Generate From Creator Activity

`POST /posts/from-creator-activity`

Request schema: `GenerateFromActivityRequest`

```json
{
  "user_id": "test-user-1",
  "creator_id": "theburningmonk",
  "post_id": "saved-creator-post-id",
  "provider": "groq",
  "model": "openai/gpt-oss-120b",
  "api_key": "optional-key"
}
```

Response schema: `ThreadResponse`

How it works:

- Checks the creator exists for that user.
- Checks the saved creator activity exists.
- Extracts writing style from the creator post.
- Generates a distinct post variation using existing generation graph.
- Saves the output as a new thread.
- The returned thread can be modified later through `/posts/modify`.

### Brainstorm

`POST /ideas/brainstorm`

Request schema: `BrainstormRequest`

```json
{
  "user_id": "test-user-1",
  "topic": "AI backend workflows",
  "action": "Find audience pain points",
  "provider": "groq",
  "model": "openai/gpt-oss-120b",
  "api_key": "optional-key"
}
```

Response schema: `BrainstormResponse`

How it works:

- Loads the user's profile.
- Uses the selected saved action and topic.
- Calls the existing research helper.
- Returns idea objects and research suggestions.
- Includes provider and model used.

### List User Threads

`GET /users/{user_id}/threads?limit=10`

Response schema:

```text
list[ThreadSummary]
```

Returns thread IDs, topics, source, and timestamps.

### Get Thread Detail

`GET /users/{user_id}/threads/{thread_id}`

Response schema: `ThreadResponse`

Returns:

- Current generated or modified post.
- Original generated post.
- Conversation history.
- Provider/model.
- Source metadata.
- Generation and modification timestamps.

### Delete Thread

`DELETE /users/{user_id}/threads/{thread_id}`

Response schema: `DeleteResponse`

Deletes the thread from DynamoDB.

### Add Creator

`POST /creators`

Request schema: `CreatorCreateRequest`

```json
{
  "user_id": "test-user-1",
  "profile_url": "https://www.linkedin.com/in/theburningmonk/"
}
```

Response schema: `CreatorResponse`

How it works:

- Normalizes the LinkedIn URL.
- Extracts `creator_id` from the profile URL.
- Saves the creator under the user ID.
- Multiple users can track the same creator separately.

### List Creators

`GET /users/{user_id}/creators?limit=10`

Response schema:

```text
list[CreatorResponse]
```

Returns tracked creators for that user.

### Delete Creator

`DELETE /users/{user_id}/creators/{creator_id}`

Response schema: `DeleteResponse`

Deletes the creator tracking record. Existing saved activities are not listed after
the creator is removed because activity listing walks the current creator list.

### Scrape Creators

`POST /creators/scrape`

Request schema: `ScrapeCreatorsRequest`

```json
{
  "user_id": "test-user-1",
  "creator_ids": ["theburningmonk"],
  "max_posts": 5
}
```

Response schema: `ScrapeCreatorsResponse`

```json
{
  "user_id": "test-user-1",
  "checked_creator_ids": ["theburningmonk"],
  "new_activities": [],
  "errors": []
}
```

How it works:

- Loads all tracked creators for the user, or only `creator_ids` if provided.
- Runs Playwright scraping in parallel with `ThreadPoolExecutor`.
- Parallelism is controlled by `SCRAPE_MAX_WORKERS`.
- Each scrape calls the existing `fetch_recent_profile_posts`.
- Each returned post receives a stable `post_id`.
- Existing posts are skipped by checking DynamoDB first.
- Only new activities are returned in the response.
- All new activities are saved without replacing old activity records.
- This endpoint is synchronous for now, as requested in the fifth plan.

### List Creator Activities

`GET /users/{user_id}/creators/{creator_id}/activities?limit=10`

Response schema:

```text
list[ActivityResponse]
```

Returns saved posts for one tracked creator.

### List All User Activities

`GET /users/{user_id}/activities?limit=10`

Response schema:

```text
list[ActivityResponse]
```

Returns recent saved activities across all currently tracked creators for that user.

## Schema Index

Schemas live in `app/api/schemas.py`.

- `ApiKeyTestRequest`
- `ApiKeyTestResponse`
- `UserCreateRequest`
- `UserUpdateRequest`
- `UserResponse`
- `GeneratePostRequest`
- `GenerateFromActivityRequest`
- `ModifyPostRequest`
- `ThreadResponse`
- `ThreadSummary`
- `BrainstormRequest`
- `BrainstormResponse`
- `CreatorCreateRequest`
- `CreatorResponse`
- `ScrapeCreatorsRequest`
- `ActivityResponse`
- `ScrapeCreatorsResponse`
- `UserDataResponse`
- `DeleteResponse`

## Implementation Details

### FastAPI Layer

`app/api/main.py` owns the API routes.

It uses a repository dependency:

- Creates a DynamoDB repository.
- Ensures tables exist on first DB-backed request.
- Seeds `test-user-1` and `test-user-2` if they are missing.
- Returns HTTP 503 if DynamoDB Local is not reachable.

### Service Layer

`app/api/services.py` keeps business logic out of route functions.

It handles:

- Default users.
- Provider/model resolution.
- LLM config creation.
- Post generation.
- Post modification.
- Brainstorming.
- Creator URL normalization.
- Creator scraping.
- Activity deduplication.
- Generating post variations from saved creator activities.

### Repository Layer

`app/db/dynamodb.py` wraps `boto3`.

It handles:

- Table creation.
- Put/get/query/delete operations.
- DynamoDB Decimal conversion.
- User, thread, creator, and activity data access.

### Existing Code Reused

The new API layer uses existing functions instead of rewriting core behavior:

- `run_post_generation`
- `run_post_chat_edit`
- `research_trending_topics`
- `fetch_recent_profile_posts`
- `normalize_linkedin_profile_url`
- `get_profile_id`
- `extract_writing_style`
- `format_linkedin_post`

## Special Behavior And Limits

- API list endpoints default to `API_LIST_LIMIT`, currently `10`.
- Scrape parallelism defaults to `SCRAPE_MAX_WORKERS`, currently `2`.
- Scraping is synchronous for now. The request waits until scraping finishes.
- API keys sent in request bodies are used for that request only and are not saved.
- DynamoDB Local uses dummy AWS credentials.
- `GET /health` works without DynamoDB. Most other endpoints need DynamoDB Local.
- LinkedIn may hide activity or require manual login. Use a bootstrapped browser
  profile if the burner login flow hits verification.
- Creator activity dedupe is per user and creator, not global.
- Generated posts are formatted and hashtags are appended if the model omits them.

## Verification Done

Commands run:

```powershell
uv run python -m compileall app test scripts
uv run pytest
docker compose -f docker-compose.dynamodb.yml up -d
```

Result:

```text
25 passed
DynamoDB Local started on port 8000.
GET /users returned the seeded test users.
```

## Useful Next Steps

- Add async job tracking for `/creators/scrape` later if scraping becomes slow.
- Add cursor pagination once data grows beyond local testing.
- Add a small API client collection for Postman.
- Add optional cleanup of creator activities when a creator is deleted.
- Add endpoint-level tests with FastAPI dependency overrides.
