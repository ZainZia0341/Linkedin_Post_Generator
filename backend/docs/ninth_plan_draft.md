# Ninth Plan Draft - Stored Dashboard Stats In User Data

## Goal

Make the dashboard numbers come from the FastAPI response as explicit fields
instead of making Streamlit count returned lists during each page run.

The current top cards show:

- Creators
- Threads
- Activities
- Profile name

Today, `/users/{user_id}/data?limit=100` returns arrays and Streamlit calculates
the numbers with `len(...)`. That means the displayed numbers are tied to the
response limit and to whatever lists the page loaded. The API should instead
return a saved, explicit dashboard stats object for the active user.

## Current Problem

Current flow:

```text
Streamlit
  -> GET /users/{user_id}/data?limit=100
  -> receives creators[], threads[], recent_activities[]
  -> counts those arrays in Streamlit
```

Current issue:

- The API does not return `creator_count`, `thread_count`, or `activity_count`.
- Streamlit computes numbers at runtime with `len(...)`.
- If the API uses `limit=100`, the dashboard can only count the returned items.
- The card labels look like database totals, but they are currently page-level
  list counts.
- As data grows, loading full lists only to show counts becomes wasteful.

## Recommended Direction

Add a saved per-user dashboard stats object and return it from:

```text
GET /users/{user_id}/data
```

Recommended response addition:

```json
{
  "dashboard_stats": {
    "creator_count": 65,
    "thread_count": 7,
    "activity_count": 37,
    "commented_activity_count": 0,
    "last_scrape_checked_count": 65,
    "last_scrape_new_activity_count": 4,
    "last_scrape_error_count": 2,
    "last_scrape_at": "2026-07-08T00:00:00+00:00",
    "updated_at": "2026-07-08T00:00:00+00:00"
  }
}
```

Streamlit should display these explicit values instead of counting arrays.

The arrays should still be returned for tabs that need actual records, but the
dashboard numbers should come from `dashboard_stats`.

## Where To Save The Stats

Best fit: save `dashboard_stats` on the existing user record in:

```text
linkedin_post_generator_users
```

Reason:

- The stats are user-level summary data.
- The table is already keyed by `user_id`.
- The dashboard is always scoped to one active user.
- No separate lookup is needed when loading `/users/{user_id}/data`.
- No new table is required for this feature.

Do not save these counts on the creators table, because the counts summarize
multiple tables. Do not save them on the activities table, because thread and
creator counts do not belong there.

Optional future alternative:

```text
linkedin_post_generator_user_stats
```

Use a separate stats table only if the stats object becomes large, heavily
updated, or needs separate permissions/lifecycle later. For the current app, the
users table is cleaner.

## Stats Are A Cached Read Model

The saved stats should be treated as a cached read model, not the source of
truth.

Source-of-truth tables remain:

- `linkedin_post_generator_users`
- `linkedin_post_generator_creators`
- `linkedin_post_generator_threads`
- `linkedin_post_generator_activities`

The stats object is derived from those tables so the UI can read dashboard
numbers quickly and consistently.

## API Requirements

### Update User Data Response

Extend `UserDataResponse` with:

```text
dashboard_stats
```

The endpoint:

```text
GET /users/{user_id}/data?limit=100
```

should return:

- `user`
- `dashboard_stats`
- `creators`
- `threads`
- `recent_activities`

Rules:

- If `dashboard_stats` exists on the user record, return it.
- If it is missing, rebuild it from the database, save it on the user record,
  then return it.
- The numbers in `dashboard_stats` should not depend on the `limit` query param.
- The returned arrays can still respect `limit`.

### Optional Stats-Only Endpoint

Add only if useful for debugging/admin UI:

```text
GET /users/{user_id}/dashboard-stats
```

Rules:

- Return only the saved dashboard stats.
- Do not return creators, threads, or activities.
- If missing, rebuild and save before returning.

### Optional Rebuild Endpoint

Add a manual repair endpoint:

```text
POST /users/{user_id}/dashboard-stats/rebuild
```

