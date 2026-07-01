# Third Plan Draft: Playwright Creator Tracking and Persistent User Profile

## 0. Goal

This draft upgrades the current LinkedIn Post Generator so it can use a tracked creator's latest LinkedIn post as the topic seed for your own generated post.

The strategy for this draft is Playwright automation, not the LinkedIn API.

The app will:

- Let you track a LinkedIn creator profile URL.
- Use a safe default testing profile when no URL is provided:
  `https://www.linkedin.com/in/theburningmonk/`
- Check that creator's recent LinkedIn activity with Playwright.
- Store posts already seen from that creator.
- Store posts already used as source topics, so the same creator post never appears again as an unused topic.
- Generate a new LinkedIn post in your own writing style based on the tracked creator post topic.
- Persist your writing style and resume/profile data across new chats.

This is still a local prototype plan. It is designed for your current Streamlit app, current local JSON database, and current LangGraph post generation workflow.

## 1. Important Safety Rule

Your personal LinkedIn account must not be used for any automation in this draft.

The Playwright scraper must never:

- Connect to your normal Chrome, Edge, or browser profile.
- Reuse personal LinkedIn cookies.
- Ask you to paste personal LinkedIn session cookies.
- Like, comment, repost, follow, message, publish, or perform any account action.
- Auto-post generated content back to LinkedIn.

The Playwright automation is read-only. It only opens tracked creator pages, reads recent post text where visible, and closes.

For testing, use one of these modes:

1. `logged_out` mode:
   - No LinkedIn account is used.
   - Lowest account risk.
   - Least reliable because LinkedIn often hides posts behind a login wall.

2. `burner` mode:
   - Uses a new throwaway LinkedIn account created only for testing.
   - More reliable for reading recent posts.
   - Still may be rate-limited or flagged by LinkedIn.
   - Must not be your personal account.

The app should default to `logged_out` mode unless burner credentials are explicitly provided in `.env`.

## 2. API Decision

For this draft, do not use the LinkedIn API.

Reason:

- The official LinkedIn API does not provide a normal free endpoint for reading arbitrary third-party creator posts.
- Useful LinkedIn data APIs are approval-gated and not realistic for this prototype.
- This draft is testing feasibility using Playwright-controlled browser automation instead.

Important limitation:

Playwright automation against LinkedIn can violate LinkedIn's terms and can break when LinkedIn changes its UI. This plan reduces personal account risk by isolating the browser profile and avoiding all personal-account activity, but it does not make scraping officially supported.

## 3. Current App Baseline

The current app already has these useful pieces:

- Streamlit UI in `streamlit_ui/app.py`
- Local JSON storage in `app/storage.py`
- Local DB root in `schema/local_db`
- Provider and model config in `app/config.py`
- Writing style extraction in `app/writing_style_extract.py`
- Resume/profile extraction in `app/extract_resume_details.py`
- Topic-to-post generation graph in `app/graph_state.py`
- Post editing graph with guardrails in `app/graph_state.py`
- Deep research flow in `app/langchain_deep_search.py`

This draft should extend those pieces instead of replacing the app.

## 4. New User Flow

### 4.1 First App Start

When the app starts:

1. Load `schema/local_db/user_profile.json`.
2. If it does not exist, keep the existing writing style and resume setup flow.
3. If it exists, skip repeated writing style and resume setup for new chats.
4. Load tracked creator profiles from `schema/local_db/tracked_profiles/index.json`.
5. If no tracked profile exists, seed the default testing profile:
   `https://www.linkedin.com/in/theburningmonk/`

### 4.2 New Chat

When the user clicks "Start new chat":

1. Validate provider, model, and API key as the app already does.
2. Create a normal chat session.
3. Check the global saved user profile.
4. If writing style exists, do not ask for previous posts again.
5. If resume/profile data exists or was previously skipped, do not ask for resume again.
6. Send the user directly to the workflow choice screen.

The user can still edit saved style or resume data from the sidebar.

### 4.3 Tracking a Creator

In the sidebar, add a "Tracked Creators" section.

Controls:

