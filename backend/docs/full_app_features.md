# Full App Features And API Shapes

This file is for UI/UX design planning. It maps each app feature to the current
backend API shape and notes where the design idea needs either frontend
composition or new backend work.

## Quick Audit Of `app_features.md`

### You Did Not Miss Major Current Features

Your feature list covers the important app flows:

- LLM key test.
- User profile viewing/updating.
- Post generation.
- Post modification/chat-style revision.
- Brainstorming and generating from an idea.
- Thread/history management.
- Creator add, bulk import, list, and delete.
- Creator post scraping.
- 24-hour scrape and 24-hour saved DB view.
- Creator profile detail scraping.
- Activity list and generate post from creator activity.
- Comment generation and mark-as-commented flow.

### Extra Or Not Fully Backend-Backed Yet

These items in your notes are UI ideas, but the backend does not currently have
dedicated APIs exactly for them:

- "Show user name already selected from .env backend": backend seeds/list users,
  but there is no active-user-from-env endpoint. UI currently selects from
  `/users`.
- "Thread conversations shown in right sidebar": backend supports thread list and
  thread detail, but sidebar placement is only UI design.
- "Three-dot delete on each thread": backend supports delete; three-dot menu is
  UI design.
- "Copy option on brainstorm ideas": frontend-only feature; no API needed.
- "Generate post from brainstorm idea and user selects style": current Streamlit
  generates from an idea using a fixed style in that button flow. Backend
  supports selecting style through `/posts/generate`, so UI can implement this.
- "List all posts from all creators with pagination": backend has `limit`, but
  no cursor/page/offset pagination yet.
- "Show 5 posts each creator": no dedicated grouped endpoint. UI can group
  results client-side after calling creator/activity endpoints, or backend needs
  a grouped endpoint.
- "Comment section filters: all/commented/uncommented/24h": backend supports
  commented list and activity lists, but there is no dedicated uncommented or
  filtered comment queue endpoint yet.
- "24h scrape default to 1 post": backend default is currently `max_posts=5` and
  `window_hours=24`. UI may choose a default of 1, but API default is 5.
- "Web scraper creator list with name/headline together": backend returns creator
  list and profile details separately. UI can merge `/creators` with
  `/creators/profile-details`.

## Common Data Shapes

### User

```json
{
  "user_id": "test-user-1",
  "profile": {
    "full_name": "Mughees Khan",
    "headline": "Backend and AI Workflow Builder",
    "location": "Pakistan",
    "skills": ["Python", "FastAPI"],
    "industries": ["AI automation"],
    "experience_summary": "Builds practical AI tools."
  },
  "writing_style": {},
  "created_at": "2026-07-07T00:00:00+00:00",
  "updated_at": "2026-07-07T00:00:00+00:00"
}
```

### Thread

```json
{
  "user_id": "test-user-1",
  "thread_id": "uuid",
  "current_post": "Generated LinkedIn post...",
  "original_post": "First generated version...",
  "conversation": [{"role": "user", "content": "Make it shorter"}],
  "provider": "gemini",
  "model": "gemini-3.1-flash-lite",
  "topic": "AI agents",
  "topic_source": "manual",
  "generation_style": "Create a post about a topic",
  "source": {},
  "created_at": "2026-07-07T00:00:00+00:00",
  "updated_at": "2026-07-07T00:00:00+00:00",
  "generated_at": "2026-07-07T00:00:00+00:00",
  "modified_at": "",
  "modification_count": 0
}
```

### Creator

```json
{
  "user_id": "test-user-1",
  "creator_id": "txshep",
  "profile_url": "https://www.linkedin.com/in/txshep/",
  "display_name": "Ben Sheppard",
  "added_at": "2026-07-07T00:00:00+00:00",
  "updated_at": "2026-07-07T00:00:00+00:00",
  "last_checked_at": "2026-07-07T00:00:00+00:00",
  "seen_count": 10,
  "new_count": 2
}
```

### Creator Activity / Post

```json
{
  "user_id": "test-user-1",
  "creator_id": "txshep",
  "post_id": "urn:li:activity:123",
  "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:123/",
  "raw_text": "Creator post text...",
  "author_name": "Ben Sheppard",
  "posted_at_text": "2h",
  "fetched_at": "2026-07-07T00:00:00+00:00",
  "content_hash": "hash",
  "source": "playwright",
  "is_new": true,
  "engagement": {}
}
```

### Creator Profile Details

