# 16 July Frontend Plan

## Scope

Improve the current Ready to Comment and creator scraping UX without changing
the experimental backend-only own-post engagement screens.

## Changes

- Ready to Comment cards now include a direct `Open post` link when the scraped
  post URL is available.
- The post details drawer action text changed from `Open LinkedIn` to
  `Open post`.
- Long-running post scraping now starts an async backend scrape job and polls
  `GET /scrape-jobs/{job_id}` instead of waiting on the original scrape request.
- The run-scraping dialog shows job progress:
  - creators scraped
  - posts found
  - errors
- Add/bulk creator profile scraping uses the same async job status flow and
  shows profile scrape progress while imports finish.
- Creator profile copy now puts Experience last, adds blank spacing between
  experience entries, and uses rich clipboard labels when the browser supports
  HTML clipboard writes.
- Creator detail experience display now preserves full saved experience blocks
  instead of reducing them to truncated single-line rows.

## Polling

The frontend checks job status immediately after starting a job, then every
three minutes until the backend reports `succeeded` or `failed`.

## Ready To Comment

- Clamp creator headlines on cards to two lines with an ellipsis.
- Make the complete post card open the existing details drawer while preserving
  the separate copy, Open post, and View Details actions.
- Use direct feed URLs for Open post and copied post links.
- Rename time ranges to explicit hour buckets:
  - Last 12 h
  - Last 24 h
  - 24-48 h
  - 48-72 h

## Creator List

- Replace last-checked sorting options with:
  - All Creators
  - Recently Added
  - New Posts
  - Profile Never Scraped
  - Name A-Z
- Apply Recently Added and New Posts as filters before pagination so later
  pages do not contain creators outside the selected mode.
- Profile Never Scraped shows creators without a saved profile scrape timestamp,
  including profiles that still need a successful retry.
- Add a row-level profile scrape action.
- Add a bulk profile scrape action for selected creators and reuse the async
  scrape progress display.

## Experience Display And Copy

- Split legacy concatenated experience text into individual jobs for display.
- Display each role as a separate experience row.
- Add blank lines between jobs in copied profile text so multiple experiences
  remain readable.

## Metric And Drawer Corrections

- The creator summary shows Added Today and Posts From Last Scrape.
- Ready to Comment metrics are independent of search, creator, and time filters.
- Total Scraped Posts uses the cumulative backend count.
- The post drawer matches the import drawer width and shows the complete creator
  headline while card headlines remain limited to two lines.
