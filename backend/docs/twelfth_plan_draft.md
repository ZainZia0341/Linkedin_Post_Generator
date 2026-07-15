# Twelfth Plan Draft - Backend APIs For Own Post Engagement And Actions

## Goal

Build backend-only APIs for tracking posts, scraping engagement from LinkedIn
post pages, storing engagers, and triggering Playwright actions from stored
engager lists. No frontend UI is planned for this phase; every endpoint should
be testable from FastAPI docs.

## Current Scraping Error Finding

The frontend scrape dialog calls the Next proxy route:

```text
POST /api/backend/creators/scrape/recent-24h
```

That proxy forwards to FastAPI at:

```text
API_BASE_URL or NEXT_PUBLIC_API_BASE_URL, default http://localhost:7860
```

Scraping routes are already excluded from the proxy's 60 second timeout. So if
the UI shows only `fetch failed`, the likely causes are:

- FastAPI is not running on the configured backend URL.
- `API_BASE_URL`/`NEXT_PUBLIC_API_BASE_URL` points to the wrong port.
- The backend process crashed or disconnected while Playwright was running.
- The browser/session/Dynamo dependency failed before FastAPI could return a
  structured response.

This pass improves the proxy error message so it includes the backend origin
and tells the user to check the configured FastAPI URL.

## Implemented In This Pass

- Scraped creator activities now have a 3 day retention rule based on
  `fetched_at`.
- `POST /creators/scrape` and `POST /creators/scrape/recent-24h` prune stored
  activities older than 3 days whenever a scrape starts.
- `RecentScrapeCreatorsRequest.window_hours` is capped at 72 hours.
- `GET /users/{user_id}/activities/recent-24h` also caps `window_hours` at 72.
- DynamoDB repository now exposes `delete_activity(...)` for safe activity row
  removal.

Retention rule:

```text
Delete activity when activity.fetched_at < now - 3 days.
```

This is based on scrape date, not LinkedIn posted date, matching the current UI
need to keep only recently scraped records in the system.

## Architecture Direction

Use one pipeline:

```text
tracked post -> engagement scrape -> stored engagers -> user-selected action -> action log
```

There should not be separate backend systems for platform-published posts and
posts created directly on LinkedIn. They need different intake endpoints, but
after intake both should write to the same post table and use the same
engagement/action services.

## Post Intake

### 1. Posts Published Through The Platform

When the app later supports publishing to LinkedIn, the publish endpoint should
store the LinkedIn post URL/URN as soon as Playwright confirms the post.

Suggested endpoint:

```text
POST /linkedin/posts/publish
```

Suggested request:

```json
{
  "user_id": "test-user-1",
  "thread_id": "generated-thread-id",
  "post_text": "Final post text"
}
```

Suggested response:

```json
{
  "post_id": "urn:li:activity:123",
  "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:123/",
  "source": "platform",
  "status": "published"
}
```

### 2. Posts Published Directly On LinkedIn

For posts not created through the app, scrape the user's own LinkedIn activity
feed and upsert recent posts into the same table.

Suggested endpoint:

```text
POST /linkedin/posts/sync-recent
```

Suggested request:

```json
{
  "user_id": "test-user-1",
  "window_hours": 72,
  "max_posts": 30,
  "launch_delay_seconds": 3
}
```

Suggested response:

```json
{
  "user_id": "test-user-1",
  "checked_count": 30,
  "saved_count": 12,
  "posts": []
}
```

## Data Model

### `linkedin_post_generator_own_posts`

Partition key:

```text
user_id
```

Sort key:

```text
post_id
```

Fields:

- user_id
- post_id
- post_url
- source: `platform | direct`
- text
- created_at_text
- estimated_posted_at
- first_seen_at
- last_scraped_at
- reaction_count
- comment_count
- impression_count
- scrape_status
- raw_metadata

### `linkedin_post_generator_post_engagers`

One row per `(post, person)`, not one row per engagement event.

Partition key:

```text
user_post_id = "{user_id}#{post_id}"
```