```json
{
  "user_id": "test-user-1",
  "creator_id": "txshep",
  "profile_url": "https://www.linkedin.com/in/txshep/",
  "name": "Ben Sheppard",
  "headline": "4x Founder | Fractional COO & Coach",
  "about": "About text...",
  "experience": ["Founder at Inside Startups..."],
  "fetched_at": "2026-07-07T00:00:00+00:00",
  "source": "playwright"
}
```

## Feature 1: App Health And API Docs

Use this for app status and developer testing.

### `GET /health`

Input: none.

Output:

```json
{
  "status": "ok"
}
```

### Built-In Docs

- `GET /docs`
- `GET /redoc`
- `GET /openapi.json`

UI need: usually not part of customer UI.

## Feature 2: LLM Provider And API Key Testing

UI idea: provider dropdown, model dropdown based on selected provider, API key
input, and "Test key" button.

### `GET /llms/providers`

Input: none.

Output:

```json
{
  "gemini": ["gemini-3.1-flash-lite", "gemini-3.5-flash"],
  "groq": ["openai/gpt-oss-120b"],
  "claude": ["claude-sonnet-4.6"]
}
```

### `POST /llms/test-key`

Input:

```json
{
  "provider": "groq",
  "model": "openai/gpt-oss-120b",
  "api_key": "secret-key"
}
```

Output:

```json
{
  "ok": true,
  "message": "API key works.",
  "provider": "groq",
  "model": "openai/gpt-oss-120b"
}
```

## Feature 3: User Profile Management

UI idea: show active user, show profile details, edit profile and writing style.
Create/list user can stay admin/backend-only if not needed in the main UI.

### `GET /users`

Query:

```text
limit=100
```

Output:

```json
[
  {
    "user_id": "test-user-1",
    "profile": {},
    "writing_style": {},
    "created_at": "...",
    "updated_at": "..."
  }
]
```

### `GET /users/{user_id}`

Output: `User`.

### `POST /users`

Input:

```json
{
  "user_id": "test-user-1",
  "profile": {
    "full_name": "Mughees Khan",
    "headline": "AI Workflow Builder",
    "skills": ["Python", "FastAPI"]
  },
  "writing_style": {
    "name": "Clear Builder"
  }
}
```

Output: `User`.

### `PATCH /users/{user_id}`

Input:

```json
{
  "profile": {
    "full_name": "Mughees Khan",
    "headline": "Backend and AI Workflow Builder",
    "location": "Pakistan",
    "skills": ["Python", "FastAPI", "Playwright"],
    "industries": ["AI automation"],
    "experience_summary": "Builds AI apps and scraping workflows."
  },
  "writing_style": {
    "name": "Clear Builder"
  }
}
```

Output: `User`.

### `GET /users/{user_id}/data`

Query:

```text
limit=100
```

Output:

```json
{
  "user": {},
  "creators": [],
  "threads": [],
  "recent_activities": []
}
```

## Feature 4: Post Generation

UI idea: text input for topic/idea, dropdown for post generation style, generate
button, generated post view.

### `GET /post-generation-styles`

Output:

```json
[
  "Create posts from scratch",
  "Create a post about a topic",
  "Create a controversial post about a topic",
  "Create a top mistakes post about a topic",
  "Create a daily routine post about a topic",
  "Create a how to start post about a topic",
  "Create a motivational post about a topic",
  "Create a skills to become successful post about a topic",
  "Create a do's and don'ts post about a topic"
]
```

### `POST /posts/generate`

Input:

```json
{
  "user_id": "test-user-1",
  "idea": "AI agents for small businesses",
  "generation_style": "Create a post about a topic",
  "topic_source": "manual"
}
```

Output: `Thread`.

## Feature 5: Modify Generated Post

UI idea: chat-style message box after a post is generated, where user asks for
changes.

### `POST /posts/modify`

Input:

```json
{
  "user_id": "test-user-1",
  "thread_id": "uuid-from-generation",
  "modification_message": "Make it shorter and add a stronger hook."
}
```

Output: updated `Thread`.

## Feature 6: Brainstorming / Research Ideas

UI idea: topic input, action/research style dropdown, "Do research" button,
ideas list, copy option, generate-from-idea button.

### `GET /actions`

Output includes:

```json
[
  "Find audience pain points",
  "Find common mistakes around my topic",
  "Find common misconceptions people have about a topic",
  "Brainstorm post topics",
  "Brainstorm book recommendation about a topic",
  "Brainstorm documentary recommendations about a topic",
  "Brainstorm useful tools about a topic"
]
```

### `POST /ideas/brainstorm`

Input:

```json
{
  "user_id": "test-user-1",
  "topic": "AI agents for small teams",
  "action": "Find audience pain points"
}
```

