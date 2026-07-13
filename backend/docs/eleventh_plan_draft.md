# Eleventh Plan Draft - Backend Needs For Creator Posts And Scraping Screens

## Goal

Track backend work needed by the new creator posts and scraping frontend screens.
No backend code was changed for this frontend pass.

## Existing APIs Reused

The frontend now reuses these existing APIs:

```text
GET /users/{user_id}/data?limit=1000
GET /users/{user_id}/activities?limit=100
GET /users/{user_id}/creators/{creator_id}/activities?limit=20
GET /users/{user_id}/creators/{creator_id}/profile-details
POST /creators
POST /creators/import/preview
POST /creators/import
POST /creators/profile-details/scrape
POST /creators/scrape/recent-24h
POST /posts/from-creator-activity
POST /comments/generate
DELETE /users/{user_id}/creators/{creator_id}
```

## Behavior Covered By Existing Backend

- Single creator add saves the creator record.
- Bulk import preview parses files, normalizes URLs, checks existing creators,
  detects duplicate file rows, and returns errors without saving.
- Bulk import saves only new valid creators and skips existing/duplicate rows.
- Profile-details scraping saves and returns name, headline, about, location,
  profile image URL, and experience.
- Recent scraping can run for all creators or selected creators with
  `window_hours` and `max_posts`.
- Saved creator activities can be listed and used to generate similar posts or
  comments.
- Profile scraping and post scraping request bodies now support
  `launch_delay_seconds`.

Default launch delay:

```json
{
  "launch_delay_seconds": 3
}
```

This delay is applied immediately before each Playwright launch call for:

- `POST /creators/profile-details/scrape`
- `POST /creators/scrape`
- `POST /creators/scrape/recent-24h`

Reason: the local burner-profile Chromium context can randomly fail with
`ProcessSingleton` profile-lock errors when a previous browser process has not
released the profile directory yet. The delay gives Chromium time to release
the shared profile lock. Callers can set the value to `0` to skip the wait or a
higher value if the local machine needs more time.

## Backend Still Needed

### 1. Scrape Job History

The Figma screens include job history, progress, failures, and per-creator
breakdown. The backend should persist one scrape run record per job.

Suggested endpoint:

```text
GET /users/{user_id}/scrape-runs?limit=20
GET /users/{user_id}/creators/{creator_id}/scrape-runs?limit=20
```

Suggested fields:

- scrape_run_id
- user_id
- creator_ids
- scope
- window_hours
- max_posts
- status
- started_at
- finished_at
- checked_creator_count
- posts_found
- new_posts_saved
- errors
- timeline events

### 2. Async Scrape Jobs

Current scraping is synchronous. If scraping may run for many creators, add an
async job model.

Suggested endpoints:

```text
POST /creators/scrape/jobs
GET /creators/scrape/jobs/{job_id}
```

The existing synchronous `POST /creators/scrape/recent-24h` can remain for small
manual jobs.

### 3. Scraped Post Detail/Delete

The frontend can render details from activity records, but delete is not wired.

Suggested endpoint:

```text
DELETE /users/{user_id}/creators/{creator_id}/activities/{post_id}
```

### 4. Scraped Post Search And Pagination

The current frontend loads up to 100 user activities and filters client-side.
For larger datasets add:

```text
GET /users/{user_id}/activities/search?q=&creator_id=&status=&cursor=&limit=
```

Suggested response:

```json
{
  "items": [],
  "next_cursor": "",
  "total_count": 1284
}
```

### 5. AI Insight And Related Post Read Models

The new frontend intentionally removed the AI insights and related posts drawer
sections until the backend has real data.

Needed later:

- analysis fields such as tone, topic, hook quality, reading time, CTA type
- related-post recommendation/query endpoint

## Acceptance Criteria

- Scrape job history can be displayed without using saved activity rows as a
  substitute.
- Long-running scrape jobs do not rely on one browser request staying open.
- Scraped post search/pagination works server-side.
- Deleting a scraped post removes the activity record safely.
- AI insights and related posts are only shown when backed by stored backend
  data.

## 2026-07-13 Follow-up Backend Notes

- Profile scraping now treats LinkedIn navigation chrome such as `0 notifications`
  and `Skip to main content` as an invalid profile scrape, returning
  `linkedin_profile_not_found` instead of saving those strings as profile data.
- When profile scraping returns `linkedin_profile_not_found`, the creator record
  stores a small profile-details marker so the frontend can display
  `Profile not found or unavailable` after reload.
- The Posts & Scraping UI now exposes 12h, 24h, 48h, 3-day, 4-day, and 7-day
  filters. A later backend endpoint should accept the same window values for
  server-side filtering instead of relying on the current client-side filter.