Sort key:

```text
profile_url or profile_urn
```

Fields:

- user_id
- post_id
- post_url
- profile_url
- profile_urn
- name
- headline
- connection_degree
- engagement_types: `["like", "comment"]`
- comment_text
- comment_permalink
- comment_urn
- comment_text_hash
- comment_timestamp_text
- scraped_at
- source
- raw_metadata

Important rule:

If one person both likes and comments, update the same engager row and merge
`engagement_types` instead of creating duplicate prospects.

### `linkedin_post_generator_linkedin_action_logs`

Partition key:

```text
user_id
```

Sort key:

```text
action_id
```

Fields:

- action_id
- user_id
- post_id
- profile_url
- action_type: `comment_reply | connection_request | dm`
- requested_text
- final_text
- status: `queued | running | sent | skipped | failed`
- skip_reason
- error_message
- created_at
- started_at
- finished_at

Use this table to avoid sending the same connection request or DM repeatedly
across multiple posts.

## Engagement Scraping APIs

### List Own Posts

```text
GET /users/{user_id}/linkedin/posts?source=&window_hours=72&limit=100
```

Returns tracked own posts from both platform and direct LinkedIn intake.

### Scrape Engagement For One Post

```text
POST /linkedin/posts/{post_id}/engagement/scrape
```

Request:

```json
{
  "user_id": "test-user-1",
  "include_likes": true,
  "include_comments": true,
  "launch_delay_seconds": 3
}
```

Response:

```json
{
  "user_id": "test-user-1",
  "post_id": "urn:li:activity:123",
  "like_count": 10,
  "comment_count": 4,
  "engagers_saved": 12,
  "errors": []
}
```

### List Engagers

```text
GET /linkedin/posts/{post_id}/engagers?engagement_type=&connection_degree=&limit=100
```

Returns stored engagers only. It should not scrape LinkedIn during a read call.

## Action APIs

### Reply To Commenters

Only valid for commenters. Likes do not have a reply surface on LinkedIn.

```text
POST /linkedin/actions/comment-replies
```

Request:

```json
{
  "user_id": "test-user-1",
  "post_id": "urn:li:activity:123",
  "profile_urls": ["https://www.linkedin.com/in/example/"],
  "reply_text": "Thanks for sharing your thoughts."
}
```

Backend behavior:

- Load stored engagers.
- Keep only users with `comment` in `engagement_types`.
- Re-find comments using `comment_urn` or permalink when available.
- Fallback locator may use `name + timestamp + text hash`.
- Write action logs for sent, skipped, and failed rows.

### Send Connection Requests To Likers Or Commenters

This is the main action for "likes and comments" in this phase.

```text
POST /linkedin/actions/connection-requests
```

Request:

```json
{
  "user_id": "test-user-1",
  "post_id": "urn:li:activity:123",
  "profile_urls": [],
  "engagement_types": ["like", "comment"],
  "note": "Thanks for engaging with my post."
}
```

Backend behavior:

- Load engagers from the selected post.
- Filter by selected engagement types.
- Skip existing first-degree connections.
- Skip profiles already contacted in action logs.
- Queue through the shared LinkedIn action limiter.

### DM First-Degree Engagers

Only valid for first-degree connections.

```text
POST /linkedin/actions/dms
```

Request:

```json
{
  "user_id": "test-user-1",
  "post_id": "urn:li:activity:123",
  "profile_urls": [],
  "message": "Thanks for engaging with my post."
}
```

Backend behavior:

- Require `connection_degree == "1st"`.
- Skip non-first-degree profiles.
- Log every result.

## Rate Limiting And Safety

All Playwright writes must use one shared per-account queue. Do not create
separate independent rate limits for reply, DM, and connect actions.

Suggested first-pass caps:

- scraping reads: low concurrency, existing burner mode should stay sequential
- connection requests: daily cap per user
- DMs: daily cap per user
- comment replies: daily cap per user
- randomized delay between actions

## Selector Strategy

