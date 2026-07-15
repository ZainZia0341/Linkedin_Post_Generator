# Third Frontend Plan Draft - Ready To Comment UI Fixes

## Goal

Apply the requested UI cleanup for the posts scraping screen and creators
screen, while documenting the backend dependency for 3 day post retention.

## Implemented In This Pass

### Ready To Comment Naming

- Sidebar item changed from `Posts & Scraping` to `Ready to Comment`.
- Page title changed to `Ready to Comment`.
- The small topbar eyebrow text `posts` is hidden on this page.
- Comment generation breadcrumb now references `Ready to Comment`.

### Posts Screen Cleanup

Removed from the main posts screen:

- `Latest Scraping Results` horizontal banner.
- `Latest Scrape` card/section heading.
- `Posts discovered during the most recent scraping job` text.
- `Generate Comment` button from scraped post cards.
- `Playwright` source text from scraped post cards.

Updated behavior:

- The screen now shows retained recent posts, not only `is_new` posts.
- New posts show a `New` pill.
- Previously saved retained posts show an `Old` pill.
- Pagination shows 9 posts per page.
- Cards render as a 3 column grid on desktop, 2 columns on medium screens, and
  1 column on small screens.
- The post details drawer closes when clicking outside the right-side panel.

### Time Window Filters

Posts screen dropdown now shows only:

- Last 12 Hours
- Last Day
- Last 2 Days
- Last 3 Days

Run scraping modal now uses the same maximum 3 day window:

- Last 12h
- Last Day
- Last 2 Days
- Last 3 Days

### Creators Screen

- Removed the visible status badge column from the creators table.
- Replaced that table position with a profile copy icon.
- Renamed `New Posts` column to `New post (last 24 h)`.
- Renamed the matching metric to `New post (last 24 h)`.
- Added selected creator count in the table toolbar.
- Added a `Copy` button for selected creators.

Single profile copy format:

```text
Name
...

Headline
...

About
...

Experience
...

Location
...

LinkedIn
...
```

Selected profile copy format:

```text
1
Name
...

Headline
...

About
...

Experience
...

Location
...

LinkedIn
...

2
Name
...
```

### Creator Detail Copy

The `Copy Information` button on the creator detail profile section now copies
formatted labeled fields instead of plain unlabeled lines.

## Backend Changes Needed For This UI

Implemented with this pass:

- Scraped post retention is handled in the backend.
- Posts older than 3 days by `fetched_at` are deleted when scraping runs.
- Scrape and recent activity API windows are capped at 72 hours.

Reason:

The UI only exposes up to 3 days, and the backend should not keep older scraped
post rows around after scrape jobs.

## Scrape Error Note

The frontend proxy now returns a clearer message when it cannot reach FastAPI.
Scrape routes are not using the proxy's 60 second timeout, so a visible
`fetch failed` usually means the backend URL is wrong, FastAPI is not running,
or the backend disconnected while Playwright was running.

## Files Touched

- `frontend/components/AppShell.tsx`
- `frontend/components/PostsScrapingView.tsx`
- `frontend/components/RunScrapingDialog.tsx`
- `frontend/components/CreatorsView.tsx`
- `frontend/components/CreatorDetailView.tsx`
- `frontend/components/CommentGenerationView.tsx`
- `frontend/app/api/backend/[...path]/route.ts`
- `frontend/app/globals.css`
- `backend/app/api/main.py`
- `backend/app/api/schemas.py`
- `backend/app/api/services.py`
- `backend/app/db/dynamodb.py`
- `backend/test/test_scripts/test_fastapi_services.py`

## Acceptance Checks

- Ready to Comment screen has no latest scrape banner or latest scrape heading.
- Ready to Comment screen renders post cards instead of horizontal rows.
- Pagination shows 9 posts per page.
- `New` post badges are based on `fetched_at` from the last 24 hours; older
  retained posts show `Old`.
- Main time window filter stops at Last 3 Days.
- Scraping modal stops at Last 3 Days.
- Clicking outside post detail drawer closes it.
- Creators table no longer shows `Up To Date` status badges.
- Creators table no longer shows the `Never Scraped` filter.
- Creators table exposes row copy icons and selected-copy action.
- Copied profile text is labeled and readable.