- Text input: "LinkedIn profile URL"
- Default value or placeholder: `https://www.linkedin.com/in/theburningmonk/`
- Button: "Add creator"
- List/selectbox of tracked creators
- Button: "Check for new posts"
- Small stats:
  - Seen posts
  - Used posts
  - Unused posts
  - Last checked time

When no URL is entered and the user clicks "Add creator", the app adds the default testing URL.

### 4.4 Checking for New Posts

When the user clicks "Check for new posts":

1. Call the new Playwright scraper module.
2. Open a fully isolated Playwright browser context.
3. Use logged-out mode or burner mode.
4. Visit the tracked profile's recent activity page.
5. Extract recent post candidates.
6. Normalize each post into a stable local record.
7. Save only posts that are not already in `seen_posts`.
8. Do not show posts already listed in `used_post_ids`.

### 4.5 Generating From a Tracked Creator Post

The "Generate Post" screen gets two topic source options:

1. Manual topic
2. Tracked creator post

When "Tracked creator post" is selected:

1. User selects a tracked creator.
2. App shows unused source posts from that creator.
3. User clicks "Use this post as topic".
4. The selected creator post text becomes the seed topic.
5. The app loads saved writing style and resume/profile data from `user_profile.json`.
6. The existing LangGraph generation workflow runs.
7. The generated post opens in the existing post editor chat screen.
8. After successful generation, the source LinkedIn post ID is added to `used_post_ids`.

The generated post should not copy the creator's wording. It should use the creator post only as topic inspiration.

## 5. Data Model

### 5.1 Global User Profile

New file:

```text
schema/local_db/user_profile.json
```

Shape:

```json
{
  "writing_style": {
    "name": "Clear Builder",
    "summary": "Practical, concise, and lesson-driven.",
    "tone": "helpful, grounded, professional",
    "hooks": [],
    "sentence_patterns": [],
    "formatting_patterns": [],
    "vocabulary": [],
    "calls_to_action": [],
    "hashtags": [],
    "avoid": []
  },
  "writing_style_source": "previous_post",
  "writing_style_examples": [],
  "resume_profile": {
    "name": "",
    "current_role": "",
    "skills": [],
    "experience_highlights": [],
    "target_audience": "",
    "industry": ""
  },
  "resume_source": "pdf",
  "resume_skipped": false,
  "created_at": "2026-06-29T00:00:00+00:00",
  "updated_at": "2026-06-29T00:00:00+00:00"
}
```

Rules:

- `writing_style` is required before generation.
- `resume_profile` is optional.
- `resume_skipped: true` means the user intentionally skipped resume setup and should not be asked again on every new chat.
- New chats read this file instead of requiring the user to paste previous posts again.
- Existing per-session style and resume data can remain for old sessions, but new sessions should prefer `user_profile.json`.

### 5.2 Tracked Creator Index

New file:

```text
schema/local_db/tracked_profiles/index.json
```

Shape:

```json
{
  "profiles": [
    {
      "profile_id": "theburningmonk",
      "profile_url": "https://www.linkedin.com/in/theburningmonk/",
      "display_name": "theburningmonk",
      "added_at": "2026-06-29T00:00:00+00:00",
      "last_checked_at": null,
      "seen_count": 0,
      "used_count": 0,
      "unused_count": 0
    }
  ]
}
```

### 5.3 Per-Creator Post Store

New files:

```text
schema/local_db/tracked_profiles/{profile_id}.json
```

Shape:

```json
{
  "profile_id": "theburningmonk",
  "profile_url": "https://www.linkedin.com/in/theburningmonk/",
  "display_name": "theburningmonk",
  "added_at": "2026-06-29T00:00:00+00:00",
  "last_checked_at": "2026-06-29T00:00:00+00:00",
  "seen_posts": [
    {
      "post_id": "urn:li:activity:123456789",
      "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:123456789/",
      "raw_text": "Example creator post text...",
      "author_name": "Yan Cui",
      "posted_at_text": "2h",
      "fetched_at": "2026-06-29T00:00:00+00:00",
      "content_hash": "sha256-of-normalized-text",
      "source": "playwright"
    }
  ],
  "used_post_ids": [
    "urn:li:activity:123456789"
  ]
}
```

