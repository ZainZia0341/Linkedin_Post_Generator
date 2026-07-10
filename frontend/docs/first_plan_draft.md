# First Frontend Plan Draft - Next.js Dashboard And Generate Flow

## Goal

Build the new product frontend in `frontend/` with Next.js, using the Figma
dashboard direction as the first screen.

The old Streamlit UI remains in `backend/streamlit_ui` for now, but the Next.js
frontend becomes the real user interface.

## Figma Access Note

The provided Figma node links are valid node-specific links:

- `21:220`
- `21:732`
- `21:2`
- `21:560`

The Figma tool could not read the file because the connected integration does
not have edit access. The current frontend pass is based on the screenshot and
the visible layout direction. Exact Figma metadata, screenshots, component
names, spacing, and colors should be re-read after the file is shared with edit
access.

Additional creator-management screenshots were provided after the first pass.
Those screenshots are the current visual reference for the creators list,
creator detail, add-creator drawer, and bulk-import modal.

## First Screen: Dashboard

Primary dashboard route:

```text
/dashboard
```

The dashboard should show:

- Greeting with the user's name, for example `Good Morning, Muhammad`.
- Main actions:
  - `Brainstorm Ideas`
  - `Generate Post`
- Three top metrics:
  - `Creators Following`
  - `Threads Generated`
  - `New Posts Today`
- `Continue Working` section.
- `Latest Creator Activity` section.
- Left sidebar with navigation and recent app history.

Do not show separate `Posts Generated` and `Active Threads` cards. In this app,
generated posts and threads are the same concept. Use one metric called
`Threads Generated` or `Posts Generated`, not both.

## Dashboard Data Mapping

Use the backend user data endpoint as the main dashboard source:

```text
GET /users/{user_id}/data
```

The dashboard now relies on explicit backend stats from:

```json
{
  "dashboard_stats": {
    "creator_count": 41,
    "thread_count": 32,
    "new_posts_today_count": 18,
    "new_posts_from_last_scrape_count": 9,
    "needs_scraping_count": 1,
    "recently_added_count": 7
  }
}
```

Current implementation:

- `Creators Following`: `dashboard_stats.creator_count`.
- `Threads Generated`: `dashboard_stats.thread_count`.
- `New Posts Today`: `dashboard_stats.new_posts_today_count`.

If the scraper has not run for the current 24-hour window, show a `Run scraper`
empty state instead of showing a misleading zero.

## Continue Working

Keep the section in the UI now, even if drafts are not fully modeled yet.

Initial version:

- Show the last two generated threads as resumable work.
- Use existing thread history data first if possible.
- Empty state text should be short and product-like, for example:
  `No drafts yet`.

Backend option to review later:

```text
GET /users/{user_id}/threads?limit=2
```

This existing endpoint may be enough for version one. If the frontend needs a
more draft-specific shape later, add:

```text
GET /users/{user_id}/drafts?limit=2
```

Draft response idea:

```json
{
  "items": [
    {
      "thread_id": "thread-id",
      "title": "AI Agents for SaaS",
      "summary": "A post explaining how AI agents are transforming SaaS",
      "updated_at": "2026-07-09T00:00:00+00:00",
      "status": "draft"
    }
  ]
}
```

## Latest Creator Activity

Show three latest saved creator activities from the current 24-hour window.

Backend source:

```text
GET /users/{user_id}/activities/recent-24h?limit=3&window_hours=24
```

Rules:

- Do not run the scraper just to render the dashboard.
- If saved recent activity exists, show up to three cards.
- If none exists, show a `Run scraper` action.
- `Manage creators` should navigate to the future creators screen.

## Sidebar

Initial sidebar items:

- Dashboard
- Generate
- Brainstorm
- Creators
- Activity Feed
- Engagement
- History
- Settings

Implemented routes:

- `/dashboard`
- `/generate`
- `/creators`
- `/creators/[creatorId]`

For version one, thread history can use:

```text
GET /users/{user_id}/threads?limit=100
```

Future app-history API idea:

```text
GET /users/{user_id}/app-history?limit=20
```

This endpoint would combine user actions such as generated posts, edited posts,
imported creators, scraper runs, and comments. Current backend data is spread
across threads, creators, activities, and engagement state, so app history should
be planned as a separate read model later.

Current frontend behavior:

- The sidebar shows thread history only because the backend already exposes
  thread history.
- The dashboard recent-activity panel stays as an empty API-needed state until a
  real app-history endpoint exists.
- No mock app-history events are rendered.

## Generate Post Screen

Route idea:

```text
/generate
```

Main inputs:

- Topic
- Post type/style
- Tone
- Post length
- Generate button

Post type options:

- Create posts from scratch
- Create a post about a topic
- Create a controversial post about a topic
- Create a top mistakes post about a topic
- Create a daily routine post about a topic
- Create a how to start post about a topic
- Create a motivational post about a topic
- Create a skills to become successful post about a topic
- Create a do's and don'ts post about a topic

Tone options:

- Professional
- Conversational
- Founder voice
- Educational
- Bold
- Friendly

Length options:

- Short
- Medium
- Long

Backend change to plan:

Extend `POST /posts/generate` so the frontend can pass structured generation
controls:

```json
{
  "user_id": "test-user-1",
  "topic": "AI agents for SaaS",
  "post_type": "Create a post about a topic",
  "tone": "Professional",
  "length": "Medium",
  "provider": "groq",
  "model": "openai/gpt-oss-120b"
}
```

