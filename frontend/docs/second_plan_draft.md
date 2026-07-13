# Second Frontend Plan Draft - Creator Posts And Scraping

## Goal

Add the new Next.js screens for scraped creator posts, scraping actions, and the
updated creator detail flow while using only real backend APIs.

## Implemented In This Pass

### Posts & Scraping Screen

Route:

```text
/posts-scraping
```

Navigation:

- Added `Posts & Scraping` to the main sidebar.
- The screen uses the same application shell and recent thread sidebar.

Data sources:

- `GET /users/{user_id}/data?limit=1000`
- `GET /users/{user_id}/activities?limit=100`
- `GET /users/{user_id}/creators/profile-details?limit=500`
- `POST /creators/scrape/recent-24h`
- `POST /posts/from-creator-activity`

UI behavior:

- Shows top metrics from saved activities and creator scrape timestamps.
- Shows searchable/filterable scraped post cards.
- Shows latest scraped posts and previously scraped posts from saved activity
  records.
- Shows scraped creator profile images and headlines in post cards, post
  detail drawers, and scraping creator selectors when profile-details data
  exists.
- `Run Scraping` opens a supported API-backed scraping modal.
- `Generate Similar Post` calls the existing post-from-activity endpoint.
- `Generate Comment` now opens the comment generation workspace at
  `/comments/generate?creator_id=...&post_id=...`.
- Job history button is disabled because the backend does not yet expose scrape
  job history.

### Comment Generation Workspace

Route:

```text
/comments/generate
```

Data sources:

- `GET /users/{user_id}/data?limit=1000`
- `GET /users/{user_id}/activities?limit=200`
- `GET /users/{user_id}/creators/{creator_id}/activities?limit=100` as a
  fallback if the selected post is not in the first user activity page.
- `GET /users/{user_id}/creators/profile-details?limit=500`
- `POST /comments/generate`
- `PATCH /comments/mark`

Implemented:

- Opens from any scraped-post `Generate Comment` action.
- Shows the selected creator and source post using scraped profile image and
  headline when available.
- Generates three alternative comment variations from the same saved post.
- Includes style, tone, and length controls; tone and length are passed through
  the comment topic text because the current backend endpoint only accepts one
  comment prompt/topic field.
- Pencil action opens an AI comment editor side panel.
- Final workspace from the Figma design is intentionally not implemented yet.
- `Mark Commented` saves the chosen comment with the existing comment mark API.

### Comment History / Content Library

Route:

```text
/history
```

Data sources:

- `GET /users/{user_id}/data?limit=1000`
- `GET /users/{user_id}/engagements/comments?limit=200`
- `GET /users/{user_id}/creators/profile-details?limit=500`
- `PATCH /comments/mark`

Implemented:

- Sidebar History now links to the content library screen.
- Shows saved/finalized comment records returned by the existing comments
  history endpoint.
- Shows creator profile images and headlines beside each saved comment when
  profile-details data exists.
- Supports local search plus creator/style filters.
- Clicking a history row or pencil action opens a saved-comment editor drawer.
- Saving from the drawer updates the comment through the existing mark API and
  keeps it in the finalized history list.

### Scraped Post Details Drawer

Implemented:

- Right-side drawer when a scraped post is opened.
- Creator summary.
- Original post text.
- Saved metadata such as creator ID, post ID, content hash, source, fetched
  time, and database status.
- Quick actions for copying text, copying/opening URL, generating a similar
  post, generating a comment, and closing.

Removed from this version:

- Related posts section.
- AI insights section.

These were removed because they either need extra backend analysis fields or a
separate related-posts read model.

### Run Scraping Modal

Implemented as a reusable component for:

- `/posts-scraping`
- `/creators/[creatorId]`

Supported fields:

- Scope: all active creators or selected creators.
- Creator selection when scope is selected.
- Time window: 12 hours, 24 hours, 3 days, 4 days, or 7 days.
- Max posts per creator.

Not shown because the current API does not support them as explicit options:

- Save posts to database toggle.
- Skip existing toggle.
- Force refresh toggle.
- Estimated total posts.
- Estimated duration.

### Creator Detail Screen Refresh

Route:

```text
/creators/[creatorId]
```

Updated to match the newer Figma direction:

- Header with profile image or initials, creator name, headline, status, run
  scraping action, and LinkedIn action.
- Creator Information card with headline, about, location, URL, and experience.
- Creator Information now uses a cleaner Figma-style split layout:
  - headline and about text on the left
  - full name, location, and LinkedIn URL facts on the right
  - compact experience rows with icon, title, company, period, and location
  - profile image shown as a square thumbnail with an active-status dot
- Experience rows are not capped in the creator detail UI; all parsed saved
  experience entries are shown.
- The creators list uses saved profile-details data when available, including
  scraped profile images and scraped headlines.
- Posts-found card for last 24 hours using the creator `new_count` field.
- Quick actions card.
- Scrape history section remains visible, but uses saved recent posts because
  scrape-run history does not exist yet.

### Creator Add And Bulk Import Profile Scraping

Single creator add:

- Calls `POST /creators`.
- Then calls `POST /creators/profile-details/scrape` for that creator.
- Keeps the drawer loading until profile scraping finishes.
- Closes on success and shows a centered green success message.
- Keeps the drawer open and shows an error if add or profile scraping fails.

Bulk creator import:

- File upload still calls `POST /creators/import/preview`.
- Preview shows corrected URLs, new URLs, in-database URLs, duplicates, and
  errors without saving anything.
- `Import Creators` is disabled when the preview has zero new URLs.
- Import calls `POST /creators/import`.
- Then calls `POST /creators/profile-details/scrape` for newly added creators.
- Keeps the drawer loading until profile scraping finishes.
- Closes on success and shows a centered green success message.
- Keeps the drawer open if import or profile scraping fails.

## Backend Gaps Tracked Separately

The frontend does not fake these features:

- Scrape job history.
- Scrape job progress timeline.
- Scraped post delete endpoint.
- Related posts read model.
- AI insight/analysis fields for scraped posts.
- Server-side scraped post pagination/search.

## 2026-07-13 Follow-up UI Adjustments

- Creators table now matches the newer Figma shape more closely:
  - three dashboard metrics only: total creators, new posts 24h, recently added
  - row selection remains available
  - actions column and grid/list toggle are removed
  - status filters are reduced to `All` and `Never Scraped`
  - `Sort by` control added with recently added, last checked, new posts, and name options
  - `Last Checked` header remains clickable for ascending/descending sort
- Creator rows and post cards use saved profile images when available.
- Bad scraped profile chrome such as `0 notifications` or `Skip to main content`
  is displayed as profile unavailable instead of as a creator name/headline.
- Bulk import preview shows only four counts: new URLs, duplicates, already in DB,
  and errors. Import stays disabled when there are zero new URLs.
- Posts & Scraping screen now shows only total scraped posts, new posts, and last
  scraping metrics. Top secondary actions, status filter, scrape category pills,
  creator-scraped metric, and post overflow menus are removed.
- Posts & Scraping time filter now includes 12h, 24h, 48h, 3 days, 4 days, and 7
  days. Filtering is client-side until the backend supports those windows.