Deduplication rules:

- Prefer LinkedIn activity URNs when available.
- If no activity URN is found, use `content_hash`.
- A post is unused when it exists in `seen_posts` and its `post_id` is not in `used_post_ids`.
- Once a source post generates a draft successfully, add its ID to `used_post_ids`.

### 5.4 Session Additions

Existing session files may add source metadata:

```json
{
  "topic_source": "tracked_creator",
  "source_profile_id": "theburningmonk",
  "source_post_id": "urn:li:activity:123456789",
  "source_post_url": "https://www.linkedin.com/feed/update/urn:li:activity:123456789/",
  "source_post_text": "Creator post text used as topic seed..."
}
```

This makes it easy to know which generated post came from which creator post.

## 6. New Modules

### 6.1 `app/creator_tracking.py`

Purpose:

Manage tracked profile records and used post history.

Functions:

```python
def normalize_linkedin_profile_url(url: str) -> str:
    ...

def get_profile_id(profile_url: str) -> str:
    ...

def seed_default_profile_if_empty() -> None:
    ...

def add_tracked_profile(url: str | None) -> dict:
    ...

def list_tracked_profiles() -> list[dict]:
    ...

def load_tracked_profile(profile_id: str) -> dict:
    ...

def save_tracked_profile(profile: dict) -> dict:
    ...

def check_for_new_posts(profile_id: str) -> list[dict]:
    ...

def list_unused_posts(profile_id: str) -> list[dict]:
    ...

def mark_post_used(profile_id: str, post_id: str) -> None:
    ...
```

Implementation notes:

- Use existing JSON storage style from `app/storage.py`.
- Keep file writes simple and readable.
- Update index counts after each profile save.
- Print important workflow actions to console because the current project prefers `print()`.

### 6.2 `app/linkedin_playwright_scraper.py`

Purpose:

Use Playwright to read recent posts from one LinkedIn profile.

Main function:

```python
def fetch_recent_profile_posts(profile_url: str, max_posts: int = 5) -> list[dict]:
    ...
```

Returned post shape:

```python
{
    "post_id": "urn:li:activity:123456789",
    "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:123456789/",
    "raw_text": "Post text...",
    "author_name": "Creator name",
    "posted_at_text": "1d",
    "content_hash": "...",
    "source": "playwright",
}
```

Playwright strategy:

1. Build candidate activity URLs:
   - `{profile_url}/recent-activity/all/`
   - `{profile_url}/recent-activity/shares/`
   - base profile URL as fallback
2. Launch an isolated browser context.
3. If burner credentials exist, use a persistent burner browser profile.
4. If no burner credentials exist, use logged-out mode.
5. Navigate to the best activity URL.
6. Wait for the page to settle.
7. Scroll slowly once or twice to load recent posts.
8. Extract post containers.
9. Extract post text, post URL, and activity URN where available.
10. Return normalized post objects.

Important:

- Do not use the user's installed browser profile.
- Do not import cookies from any browser.
- Do not store personal LinkedIn credentials.
- Do not perform write actions on LinkedIn.

### 6.3 `app/user_profile.py`

Purpose:

Separate global writing style and resume/profile persistence from per-chat session state.

Functions:

```python
def load_user_profile() -> dict:
    ...

def save_user_profile(profile: dict) -> dict:
    ...

def has_saved_writing_style() -> bool:
    ...

def get_generation_profile() -> tuple[dict, dict]:
    ...

def update_writing_style(style: dict, source: str, examples: list[str] | None = None) -> dict:
    ...

def update_resume_profile(resume_profile: dict, source: str, skipped: bool = False) -> dict:
    ...
```

Implementation notes:

- Keep `user_profile.json` in `schema/local_db`.
- Use this global profile for all new chats.
- Existing sessions can continue to load old style/resume values if no global profile exists.

## 7. Config Changes

Add constants to `app/config.py`:

```python
USER_PROFILE_PATH = LOCAL_DB_DIR / "user_profile.json"
TRACKED_PROFILE_DIR = LOCAL_DB_DIR / "tracked_profiles"
TRACKED_PROFILE_INDEX_PATH = TRACKED_PROFILE_DIR / "index.json"

LINKEDIN_DEFAULT_TRACK_URL = os.getenv(
    "LINKEDIN_DEFAULT_TRACK_URL",
    "https://www.linkedin.com/in/theburningmonk/",
)

LINKEDIN_AUTOMATION_MODE = os.getenv("LINKEDIN_AUTOMATION_MODE", "logged_out")
LINKEDIN_BURNER_EMAIL = os.getenv("LINKEDIN_BURNER_EMAIL", "")
LINKEDIN_BURNER_PASSWORD = os.getenv("LINKEDIN_BURNER_PASSWORD", "")
LINKEDIN_HEADLESS = os.getenv("LINKEDIN_HEADLESS", "true").lower() == "true"
LINKEDIN_CHECK_MAX_POSTS = int(os.getenv("LINKEDIN_CHECK_MAX_POSTS", "5"))
LINKEDIN_BROWSER_PROFILE_DIR = LOCAL_DB_DIR / "playwright" / "linkedin_burner_profile"
```

Update `ensure_local_db()` so it creates:

```text
schema/local_db/sessions/
schema/local_db/tracked_profiles/
schema/local_db/playwright/
```

## 8. Environment Variables

Add to `example.env`:

```env
# LinkedIn creator tracking with Playwright
LINKEDIN_DEFAULT_TRACK_URL=https://www.linkedin.com/in/theburningmonk/
LINKEDIN_AUTOMATION_MODE=logged_out
LINKEDIN_HEADLESS=true
LINKEDIN_CHECK_MAX_POSTS=5

# Optional burner account only.
# Do not use your personal LinkedIn account here.
LINKEDIN_BURNER_EMAIL=
LINKEDIN_BURNER_PASSWORD=
```

Mode behavior:

- `LINKEDIN_AUTOMATION_MODE=logged_out`
  - No account login.
  - Best for safest testing.

- `LINKEDIN_AUTOMATION_MODE=burner`
  - Uses burner credentials only.
  - More reliable, but still risky for that burner account.
  - Must fail with a clear Streamlit error if credentials are missing.

## 9. Dependency Changes

Add Playwright:

```bash
uv add playwright
uv run playwright install chromium
```

No LinkedIn API package is needed for this draft.

## 10. Streamlit UI Changes

### 10.1 Sidebar: Saved User Profile

Add a sidebar expander named "Saved Profile".

Show:

- Writing style status:
  - "Saved" or "Not saved"
- Resume/profile status:
  - "Saved", "Skipped", or "Not saved"
- Buttons:
  - "Edit writing style"
  - "Edit resume/profile"
  - "Reset saved profile"

Editing can reuse the existing writing style and resume screens.

### 10.2 Sidebar: Tracked Creators

Add a sidebar expander named "Tracked Creators".

Controls:

- URL input.
- "Add creator" button.
- Selectbox of tracked creators.
- "Check for new posts" button.
- Counts for seen, used, and unused posts.
- Last checked timestamp.

If the tracked profile list is empty, automatically call `seed_default_profile_if_empty()`.

### 10.3 New Chat Behavior

Current behavior starts at:

```text
writing_style -> resume -> choose_mode
```

New behavior:

```text
if no saved writing style:
    writing_style -> save globally -> resume
elif no saved resume and resume was not skipped:
    resume -> save globally -> choose_mode
else:
    choose_mode
```

For generation, load style/resume from `user_profile.json`.

### 10.4 Choose Workflow Screen

Keep the current two cards:

1. Generate from topic
2. Research trending topics

Inside "Generate from topic", add topic source options:

- Manual topic
- Tracked creator post

This avoids adding a third main card and keeps the app flow simple.

### 10.5 Tracked Creator Topic Screen

When user chooses "Tracked creator post":

- Show selectbox of tracked creators.
- Show unused posts for selected creator.
- Each unused post card should show:
  - Short text preview.
  - Source URL if available.
  - Fetched time.
  - "Use this post as topic" button.

When clicked:

- Run the existing post generation graph.
- Save source post metadata into the session.
- Mark source post used only after generation succeeds.

## 11. LangGraph Changes

The graph does not need a major rewrite.

Current topic generation already accepts:

- `topic`
- `writing_style`
- `resume_profile`
- `messages`
- `provider`
- `model`
- `api_key`

For tracked creator generation:

- Set `topic` to a generated topic seed from the creator post.
- Include source post text in the user message.
- Add optional source fields to graph state if useful.

Suggested topic seed format:

```text
Creator source post:
{raw_text}

Task:
Write a new LinkedIn post inspired by the topic of this creator post.
Do not copy phrasing. Use my saved writing style and profile.
```

The final generated post should still be reviewed by the existing review node.

## 12. Storage Migration Plan

This draft should be additive.

Do not break existing sessions.

Migration behavior:

1. If `user_profile.json` exists, use it.
2. If it does not exist, keep using the old per-session setup prompts.
3. When the user saves writing style in a new session, write it to `user_profile.json`.
4. When the user saves resume/profile data or skips resume, write that decision to `user_profile.json`.
5. Existing old sessions can continue to contain `writing_style` and `resume_profile`.

Recommended new-session behavior:

- Store `writing_style_snapshot` and `resume_profile_snapshot` in the session only when generation starts.
- This preserves what was used for that generated post even if the global profile is edited later.

## 13. Playwright Implementation Details

### 13.1 Browser Context

Use:

```python
chromium.launch_persistent_context(
    user_data_dir=str(LINKEDIN_BROWSER_PROFILE_DIR),
    headless=LINKEDIN_HEADLESS,
    viewport={"width": 1365, "height": 900},
)
```

Only use this directory for the burner profile.

Do not use paths such as:

- Your real Chrome user data directory.
- Your real Edge user data directory.
- Any profile copied from a personal browser.

### 13.2 Login Logic

If mode is `burner`:

1. Open LinkedIn.
2. Check if already logged in.
3. If not logged in, navigate to login page.
4. Fill burner email and password from `.env`.
5. Submit.
6. If LinkedIn asks for CAPTCHA, phone verification, or 2FA, stop and show a clear message in Streamlit.

Do not try to bypass CAPTCHA or verification.

If mode is `logged_out`:

- Never submit login forms.
- Try to read public post data only.

### 13.3 Selectors

LinkedIn class names change often, so selectors should be layered.

Try multiple approaches:

- Links containing `/feed/update/`
- Elements containing `urn:li:activity`
- Feed update containers such as `div.feed-shared-update-v2`
- Visible post text containers such as `div.update-components-text`
- Fallback page text parsing if structured selectors fail

Extraction should be tolerant:

- If post URL exists but text is missing, skip.
- If text exists but post ID is missing, create a hash-based ID.
- If the page is blocked by login wall, return a clear error object.

### 13.4 Rate and Behavior

Keep activity low:

- Manual "Check for new posts" only.
- No background scheduler in this draft.
- Max 5 posts per check by default.
- Small random waits between page actions.
- One or two scrolls only.

This keeps the prototype simple and reduces automation noise.

## 14. File Structure After This Draft

Expected structure:

```text
app/
  config.py
  storage.py
  user_profile.py
  creator_tracking.py
  linkedin_playwright_scraper.py
  graph_state.py
  writing_style_extract.py
  extract_resume_details.py
  langchain_deep_search.py
  nodes/
  llms/

streamlit_ui/
  app.py

schema/
  local_db/
    user_profile.json
    sessions_index.json
    sessions/
      {session_id}.json
    tracked_profiles/
      index.json
      {profile_id}.json
    playwright/
      linkedin_burner_profile/

docs/
  first_plan_draft.md
  second_plan_draft.py
  third_plan_draft.md
```

## 15. Git Ignore Changes

Make sure generated local data and browser profiles are not committed.

Add or confirm:

```gitignore
schema/local_db/*.json
schema/local_db/sessions/
schema/local_db/tracked_profiles/
schema/local_db/playwright/
```

