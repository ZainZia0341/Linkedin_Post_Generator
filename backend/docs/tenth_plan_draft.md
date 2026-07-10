# Tenth Plan Draft - Backend Requirements For Next.js Frontend

## Goal

Document backend changes needed by the new Next.js frontend without changing the
current working backend code in this pass.

The frontend now lives in `frontend/` and should avoid mock data. If a feature
needs backend support that does not exist yet, the UI should show an empty or
API-needed state and this plan should track the backend work.

## Current Backend Endpoints Reused By Frontend

The frontend can already use:

- `GET /users/{user_id}/data?limit=1000`
- `GET /users/{user_id}/threads?limit=...`
- `GET /users/{user_id}/activities/recent-24h?limit=3&window_hours=24`
- `GET /users/{user_id}/creators?limit=...`
- `GET /users/{user_id}/creators/{creator_id}/profile-details`
- `GET /users/{user_id}/creators/{creator_id}/activities?limit=...`
- `GET /post-generation-styles`
- `POST /posts/generate`
- `POST /posts/modify`
- `POST /creators`
- `POST /creators/import`
- `POST /creators/scrape/recent-24h`
- `DELETE /users/{user_id}/creators/{creator_id}`

No backend code was changed for the first Next.js screen pass.

## Needed Backend Changes

### 1. Dashboard And Creator Stats

Return explicit dashboard stats from:

```text
GET /users/{user_id}/data
```

Needed shape:

```json
{
  "dashboard_stats": {
    "creator_count": 41,
    "thread_count": 32,
    "new_posts_today_count": 18,
    "activity_count": 120,
    "new_posts_from_last_scrape_count": 9,
    "needs_scraping_count": 1,
    "recently_added_count": 7,
    "recently_added_window_days": 7,
    "scraping_stale_after_hours": 24,
    "updated_at": "2026-07-09T00:00:00+00:00"
  }
}
```

This overlaps with `ninth_plan_draft.md`; keep that plan as the detailed DB
strategy. The frontend should eventually read these stats directly instead of
counting returned arrays.

Implementation status: partially implemented.

- `GET /users/{user_id}/data` now returns `dashboard_stats`.
- The stats are calculated in the backend and saved on the user record as
  `dashboard_stats` when `/data` is loaded.
- The creators screen now reads its top metric cards from this object instead
  of calculating them locally or calling a separate recent-activity API.
- `recently_added_count` uses a 7-day `added_at` window.
- `needs_scraping_count` counts creators that were never scraped or whose
  `last_checked_at` is older than 24 hours.
- `new_posts_from_last_scrape_count` sums the creators' saved `new_count`
  values, which are updated by scraper runs.

### 2. Scraper Window Status

The dashboard needs to know whether the 24-hour scraper has run for the current
window.

Add a saved scrape status/read model such as:

```json
{
  "recent_scrape_status": {
    "window_hours": 24,
    "last_started_at": "2026-07-09T00:00:00+00:00",
    "last_finished_at": "2026-07-09T00:10:00+00:00",
    "checked_creator_count": 41,
    "new_activity_count": 18,
    "error_count": 0,
    "status": "completed"
  }
}
```

This lets the frontend decide between:

- show new post count
- show `0`
- show `Run scraper`
- show scrape failed/partial state

### 3. Structured Generate Post Controls

Extend `POST /posts/generate` to accept structured controls instead of requiring
the frontend to fold everything into `idea`.

Suggested request:

```json
{
  "user_id": "test-user-1",
  "topic": "AI agents for SaaS",
  "post_type": "Create a post about a topic",
  "tone": "Professional",
  "length": "Medium",
  "writing_style_name": "Clear Builder",
  "topic_source": "manual"
}
```

Rules:

- Keep backward compatibility with the current `idea` and `generation_style`
  fields.
- Translate `tone`, `length`, and `writing_style_name` into prompt instructions
  in the service layer.
- Save these controls on the thread record for history and future editing.

### 4. Drafts Or Continue Working

Current frontend can use:

```text
GET /users/{user_id}/threads?limit=2
```

If the product needs true drafts, add:

```text
GET /users/{user_id}/drafts?limit=2
```

Suggested response item:

```json
{
  "thread_id": "thread-id",
  "title": "AI Agents for SaaS",
  "summary": "A post explaining how AI agents are transforming SaaS",
  "status": "draft",
  "updated_at": "2026-07-09T00:00:00+00:00"
}
```

This probably requires adding `status` to thread records.

### 5. App History

The Figma dashboard includes recent activity/history. The backend does not yet
have a single app-history endpoint.

Add:

```text
GET /users/{user_id}/app-history?limit=20
```

Suggested events:

- generated post
- edited post
- imported creators
- scraped creators
- saved new creator activity
- generated comment
- marked comment complete

Suggested shape:

```json
{
  "items": [
    {
      "event_id": "event-id",
      "event_type": "post_generated",
      "label": "Generated 'AI Agents for SaaS'",
      "occurred_at": "2026-07-09T00:00:00+00:00",
      "metadata": {
        "thread_id": "thread-id"
      }
    }
  ]
}
```

Implementation options:

- Build it dynamically from existing tables for now.
- Later save append-only event records if the product needs a reliable audit
  trail.

### 6. CORS Or Proxy Decision

Current frontend uses a Next.js API proxy:

```text
/api/backend/*
```

That means FastAPI does not need CORS changes yet.

If the frontend later calls FastAPI directly from the browser, add a controlled
CORS configuration for local and deployed frontend origins.