Rules:

- Recount from source-of-truth tables.
- Save the rebuilt stats to the user record.
- Return the rebuilt stats.

This helps if old data exists before the feature or if counts drift during
development.

## Database Save Shape

Add this field to each user item:

```json
{
  "user_id": "test-user-1",
  "profile": {},
  "writing_style": {},
  "dashboard_stats": {
    "creator_count": 65,
    "thread_count": 7,
    "activity_count": 37,
    "commented_activity_count": 0,
    "last_scrape_checked_count": 65,
    "last_scrape_new_activity_count": 4,
    "last_scrape_error_count": 2,
    "last_scrape_at": "2026-07-08T00:00:00+00:00",
    "updated_at": "2026-07-08T00:00:00+00:00"
  }
}
```

Implementation note for later coding:

- Prefer a repository method that updates only `dashboard_stats` on the user row.
- Avoid rewriting the entire user item from stale data.
- Keep the user profile and writing style untouched when stats update.

## Stat Definitions

### `creator_count`

Number of tracked creators for the user.

Source of truth:

```text
creators table where user_id = selected user
```

### `thread_count`

Number of generated post threads for the user.

Source of truth:

```text
threads table where user_id = selected user
```

### `activity_count`

Number of saved creator activity/post records visible for the user's currently
tracked creators.

Source of truth:

```text
activities table for each current creator:
user_creator_id = "{user_id}#{creator_id}"
```

Important note:

- Current activity listing walks the current creator list.
- If a creator is deleted, old activities for that creator may still exist in
  the table, but they are no longer visible through current user activity lists.
- The dashboard `activity_count` should match visible saved activities, not
  orphaned activity rows.

### `commented_activity_count`

Number of saved activities where engagement/comment state says the user has
commented.

This is useful later for a dashboard card, filter, or progress indicator.

### Last Scrape Fields

Useful optional fields:

- `last_scrape_checked_count`
- `last_scrape_new_activity_count`
- `last_scrape_error_count`
- `last_scrape_at`

These are not permanent totals. They describe the most recent scrape run.

## DB Update Rules

### Create User

When a user is created:

- Save `dashboard_stats` with all numeric counts set to `0`.
- Set `updated_at`.

### Add Single Creator

When `POST /creators` creates a new creator:

- Increment `creator_count` by `1`.
- Update `dashboard_stats.updated_at`.

If the creator already exists and the endpoint returns the existing record:

- Do not increment.

### Bulk Import Creators

When `POST /creators/import` adds creators:

- Increment `creator_count` by the number of actually added creators.
- Do not count skipped existing creators.
- Do not count duplicate rows inside the uploaded file.
- Update `dashboard_stats.updated_at`.

### Delete Creator

When a creator is deleted:

- Decrement `creator_count` by `1`.
- Count currently saved activities for that creator before deletion.
- Subtract those visible activities from `activity_count`.
- Subtract commented activities for that creator from `commented_activity_count`.
- Update `dashboard_stats.updated_at`.

Do not physically delete old activity rows unless a later feature explicitly
changes creator deletion behavior.

### Generate New Thread

When `POST /posts/generate` creates a new thread:

- Increment `thread_count` by `1`.
- Update `dashboard_stats.updated_at`.

### Generate From Creator Activity

When `POST /posts/from-creator-activity` creates a new thread:

- Increment `thread_count` by `1`.
- Update `dashboard_stats.updated_at`.

### Modify Thread

When an existing thread is modified:

- Do not change `thread_count`.
- Optionally update a separate `last_thread_updated_at` later if needed.

### Delete Thread

When a thread is deleted:

- Decrement `thread_count` by `1`.
- Update `dashboard_stats.updated_at`.

### Normal Creator Scrape

When `POST /creators/scrape` saves new activities:

- Increment `activity_count` by the number of newly inserted activities.
- Do not increment for posts that already existed.
- Save last scrape fields:
  - checked creator count
  - new activity count
  - error count
  - scrape timestamp
- Update `dashboard_stats.updated_at`.