- Centralize LinkedIn selectors in one backend module.
- Prefer accessible labels and stable attributes over generated CSS classes.
- Treat "0 engagers found" as a warning event when visible counts are non-zero.
- Store raw scrape diagnostics with each scrape run so selector breakage is
  visible from FastAPI responses/logs.

## Suggested Build Order

1. Add own-post table and repository methods.
2. Add `POST /linkedin/posts/sync-recent` for direct LinkedIn post intake.
3. Add `GET /users/{user_id}/linkedin/posts`.
4. Add post engagement scraper for comments first, including stable comment
   references.
5. Add likes scraper and merge likers into the same engager table.
6. Add `GET /linkedin/posts/{post_id}/engagers`.
7. Add action log table.
8. Add comment reply API.
9. Add connection request API for likers/commenters.
10. Add DM API for first-degree engagers.
11. Add shared action queue/rate limiter before enabling bulk actions.
12. Add async scrape/action job endpoints if FastAPI docs testing shows sync
    calls are too slow for real accounts.

## Acceptance Criteria

- A post published through the platform and a post synced from LinkedIn both
  appear in the same own-post list.
- Engagement scraping stores each engager once per post, with merged like and
  comment signals.
- Comment replies only target stored commenters with a stable comment ref.
- Connection requests can target likers and commenters from stored engagement
  rows.
- DMs skip non-first-degree engagers.
- Action logs prevent duplicate outreach.
- All action endpoints return per-profile sent/skipped/failed results.
- FastAPI docs can exercise every backend workflow without frontend UI.






=================================================================
Done. Backend-only changes, no UI touched.
Implemented from twelfth_plan_draft.md:
Added own LinkedIn post tracking/sync APIs.
Added post engagement scrape API for likes/comments.
Added stored engagers model with one row per person per post.
Added dry-run safe action APIs for:comment replies
connection requests
DMs to first-degree engagers

Added action logs to prevent duplicate real connection requests/DMs.
Added DynamoDB support for:*_own_posts
*_post_engagers
*_linkedin_action_logs

New Swagger routes:
POST /linkedin/posts/publish
POST /linkedin/posts/sync-recent
GET  /users/{user_id}/linkedin/posts
POST /linkedin/posts/{post_id}/engagement/scrape
GET  /linkedin/posts/{post_id}/engagers
GET  /users/{user_id}/linkedin/action-logs
POST /linkedin/actions/comment-replies
POST /linkedin/actions/connection-requests
POST /linkedin/actions/dms
Key files changed:
[main.py](D:/Linkedin_Post_Generator/backend/app/api/main.py)
[schemas.py](D:/Linkedin_Post_Generator/backend/app/api/schemas.py)
[services.py](D:/Linkedin_Post_Generator/backend/app/api/services.py)
[dynamodb.py](D:/Linkedin_Post_Generator/backend/app/db/dynamodb.py)
[linkedin_post_engagement.py](D:/Linkedin_Post_Generator/backend/app/linkedin_post_engagement.py)
[linkedin_post_actions.py](D:/Linkedin_Post_Generator/backend/app/linkedin_post_actions.py)
Validation passed:
13 passed in 12.06s
FastAPI import check also passed, and all new LinkedIn routes are visible. For testing actions, keep dry_run: true first. Real Playwright write actions need scraping enabled plus burner/authenticated LinkedIn session.

Edited 7 files+2,117-148Review changesUndoReview

backend/app/api/main.pybackend/app/api/main.py+200-56
backend/app/api/schemas.pybackend/app/api/schemas.py+176-10
backend/app/api/services.pybackend/app/api/services.py+822-30
backend/app/db/dynamodb.pybackend/app/db/dynamodb.py+57-16
backend/app/linkedin_post_actions.pybackend/app/linkedin_post_actions.py+256-0
backend/app/linkedin_post_engagement.pybackend/app/linkedin_post_engagement.py+367-0
backend/test/test_scripts/test_fastapi_services.pybackend/test/test_scripts/test_fastapi_services.py+239-36
Collapse files