### 7. Creator Validation Preview

The add-creator drawer design has a `Validate Creator` step and live preview
before saving. The current backend only supports saving a creator directly with:

```text
POST /creators
```

Add:

```text
POST /creators/validate
```

Suggested request:

```json
{
  "user_id": "test-user-1",
  "profile_url": "https://linkedin.com/in/example"
}
```

Suggested response:

```json
{
  "creator_id": "example",
  "normalized_profile_url": "https://www.linkedin.com/in/example/",
  "display_name": "Example Creator",
  "headline": "Creator headline",
  "avatar_url": "",
  "already_tracked": false,
  "ready_to_add": true,
  "errors": []
}
```

Rules:

- Normalize and validate the URL.
- Check whether the creator is already tracked for the user.
- Do not create a creator record.
- If profile scraping is used for preview, keep it read-only and explicit.

### 8. Creator List Read Model

The creator list screen needs fields that are not all available on the current
creator records.

Add or derive:

- avatar/profile image URL
- headline
- status: active, needs scraping, never scraped
- last checked display value
- new posts in current 24-hour window
- recently added marker
- server-side total count

Recommended endpoint:

```text
GET /users/{user_id}/creators/summary?limit=50&cursor=...&status=...&q=...
```

This would avoid making the frontend load all creators and filter client-side as
the list grows.

Implementation status: partially implemented through existing endpoints.

- Profile details scraping now saves `profile_image_url` and `location` inside
  each creator record's `profile_details` object.
- Existing profile-details responses now return `profile_image_url` and
  `location`.
- A dedicated server-side creator summary endpoint is still not implemented.

### 9. Creator Detail Read Model

The creator detail screen needs a single endpoint that combines creator record,
profile details, recent activity stats, and scrape status.

Recommended endpoint:

```text
GET /users/{user_id}/creators/{creator_id}/detail
```

Suggested response sections:

- creator identity
- profile details
- tracking status
- quick action availability
- recent saved posts
- scrape history summary

Fields needed by the current design:

- display name
- headline
- avatar URL
- location
- creator since
- profile URL
- last checked
- next scrape
- latest activity
- posts found in 24 hours
- tracking enabled/encrypted state

Implementation status: partially implemented.

- Existing profile-details API now returns avatar/profile image URL and
  location after profile scraping.
- A combined creator detail read model and scrape-history endpoint are still
  planned work.

### 10. Scrape History

The creator detail design includes a scrape history table. The current backend
saves creator metadata and activities, but does not save one row per scrape run.

Add a scrape-run table or user/creator-scoped records.

Possible table:

```text
linkedin_post_generator_scrape_runs
```

Possible keys:

- partition key: `user_creator_id`
- sort key: `scrape_run_id` or `started_at`

Suggested fields:

- user_id
- creator_id
- scrape_run_id
- scrape_type
- status
- started_at
- finished_at
- posts_found
- new_posts_saved
- errors
- analysis_status

Endpoint:

```text
GET /users/{user_id}/creators/{creator_id}/scrape-runs?limit=20
```

### 11. Bulk Import Preview And Import

The import UI uses two separate backend calls:

```text
POST /creators/import/preview
POST /creators/import
```

Preview endpoint:

- Accepts `.csv`, `.txt`, and `.xlsx` files.
- Extracts LinkedIn profile URLs from the uploaded file.
- Normalizes valid URLs and returns them in `corrected_creators`.
- Checks the current creators table and returns URLs not already tracked in
  `new_creators`.
- Returns URLs already tracked in the database in `existing_creators`.
- Detects duplicate URLs inside the file and returns them in
  `duplicate_creators`.
- Returns invalid rows in `errors` with row, URL, and message.
- Does not save anything to the database.

Import endpoint:

```text
POST /creators/import
```

Implementation status: implemented for two-step synchronous import.

- The import endpoint parses the file again when the user clicks Import.
- URLs already tracked in the database are skipped and returned in
  `skipped_existing_creators`.
- Duplicate URLs inside the uploaded file are skipped and returned in
  `skipped_duplicate_creators`.
- Valid new creators are saved to the creators table and returned in
  `added_creators`.
- The response still includes the legacy ID arrays:
  `skipped_existing_creator_ids` and `skipped_duplicate_creator_ids`.

Still needed only if the UI must show live progress:

- async import job creation
- job status endpoint
- progress percentage

Possible endpoints:

```text
POST /creators/import-jobs
GET /creators/import-jobs/{job_id}
POST /creators/import-jobs/{job_id}/commit
```

### 12. Bulk Creator Actions

The creator list design has selected-row batch actions like scrape batch, add
tag, and remove.

Needed endpoints:

```text
POST /creators/scrape/recent-24h
DELETE or POST /users/{user_id}/creators/bulk-delete
POST /users/{user_id}/creators/tags
```

Current backend can scrape selected creators through
`POST /creators/scrape/recent-24h`, but does not have bulk delete or tags.

## Acceptance Criteria

- Frontend can render dashboard metrics without counting limited arrays.
- Frontend can tell whether the 24-hour scraper has run.
- Generate endpoint accepts tone and length as first-class fields.
- Continue Working either uses recent threads or true draft records.
- App history has a real backend source before the UI renders activity events.
- Add creator preview validates without saving.
- Creator list can be queried server-side with counts, statuses, and pagination.
- Creator detail can load one combined read model.
- Scrape history is persisted and queryable.
- Bulk import can expose progress only if product requires it.
- Existing backend endpoints remain backward compatible.