### 24-Hour Creator Scrape

When `POST /creators/scrape/recent-24h` saves activities:

- Increment `activity_count` only for newly inserted activities.
- Do not increment when an existing activity is updated.
- Preserve existing engagement/comment data when updating existing activities.
- Save last scrape fields for the run.
- Update `dashboard_stats.updated_at`.

Do not store `recent_24h_count` as a permanent dashboard total unless the label
is clearly "last 24h scrape returned". A true rolling 24-hour count becomes stale
as time passes even when no DB write happens.

### Generate Or Mark Comment

When a comment is generated or an activity is marked commented:

- If the activity was previously not commented and becomes commented, increment
  `commented_activity_count` by `1`.
- If the activity was commented and becomes not commented, decrement it by `1`.
- If the state does not change, do not change the count.
- Update `dashboard_stats.updated_at`.

## Rebuild Logic

Add a service helper:

```text
rebuild_user_dashboard_stats(repo, user_id)
```

It should:

1. Check the user exists.
2. Count creators for the user.
3. Count threads for the user.
4. Count visible activities by walking the user's current creators.
5. Count commented visible activities.
6. Save the rebuilt stats to the user record.
7. Return the stats.

Current table design does not have a direct user-level activity key or GSI for
all activities by `user_id`. Because of that, activity counting needs to walk the
creator list and query activities by `user_creator_id`.

That is acceptable for the current local app. If activity volume grows, add a
GSI on `user_id` to the activities table in a later migration.

## Consistency Strategy

Use two paths:

1. Event updates for normal app actions.
2. Rebuild from source-of-truth tables when stats are missing or suspected stale.

Event updates are fast:

- Add creator: +1 creator.
- Add thread: +1 thread.
- Save new activity: +N activities.

Rebuild is safe:

- It corrects drift from old data, failed development runs, or manual DB edits.
- It should be available through an internal service function and optional API.

For scrape endpoints, prefer calculating the new activity total during the scrape
and updating dashboard stats once at the end of the endpoint. This avoids many
small writes during a long scrape.

## Streamlit Requirements

Update the dashboard cards to use:

```text
user_data["dashboard_stats"]["creator_count"]
user_data["dashboard_stats"]["thread_count"]
user_data["dashboard_stats"]["activity_count"]
```

Do not use:

```text
len(user_data["creators"])
len(user_data["threads"])
len(user_data["recent_activities"])
```

Fallback rule:

- If `dashboard_stats` is missing because the backend has not been updated yet,
  temporarily fall back to `len(...)`.
- After the API feature is complete, the normal path should always use
  `dashboard_stats`.

## Tests To Add Later

### API Response Tests

- `/users/{user_id}/data` includes `dashboard_stats`.
- Dashboard stats do not change when `limit` changes.
- Missing stats are rebuilt and saved.

### Creator Tests

- Adding a new creator increments `creator_count`.
- Adding an existing creator does not increment.
- Bulk import increments only for added creators.
- Deleting a creator decrements creator count and subtracts visible activities.

### Thread Tests

- Generating a post increments `thread_count`.
- Generating from activity increments `thread_count`.
- Modifying a thread does not increment.
- Deleting a thread decrements.

### Activity Tests

- Scrape increments `activity_count` only for new activities.
- 24-hour scrape updating existing activities does not increment.
- Repeated scrape of the same posts does not inflate counts.
- Comment generation/marking updates `commented_activity_count` only on state
  transitions.

### Rebuild Tests

- Rebuild returns exact counts from source tables.
- Rebuild fixes intentionally wrong saved stats.
- Rebuild handles users with no creators, no threads, and no activities.

## Acceptance Criteria

- The dashboard cards use explicit numbers returned by the API.
- The numbers are saved in DynamoDB under the user item.
- The numbers are independent of `/users/{user_id}/data?limit=...`.
- User profile and writing style updates do not overwrite stats.
- Stats update when creators, threads, activities, or comment state changes.
- A rebuild path exists for old data and development repair.
- No new database table is required for the first implementation.
