# Seventh Plan Draft - 24-Hour Creator Scrape And Bulk Creator Import

## Goal

Add new endpoints and Streamlit tabs without breaking the existing creator,
scrape, activity, generation, comment, and history flows.

The new work has three parts:

1. A separate time-based creator scraping endpoint that reuses the same tracked
   creators, Playwright scraper, DynamoDB repository, activity response shape,
   and saving behavior, but only saves and returns posts that look like they were
   posted inside the last 24 hours.
2. A separate sheet upload endpoint that adds many creator LinkedIn URLs for one
   user at once, while checking the user's existing creators first and skipping
   duplicates.
3. A separate DB-only endpoint and Streamlit tab for loading already saved
   24-hour creator posts without running the scraper again.

## Current Working Pieces To Reuse

- FastAPI routes live in `app/api/main.py`.
- Pydantic request and response models live in `app/api/schemas.py`.
- API business logic lives in `app/api/services.py`.
- DynamoDB Local persistence is already wrapped by `app/db/dynamodb.py`.
- Creator records are already keyed by `user_id` and `creator_id`.
- Activity records are already keyed by `user_creator_id` and `post_id`.
- LinkedIn profile URL normalization and creator ID extraction already exist in
  `app/creator_tracking.py`.
- Playwright scraping already exists in `app/linkedin_playwright_scraper.py` as
  `fetch_recent_profile_posts`.
- Scrape parallelism already uses `SCRAPE_MAX_WORKERS`, with sequential behavior
  when burner mode uses one persistent browser profile.
- The Streamlit UI already has creator, activity, comments, and generation tabs
  that call FastAPI through shared helper functions.

No new database tables are needed.

## New API Requirements

### 24-Hour Scrape Endpoint

Add a new endpoint:

```text
POST /creators/scrape/recent-24h
```

Request body:

```json
{
  "user_id": "test-user-1",
  "creator_ids": ["creator-one"],
  "max_posts": 5,
  "window_hours": 24
}
```

Rules:

- This endpoint is separate from the old `/creators/scrape` endpoint.
- It must not change old scrape behavior.
- It uses the same tracked creators for the user.
- It accepts optional `creator_ids`; if not provided, it checks all tracked
  creators for that user.
- It uses the same Playwright scraper function.
- It saves posts that are inside the requested time window.
- It returns posts inside the requested time window even when those posts were
  seen during a previous scrape run.
- It does not skip return values just because a post already exists in the DB.
- It still saves activities to DynamoDB so existing activity/history/comment
  flows can use them.
- If a returned post already exists in DynamoDB, update the existing activity
  record with the latest normalized data instead of creating a duplicate row.
- It should mark these response items with `is_new=false` when the activity was
  already stored and `is_new=true` when it was first saved in this run.
- It should update creator metadata such as `last_checked_at`, `seen_count`,
  `new_count`, and `updated_at`.
- It should return scraping errors in the same style as the existing scrape
  response.

### 24-Hour Filtering

The Playwright scraper currently returns LinkedIn-visible time strings such as:

- `1h`
- `45m`
- `Just now`
- `Yesterday`
- `1d`
- `2d`
- sometimes full dates, depending on what LinkedIn renders

The new endpoint will add a conservative parser in the service layer:

- Treat minutes and hours as inside 24 hours.
- Treat `just now` and similar values as inside 24 hours.
- Treat `1d` and `yesterday` as inside 24 hours.
- Treat values with days greater than 1, weeks, months, or years as outside the
  24-hour window.
- Treat unrecognized or blank values as outside the 24-hour window so old posts
  do not enter by accident.
- For saved DB records, combine `posted_at_text` with `fetched_at`. Example: if
  a post said `8h` when it was scraped on July 3, it should not still count as
  inside the current 24-hour window on July 6.

This is based on LinkedIn's rendered text, not a guaranteed original timestamp,
because the scraper does not currently expose a machine-readable post datetime.

### Bulk Creator Import Endpoint

Add a new endpoint:

```text
POST /creators/import
```

Form fields:

- `user_id`: required.
- `file`: uploaded `.csv`, `.txt`, or `.xlsx` file.

Rules:

- This endpoint is separate from the old single creator endpoint.
- It must not change old list/delete/scrape behavior.
- It should load all existing creators for the user before adding.
- It should normalize each LinkedIn URL before checking duplicates.
- It should skip duplicates already in the DB.
- It should also skip duplicates repeated inside the uploaded file.
- It should return:
  - creators that were added
  - creator IDs skipped as existing
  - row-level errors for invalid or unsupported values
  - total parsed URLs