The backend should translate `post_type`, `tone`, and `length` into prompt
instructions before generation.

Current frontend behavior:

- Post type options are loaded from `GET /post-generation-styles`.
- Tone and length controls are displayed, then folded into the existing `idea`
  text because the backend does not yet accept structured tone/length fields.
- If post type options cannot be loaded from the API, generation is disabled
  instead of using local mock options.

## Refine With AI

The generated post screen should support refining a generated thread.

Backend source:

```text
POST /posts/modify
```

Preset refinement buttons:

- Make shorter
- Add stronger hook
- Rewrite for founders
- Add bullet points

Also include a free text instruction input.

Request idea:

```json
{
  "user_id": "test-user-1",
  "thread_id": "thread-id",
  "instruction": "Make shorter and add a stronger hook."
}
```

## Creator Management Screen

Route:

```text
/creators
```

Implemented with existing backend APIs only:

- Loads user data through `GET /users/{user_id}/data?limit=1000`.
- Displays top metrics:
  - total creators from `dashboard_stats.creator_count`
  - new posts from last scrape from
    `dashboard_stats.new_posts_from_last_scrape_count`
  - needs scraping from `dashboard_stats.needs_scraping_count`
  - recently added from `dashboard_stats.recently_added_count`
- Displays a searchable/filterable creators table.
- Uses `POST /creators` for single creator add.
- Uses `POST /creators/import` for bulk file import.

Features intentionally not faked:

- Profile validation preview before saving.
- Follower/reach/posts-per-week metrics.
- Server-side pagination.
- Bulk-selected scrape/tag/remove action bar.

Those need backend support before the UI should render real data for them.

## Add Creator Drawer

Implemented:

- Right-side drawer.
- Single creator URL input.
- Calls `POST /creators`.
- Closes on successful add and shows a centered green success message for two
  seconds.
- Keeps the drawer open and shows the API error if the add fails.
- Shows an API-needed note instead of fake live preview data.

Not implemented yet:

- `Validate Creator` preflight action.
- Live preview card with name, headline, avatar, follower count, and readiness.

Needed backend endpoint:

```text
POST /creators/validate
```

## Bulk Import Drawer

Implemented:

- Opens as a right-side drawer from the main `Import Creators` button.
- File picker for `.csv`, `.txt`, and `.xlsx`.
- Calls `POST /creators/import/preview` when a file is selected.
- Preview shows corrected URL count, new URL count, already-in-database count,
  duplicate-in-file count, and invalid/error count without saving anything to
  the database.
- Preview shows new URLs, already-in-database rows, corrected URLs, duplicate
  rows, and error rows.
- Calls existing `POST /creators/import` multipart endpoint only when the user
  clicks `Import Creators`.
- Shows added/skipped/duplicate/error counts from the real response.
- Shows URLs already in the database as skipped rows.
- Shows duplicate URLs from the uploaded file.
- Shows returned row-level import errors.
- Saves valid new creators through the backend import endpoint.
- Closes on successful import and shows a centered green success message for two
  seconds.
- Keeps the drawer open and shows the error/result rows if the import fails or
  returns row-level errors.

Not implemented:

- Drag-and-drop progress percentage.

The backend now exposes a separate upload/preview step. It still does not expose
streaming progress or async import jobs.

## Creator Detail Screen

Route:

```text
/creators/[creatorId]
```

Implemented with existing backend APIs only:

- Loads creator from `GET /users/{user_id}/data`.
- Loads saved profile details from
  `GET /users/{user_id}/creators/{creator_id}/profile-details`.
- Shows saved profile image and location after profile-details scraping has run.
- Loads saved activity from
  `GET /users/{user_id}/creators/{creator_id}/activities`.
- Runs a one-creator scrape with `POST /creators/scrape/recent-24h`.
- Deletes a creator with `DELETE /users/{user_id}/creators/{creator_id}`.
- Opens and copies the saved LinkedIn URL.

Features intentionally shown as API-needed or empty:

- Next scrape time.
- Full scrape history table.
- Scrape status timeline.

These need backend read models before the UI should show them.

## Backend Features Needed For This Frontend

High priority:

- Scrape-window status field so the UI can tell the difference between "no new
  posts" and "scraper has not run for this 24-hour window."
- Saved 24-hour activity endpoint used by the dashboard with `limit=3`.
- Last two generated threads for `Continue Working`.
- Structured generation controls: `post_type`, `tone`, and `length`.
- Modify post endpoint wired to preset and custom instructions.
- App-history endpoint for the dashboard/right rail and future sidebar history.
- Creator validation endpoint for the add-creator preview drawer.
- Creator detail read model with follower metrics, scrape schedule/status, and
  scrape history.

Implemented backend support:

- Explicit dashboard/creator stats returned from `/users/{user_id}/data`.
- Profile-details scrape can save and return profile image URL and location.

Later:

- Proper drafts model if generated posts need draft/published states.
- App history read model for sidebar recent activity.
- Activity feed screen.
- Engagement/comment workflow screen.

## Open Questions

- Should `Threads Generated` be labeled `Posts Generated` in the final UI copy?
- Do drafts need a real status field, or are recent threads enough for the first
  frontend version?
- Should `New Posts Today` mean saved posts in the last 24 hours, or posts found
  during the latest scraper run?
- Should app history include only user actions, or also background scrape events?