If you want to keep empty directories in git, add `.gitkeep` files carefully, but never commit actual scraped LinkedIn data, browser cookies, or burner account profile data.

## 16. Implementation Order

### Phase 1: Configuration and Persistence

Files:

- `app/config.py`
- `app/user_profile.py`
- `app/storage.py`
- `example.env`
- `.gitignore`

Work:

1. Add new config paths and LinkedIn env variables.
2. Add local DB folder creation.
3. Add global user profile read/write helpers.
4. Save writing style globally.
5. Save resume/profile or skip decision globally.
6. Make new chats reuse saved global profile data.

### Phase 2: Creator Tracking Storage

Files:

- `app/creator_tracking.py`
- `schema/local_db/tracked_profiles/`

Work:

1. Normalize LinkedIn profile URLs.
2. Generate stable `profile_id` values.
3. Seed default profile when none exist.
4. Add tracked creator records.
5. Store seen posts and used post IDs.
6. List unused posts.
7. Mark posts used after generation.

### Phase 3: Playwright Scraper

Files:

- `app/linkedin_playwright_scraper.py`
- `pyproject.toml`
- `uv.lock`

Work:

1. Add Playwright dependency.
2. Install Chromium browser.
3. Implement logged-out mode.
4. Implement burner mode with isolated persistent context.
5. Implement recent activity navigation.
6. Extract post text and activity IDs.
7. Return normalized post records.
8. Return clear user-facing errors for login walls, verification walls, empty results, and selector failures.

### Phase 4: Streamlit UI Integration

Files:

- `streamlit_ui/app.py`

Work:

1. Add saved profile status controls.
2. Add tracked creator sidebar controls.
3. Add "Check for new posts" action.
4. Show seen/used/unused counts.
5. Add tracked creator topic source to the generation screen.
6. Pass selected source post into existing graph generation.
7. Save source metadata into session.
8. Mark source post used after successful generation.

### Phase 5: Polish and Guardrails

Files:

- `app/linkedin_playwright_scraper.py`
- `app/creator_tracking.py`
- `streamlit_ui/app.py`

Work:

1. Add clear Streamlit messages for automation mode.
2. Show warning that personal accounts must not be used.
3. Make empty/blocked LinkedIn pages understandable.
4. Keep all LinkedIn automation read-only.
5. Keep all console visibility through `print()`.

## 17. Out of Scope for This Draft

Not included in this draft:

- Full admin dashboard.
- Background cron or automatic scheduled scraping.
- Auto-publishing to LinkedIn.
- Commenting, liking, reposting, following, or messaging.
- LinkedIn official API integration.
- Multi-user auth.
- MongoDB or DynamoDB migration.
- Browser-cookie import from personal browsers.

## 18. Main Risks

### LinkedIn Blocking

LinkedIn may show login walls, CAPTCHA, verification screens, or empty pages.

Handling:

- Stop gracefully.
- Show a clear message.
- Do not bypass CAPTCHA.
- Do not keep retrying aggressively.

### UI Selector Breakage

LinkedIn can change its DOM.

Handling:

- Keep selectors in one scraper module.
- Use several fallback extraction strategies.
- Return empty results with a clear message when extraction fails.

### Burner Account Flagging

Even a burner account can be limited or banned.

Handling:

- Use manual checks only.
- Keep max posts low.
- Use a persistent burner browser context.
- Do not automate actions.
- Never use the personal account.

### Data Sensitivity

Local browser profile data can contain burner account cookies.

Handling:

- Store only under `schema/local_db/playwright/`.
- Add it to `.gitignore`.
- Never commit it.

## 19. Final Target Experience

After this draft is implemented, the app should feel like this:

1. User opens Streamlit.
2. App already knows saved writing style and resume/profile details.
3. App has the default creator profile ready for testing.
4. User clicks "Check for new posts".
5. App uses Playwright to fetch recent creator posts.
6. User selects an unused creator post.
7. App generates a new LinkedIn post in the user's own style.
8. App opens the existing post editor chat.
9. The source creator post is marked used and will not be suggested again.

This keeps the current app's strongest parts while adding creator-based topic discovery through Playwright automation and persistent user profile reuse.