- It should use the existing `create_creator`/normalization logic instead of
  inventing a new creator model.
- It should support Google Sheets by uploading an exported CSV/XLSX file.
- It should not require Google API credentials in this pass.

### Saved 24-Hour Activity Endpoint

Add a new endpoint:

```text
GET /users/{user_id}/activities/recent-24h?limit=100&window_hours=24
```

Rules:

- This endpoint is separate from both scrape endpoints.
- It must not run Playwright.
- It reads only from DynamoDB activity records already saved for the user.
- It uses the same LinkedIn time text parser as the 24-hour scrape endpoint.
- It estimates actual post time as `fetched_at - parsed LinkedIn age`, then
  compares that estimate with the current time window.
- It returns only saved activities that still look inside the requested time
  window, defaulting to 24 hours.
- It supports `limit` so the UI can request more than the default list size.
- It exists so a page refresh does not force another scrape just to view the
  saved recent posts.

### Single Creator Duplicate Behavior

The existing `POST /creators` endpoint already prevents physical duplicate rows
because DynamoDB keys are `user_id + creator_id`.

Tighten that behavior:

- When the creator already exists for the user, return the existing creator
  unchanged.
- Do not refresh `updated_at` just because the same creator was submitted again.
- Keep the response model unchanged so old UI/API callers are not broken.

## Streamlit UI Requirements

Add new tabs without removing or renaming existing tabs:

- `24h Scrape`
- `24h Saved`
- `Bulk Import`

The `24h Scrape` tab should:

- Select tracked creators for the active user.
- Let the user choose posts per creator.
- Call `/creators/scrape/recent-24h`.
- Display checked creators, errors, returned 24-hour activities, post text, and
  LinkedIn URL.
- Store the last result in Streamlit session state separately from the old scrape
  result.

The `Bulk Import` tab should:

- Upload `.csv`, `.txt`, or `.xlsx`.
- Send the file and active `user_id` to `/creators/import`.
- Show counts for added, skipped existing, skipped file duplicates, invalid rows,
  and total parsed URLs.
- Show a table of added creators and skipped/error details.

The `24h Saved` tab should:

- Call `/users/{user_id}/activities/recent-24h`.
- Read only from the database.
- Let the user choose the time window and limit.
- Show saved recent activities after page refresh without running the scraper.
- Display post text and LinkedIn URL.

Existing tabs must continue working:

- `Generate`
- `Ideas`
- `Modify`
- `Creators`
- `Activity`
- `Comments`
- `History`
- `Profile`

## Implementation Approach

### Schemas

Add new models in `app/api/schemas.py`:

- `RecentScrapeCreatorsRequest`
- `RecentScrapeCreatorsResponse`
- `RecentActivitiesResponse`
- `BulkCreatorImportResponse`

Reuse existing:

- `CreatorResponse`
- `ActivityResponse`

### Services

Add helper functions in `app/api/services.py`:

- Parse LinkedIn time text into a window decision.
- Parse CSV/text/XLSX uploads into URL candidates.
- Import creators in bulk while skipping existing and file-level duplicates.
- Scrape creators within a time window and save returned activities.
- List saved creator activities from DynamoDB within a requested time window.

Keep existing function names and variables unchanged where old endpoints depend
on them.

### Routes

Add routes in `app/api/main.py`:

- `POST /creators/import`
- `POST /creators/scrape/recent-24h`
- `GET /users/{user_id}/activities/recent-24h`

Use the same repository dependency and error handling style already used by the
old endpoints.

### UI

Patch `streamlit_ui/app.py` only through additive helpers:

- Add multipart upload helper.
- Add `last_recent_scrape`, `last_recent_db_activities`, and `last_bulk_import`
  session state keys.
- Add `render_recent_scrape_tab`.
- Add `render_recent_db_tab`.
- Add `render_bulk_import_tab`.
- Add both tab names and render calls.

## Testing Plan

Add focused tests in `test/test_scripts/test_fastapi_services.py`:

- Duplicate single creator add returns the existing record unchanged.
- Bulk import adds new creators and skips existing/file duplicates.
- Bulk import reports invalid LinkedIn URLs without stopping the whole import.
- 24-hour scrape returns previously seen posts again.
- 24-hour scrape filters out older LinkedIn time text.

Run:

```powershell
uv run python -m compileall app streamlit_ui test
uv run pytest
```

If live Playwright/LinkedIn is not available during tests, keep these tests on
mocked scraper responses only.