Output:

```json
{
  "user_id": "test-user-1",
  "action": "Find audience pain points",
  "topic": "AI agents for small teams",
  "ideas": [
    {
      "title": "Idea title",
      "summary": "Short summary",
      "post_angle": "Suggested angle",
      "source_url": "https://example.com"
    }
  ],
  "research_suggestions": ["More research idea"],
  "provider": "gemini",
  "model": "gemini-3.1-flash-lite"
}
```

Generate from idea uses `POST /posts/generate` with:

```json
{
  "user_id": "test-user-1",
  "idea": "Selected idea text",
  "generation_style": "Create a post about a topic",
  "topic_source": "brainstorm"
}
```

## Feature 7: Thread / Chat History

UI idea: right sidebar chat/thread list, click to open, three-dot delete.

### `GET /users/{user_id}/threads`

Query:

```text
limit=100
```

Output:

```json
[
  {
    "thread_id": "uuid",
    "topic": "AI agents",
    "topic_source": "manual",
    "generation_style": "Create a post about a topic",
    "created_at": "...",
    "updated_at": "..."
  }
]
```

### `GET /users/{user_id}/threads/{thread_id}`

Output: full `Thread`.

### `DELETE /users/{user_id}/threads/{thread_id}`

Output:

```json
{
  "ok": true,
  "message": "Deleted thread uuid."
}
```

## Feature 8: Creator Management

UI idea: add one LinkedIn URL, upload sheet for many creators, show added,
duplicates, existing, and errors, list creators, delete creator.

### `POST /creators`

Input:

```json
{
  "user_id": "test-user-1",
  "profile_url": "https://www.linkedin.com/in/txshep/"
}
```

Output: `Creator`.

Duplicate behavior: returns existing creator unchanged.

### `POST /creators/import`

Input: multipart form data.

```text
user_id: test-user-1
file: creators.csv | creators.xlsx | creators.txt
```

Output:

```json
{
  "user_id": "test-user-1",
  "total_urls": 100,
  "added_creators": [],
  "skipped_existing_creator_ids": ["txshep"],
  "skipped_duplicate_creator_ids": ["same-file-duplicate"],
  "errors": [
    {
      "row": "12",
      "url": "bad-url",
      "message": "Only LinkedIn profile URLs can be tracked."
    }
  ]
}
```

### `GET /users/{user_id}/creators`

Query:

```text
limit=100
```

Output: list of `Creator`.

### `DELETE /users/{user_id}/creators/{creator_id}`

Output:

```json
{
  "ok": true,
  "message": "Deleted creator txshep."
}
```

## Feature 9: Creator Profile Detail Scraping

UI idea: select one/many creators and scrape name, headline, about, experience.
Then show saved creator details.

### `POST /creators/profile-details/scrape`

Input:

```json
{
  "user_id": "test-user-1",
  "creator_ids": ["txshep"]
}
```

If `creator_ids` is `null` or missing, backend scrapes all added creators for
that user.

Output:

```json
{
  "user_id": "test-user-1",
  "checked_creator_ids": ["txshep"],
  "profiles": [
    {
      "user_id": "test-user-1",
      "creator_id": "txshep",
      "profile_url": "https://www.linkedin.com/in/txshep/",
      "name": "Ben Sheppard",
      "headline": "4x Founder | Fractional COO & Coach",
      "about": "About text...",
      "experience": ["Experience text..."],
      "fetched_at": "...",
      "source": "playwright"
    }
  ],
  "errors": []
}
```

### `GET /users/{user_id}/creators/profile-details`

Query:

```text
limit=100
```

Output: list of `CreatorProfileDetails`.

### `GET /users/{user_id}/creators/{creator_id}/profile-details`

Output: one `CreatorProfileDetails`.

## Feature 10: Creator Post Scraping

UI idea: show creators with checkboxes, select all, choose number of posts, run
scrape, show count and returned posts.

### `POST /creators/scrape`

Input:

```json
{
  "user_id": "test-user-1",
  "creator_ids": ["txshep"],
  "max_posts": 5
}
```

Output:

```json
{
  "user_id": "test-user-1",
  "checked_creator_ids": ["txshep"],
  "new_activities": [],
  "errors": []
}
```

Important behavior: returns only posts not already saved in DB.

## Feature 11: 24-Hour Creator Post Scraping

UI idea: select creators, choose number of visible posts to inspect, choose time
window, run scraper, show only posts inside the time window.

### `POST /creators/scrape/recent-24h`

Input:

```json
{
  "user_id": "test-user-1",
  "creator_ids": ["txshep"],
  "max_posts": 5,
  "window_hours": 24
}
```

Output:

```json
{
  "user_id": "test-user-1",
  "checked_creator_ids": ["txshep"],
  "window_hours": 24,
  "activities": [],
  "errors": []
}
```

Important behavior:

- Returns recent posts even if already saved before.
- Saves/updates the matching activities in DB.
- Current backend default is `max_posts=5`, not 1.

## Feature 12: Saved Creator Activities / Posts From DB

UI idea: see all saved posts from creators, open one, generate post from it.

### `GET /users/{user_id}/activities`

Query:

```text
limit=100
```

Output: list of `Activity`.

### `GET /users/{user_id}/creators/{creator_id}/activities`

Query:

```text
limit=100
```

Output: list of `Activity` for one creator.

### `GET /users/{user_id}/activities/recent-24h`

Query:

```text
limit=100
window_hours=24
```

Output:

```json
{
  "user_id": "test-user-1",
  "window_hours": 24,
  "activities": []
}
```

Important behavior: reads saved DB activities only. It does not run Playwright.
It estimates current recency from `fetched_at - posted_at_text`.

## Feature 13: Generate Post From Creator Activity

UI idea: "Use this creator post to create a post for me".

### `POST /posts/from-creator-activity`

Input:

```json
{
  "user_id": "test-user-1",
  "creator_id": "txshep",
  "post_id": "urn:li:activity:123"
}
```

Output: new `Thread`.

Note: backend currently chooses its own generation style for this endpoint. If UI
needs a style dropdown here, backend should be extended or UI should call
`/posts/generate` with copied creator-post text.

## Feature 14: Comment Generation And Engagement Tracking

UI idea: show creator posts, choose comment angle, generate comment, mark as
commented, view commented history.

### `GET /comments/topics`

Output:

```json
[
  "Add Value",
  "Congratulate",
  "Agree",
  "Disagree",
  "Challenge",
  "Expert Insight"
]
```

### `POST /comments/generate`

Input:

```json
{
  "user_id": "test-user-1",
  "creator_id": "txshep",
  "post_id": "urn:li:activity:123",
  "comment_topic": "Expert Insight"
}
```

Output:

```json
{
  "user_id": "test-user-1",
  "creator_id": "txshep",
  "post_id": "urn:li:activity:123",
  "comment_topic": "Expert Insight",
  "comment": "Generated comment text...",
  "provider": "gemini",
  "model": "gemini-3.1-flash-lite",
  "generated_at": "...",
  "commented": false
}
```

### `PATCH /comments/mark`

Input:

```json
{
  "user_id": "test-user-1",
  "creator_id": "txshep",
  "post_id": "urn:li:activity:123",
  "commented": true,
  "comment_text": "Final posted comment text"
}
```

Output: `CommentResponse`.

### `GET /users/{user_id}/engagements/comments`

Query:

```text
limit=50
```

Output: list of commented activities:

```json
[
  {
    "user_id": "test-user-1",
    "creator_id": "txshep",
    "post_id": "urn:li:activity:123",
    "raw_text": "Creator post...",
    "comment_topic": "Expert Insight",
    "comment": "Final comment...",
    "commented_at": "2026-07-07T00:00:00+00:00"
  }
]
```

Missing for your desired UI filters:

- No dedicated "uncommented posts" endpoint.
- No dedicated "comment queue by creator with 5 posts each" endpoint.
- No dedicated query params for comment status on `/activities`.

These can be implemented in frontend from activity lists, or added as a new
backend endpoint later.

## Suggested UI Sections

### Sidebar / Global

- API status.
- Active user selector.
- Provider/model/key test.
- Thread list and delete menu.

### Main App Tabs / Pages

- Generate Post.
- Modify Post.
- Brainstorm Ideas.
- Creator Management.
- Bulk Creator Import.
- Creator Profile Scrape.
- Creator Details.
- Creator Post Scrape.
- 24-Hour Scrape.
- Saved Recent Posts.
- All Saved Activity.
- Comment Engagement.
- User Profile.
- History.

## Backend Gaps To Consider Later

These are useful additions if the UI design needs them:

- Active/default user endpoint from env/config.
- Cursor or page/offset pagination for activity, creator, and thread lists.
- Grouped activity endpoint: N posts per creator.
- Comment queue endpoint with filters:
  - all
  - commented
  - uncommented
  - current 24 hours
  - by creator
- Let `/posts/from-creator-activity` accept `generation_style`.
- Add a reachout-message generation endpoint using creator profile details.
