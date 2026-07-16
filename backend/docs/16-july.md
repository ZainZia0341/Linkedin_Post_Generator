# 16 July Backend Plan

## Scope

Make the existing long-running creator scraping flows asynchronous so the
frontend no longer waits on a single 30-60 minute HTTP request.

This applies to current production scraping flows only:

- creator recent-post scraping
- creator profile-detail scraping

The experimental own-post engagement APIs stay synchronous for now until the UI
is designed and tested.

## Implementation

- Keep existing synchronous endpoints for FastAPI/manual testing:
  - `POST /creators/scrape/recent-24h`
  - `POST /creators/profile-details/scrape`
- Add async job start/status endpoints:
  - `POST /scrape-jobs/creators/recent-24h`
  - `POST /scrape-jobs/creators/profile-details`
  - `GET /scrape-jobs/{job_id}`
- Store job state in local backend memory for local FastAPI runs.
- Update progress after each creator finishes:
  - total creators
  - scraped creators
  - total posts found for post scraping
  - profile records saved for profile scraping
  - current creator id
  - per-creator errors
- Return the original scrape response under `result` when the job succeeds.

## Notes

This does not create new DynamoDB tables and does not change existing creator
activity persistence. Job state is intentionally process-local; restarting the
backend clears in-flight job status.

## Own-Post Engagement And Actions

- Canonicalize tracked own-post URNs to direct LinkedIn feed URLs before
  scraping. This prevents the engagement scraper from opening post analytics.
- Read comments from stable comment URNs and save the commenter name, profile
  URL, headline, connection degree, comment text, timestamp, and comment URN.
- Read the aggregate reaction count and open the reactors list only when the
  post has reactions.
- Keep reposts out of the engager list unless LinkedIn exposes repost actor
  identities. The supplied post DOM only exposes an aggregate repost count.
- Allow the DM endpoint to use explicitly supplied profile URLs even when the
  profile is not already present in saved post engagement data.
- Support LinkedIn messaging links, visible message composers, Send controls,
  and confirmation that the composer clears after submission.

## Profile Experience Extraction

- Prefer individual dated experience list items over a parent container that
  contains several jobs.
- Ignore generic list items without employment dates.
- Keep the existing saved profile schema and improve extraction without adding
  tables or changing existing endpoint contracts.

## Dashboard Metrics

- Recently Added now means creators added on the current calendar day.
- Save the number of posts returned by the most recent creator-post scrape.
- Maintain a cumulative scraped-post count even when post records older than
  three days are pruned.
