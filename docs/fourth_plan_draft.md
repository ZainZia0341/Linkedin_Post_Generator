# Fourth Plan Draft: Playwright Creator Tracking with Manual Session Bootstrap

## 0. Goal

This draft is a revision of `third_plan_draft.md`. It keeps everything from that draft (tracked creator profiles, persistent user profile, Playwright-based scraping instead of the LinkedIn API) and fixes the one part that failed in testing: **automated login getting stuck on LinkedIn's login/verification wall**.

The fix is a change in approach, not a new feature:

- Do **not** attempt to automate the LinkedIn login form.
- Do **not** attempt to inject cookies obtained from any external "login API" or unofficial LinkedIn client.
- Instead, bootstrap the burner account's session **once, manually, by a human**, save it to a persistent browser profile directory, and have all future Playwright runs reuse that already-authenticated context headlessly.

Everything else in this draft (data model, modules, UI flow, LangGraph integration, file structure) is unchanged from the third draft. Only the login/session strategy changes.

## 1. Important Safety Rule (unchanged)

Your personal LinkedIn account must not be used for any automation in this draft.

The Playwright scraper must never:

- Connect to your normal Chrome, Edge, or browser profile.
- Reuse personal LinkedIn cookies.
- Ask you to paste personal LinkedIn session cookies.
- Like, comment, repost, follow, message, publish, or perform any account action.
- Auto-post generated content back to LinkedIn.

The Playwright automation is read-only. It only opens tracked creator pages, reads recent post text where visible, and closes.

Two modes remain available:

1. `logged_out` mode — no account used, lowest risk, least reliable (LinkedIn often hides posts behind a login wall).
2. `burner` mode — uses a throwaway LinkedIn account, more reliable, must never be the personal account.

The app defaults to `logged_out` mode unless a burner session has been bootstrapped (see Section 2).

## 2. What Changed From the Third Draft

### 2.1 Why automated login failed

In testing, scripting the login form (fill email, fill password, submit) repeatedly got stuck on LinkedIn challenge screens — CAPTCHA, "verify it's you" puzzles, phone/email verification, or "unusual activity" checks. This happens even with correct credentials because LinkedIn's challenge system is driven largely by fingerprint/behavioral signals (new device, new IP, headless-looking browser, no history on the account), not just credential validity. Scripting the login flow more aggressively, or retrying it, does not reliably get past this — it can make an account look more suspicious.

Feeding in a session token obtained from some other authenticated channel (e.g., an unofficial LinkedIn "login API") does not reliably fix this either, because the challenge is tied to the browser context's fingerprint, not just possession of a valid cookie. This approach is also more likely to be against LinkedIn's terms and is explicitly out of scope for this project.

### 2.2 The fix: manual bootstrap, automated reuse

Separate "logging in" from "scraping" into two different processes:

1. **Bootstrap (manual, done once, by a human, rarely repeated):** Launch a **headed** (visible) persistent Playwright browser context pointed at a dedicated burner profile directory. A human manually logs into the burner LinkedIn account in that window and solves any CAPTCHA/verification challenge normally, the way a real user would. Then the window is closed.
2. **Reuse (automated, headless, run as often as needed):** All later scraping runs launch that **same persistent profile directory**, headless. Because the context already contains a previously-validated, trusted session (cookies, local storage, and whatever trust signal LinkedIn attached to that manual login), Playwright can navigate straight to the target activity URL without ever seeing the login form.

This is not a bypass of LinkedIn's checks — it is doing the check once, honestly, as a human, and then not repeating the part that was breaking (the automated login attempt itself).

If the session eventually expires or LinkedIn re-challenges it (e.g., after a long idle period, IP change, or suspicious pattern), the fix is to re-run the manual bootstrap step by hand — not to script around the new challenge.

## 3. API Decision (unchanged)

Do not use the LinkedIn API. Do not use unofficial/reverse-engineered LinkedIn "login" or data APIs. Playwright automation against LinkedIn can violate LinkedIn's terms and can break when LinkedIn changes its UI; isolating the browser profile and never touching the personal account reduces personal-account risk but does not make scraping officially supported.

## 4. Current App Baseline (unchanged)

- Streamlit UI in `streamlit_ui/app.py`
- Local JSON storage in `app/storage.py`
- Local DB root in `schema/local_db`
- Provider and model config in `app/config.py`
- Writing style extraction in `app/writing_style_extract.py`
- Resume/profile extraction in `app/extract_resume_details.py`
- Topic-to-post generation graph in `app/graph_state.py`
- Post editing graph with guardrails in `app/graph_state.py`
- Deep research flow in `app/langchain_deep_search.py`

This draft extends those pieces instead of replacing the app.

## 5. New User Flow (unchanged from third draft)

### 5.1 First App Start

1. Load `schema/local_db/user_profile.json`.
2. If it does not exist, keep the existing writing style and resume setup flow.
3. If it exists, skip repeated writing style and resume setup for new chats.
4. Load tracked creator profiles from `schema/local_db/tracked_profiles/index.json`.
5. If no tracked profile exists, seed the default testing profile:
   `https://www.linkedin.com/in/theburningmonk/`

### 5.2 New Chat

1. Validate provider, model, and API key as the app already does.
2. Create a normal chat session.
3. Check the global saved user profile.
4. If writing style exists, do not ask for previous posts again.
5. If resume/profile data exists or was previously skipped, do not ask for resume again.
6. Send the user directly to the workflow choice screen.

The user can still edit saved style or resume data from the sidebar.

### 5.3 Tracking a Creator

In the sidebar, add a "Tracked Creators" section.

Controls:

- Text input: "LinkedIn profile URL"
- Default value or placeholder: `https://www.linkedin.com/in/theburningmonk/`
- Button: "Add creator"
- List/selectbox of tracked creators
- Button: "Check for new posts"
- Small stats: Seen posts, Used posts, Unused posts, Last checked time

When no URL is entered and the user clicks "Add creator", the app adds the default testing URL.

### 5.4 Checking for New Posts (updated)

When the user clicks "Check for new posts":

1. Check whether a bootstrapped burner session exists (see Section 6). If `LINKEDIN_AUTOMATION_MODE=burner` but no bootstrapped profile directory is found, show a clear Streamlit message telling the user to run the bootstrap script first. Do not attempt to log in automatically.
2. Call the Playwright scraper module.
3. Open the persistent Playwright browser context from the existing burner profile directory (headless), or an isolated logged-out context.
4. Visit the tracked profile's recent activity page.
5. Extract recent post candidates.
6. Normalize each post into a stable local record.
7. Save only posts that are not already in `seen_posts`.
8. Do not show posts already listed in `used_post_ids`.

### 5.5 Generating From a Tracked Creator Post (unchanged)

1. User selects a tracked creator.
2. App shows unused source posts from that creator.
3. User clicks "Use this post as topic".
4. The selected creator post text becomes the seed topic.
5. The app loads saved writing style and resume/profile data from `user_profile.json`.
6. The existing LangGraph generation workflow runs.
7. The generated post opens in the existing post editor chat screen.
8. After successful generation, the source LinkedIn post ID is added to `used_post_ids`.

The generated post should not copy the creator's wording. It should use the creator post only as topic inspiration.

## 6. Session Bootstrap (new)

### 6.1 Purpose

Create a trusted, persistent Playwright browser profile for the burner account **once**, via a manual human login, so that all future scraping runs can reuse it headlessly without ever hitting the automated-login failure point.

### 6.2 New script: `scripts/bootstrap_linkedin_session.py`

```python
"""
Run this manually, from a terminal, on a machine with a display.
It opens a real (headed) browser window pointed at the burner
profile directory. Log in by hand, solve any verification
challenge normally, then close the window.

Usage:
    uv run python scripts/bootstrap_linkedin_session.py
"""

from playwright.sync_api import sync_playwright
from app.config import LINKEDIN_BROWSER_PROFILE_DIR

def main():
    LINKEDIN_BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(LINKEDIN_BROWSER_PROFILE_DIR),
            headless=False,
            viewport={"width": 1365, "height": 900},
        )
        page = context.new_page()
        page.goto("https://www.linkedin.com/login")
        print("A browser window has opened.")
        print("Log in manually with the BURNER account only.")
        print("Solve any CAPTCHA / verification screen yourself.")
        print("Once you land on the LinkedIn feed, come back here and press Enter.")
        input("Press Enter after you have finished logging in... ")
        context.close()
        print("Session saved to:", LINKEDIN_BROWSER_PROFILE_DIR)
        print("You can now run the app in headless burner mode.")

if __name__ == "__main__":
    main()
```

Notes:

- This script must never be called automatically by the Streamlit app. It is a standalone, manually-invoked tool.
- It must never be pointed at a real Chrome/Edge profile directory — only at `LINKEDIN_BROWSER_PROFILE_DIR`, the dedicated burner directory.
- It must never fill in credentials automatically — the whole point is that a human performs the login and clears any challenge.
- The script should print clear instructions so the user knows it is safe to close the window once logged in.

### 6.3 Detecting whether bootstrap has happened

Add a small check in `app/linkedin_playwright_scraper.py` (or `app/creator_tracking.py`) before attempting a burner-mode scrape:

```python
def has_bootstrapped_burner_session() -> bool:
    return LINKEDIN_BROWSER_PROFILE_DIR.exists() and any(
        LINKEDIN_BROWSER_PROFILE_DIR.iterdir()
    )
```

If `LINKEDIN_AUTOMATION_MODE=burner` and this returns `False`, the app should show:

> "Burner session not found. Run `uv run python scripts/bootstrap_linkedin_session.py` once from a terminal to log in manually, then try again."

The app should not fall back to attempting an automated login.

### 6.4 Re-bootstrapping

If a headless scrape run unexpectedly lands on a login page or challenge page (see Section 8.3), treat this as "session expired or flagged" and show the same message pointing the user back to the manual bootstrap script. Do not attempt to retry the login automatically, and do not attempt to solve the challenge programmatically.

## 7. Data Model (unchanged from third draft)

### 7.1 Global User Profile

`schema/local_db/user_profile.json`

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
  "created_at": "2026-07-01T00:00:00+00:00",
  "updated_at": "2026-07-01T00:00:00+00:00"
}
```

Rules:

- `writing_style` is required before generation.
- `resume_profile` is optional.
- `resume_skipped: true` means the user intentionally skipped resume setup and should not be asked again on every new chat.
- New chats read this file instead of requiring the user to paste previous posts again.

### 7.2 Tracked Creator Index

`schema/local_db/tracked_profiles/index.json`

```json
{
  "profiles": [
    {
      "profile_id": "theburningmonk",
      "profile_url": "https://www.linkedin.com/in/theburningmonk/",
      "display_name": "theburningmonk",
      "added_at": "2026-07-01T00:00:00+00:00",
      "last_checked_at": null,
      "seen_count": 0,
      "used_count": 0,
      "unused_count": 0
    }
  ]
}
```

### 7.3 Per-Creator Post Store

`schema/local_db/tracked_profiles/{profile_id}.json`

```json
{
  "profile_id": "theburningmonk",
  "profile_url": "https://www.linkedin.com/in/theburningmonk/",
  "display_name": "theburningmonk",
  "added_at": "2026-07-01T00:00:00+00:00",
  "last_checked_at": "2026-07-01T00:00:00+00:00",
  "seen_posts": [
    {
      "post_id": "urn:li:activity:123456789",
      "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:123456789/",
      "raw_text": "Example creator post text...",
      "author_name": "Yan Cui",
      "posted_at_text": "2h",
      "fetched_at": "2026-07-01T00:00:00+00:00",
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

### 7.4 Session Additions

```json
{
  "topic_source": "tracked_creator",
  "source_profile_id": "theburningmonk",
  "source_post_id": "urn:li:activity:123456789",
  "source_post_url": "https://www.linkedin.com/feed/update/urn:li:activity:123456789/",
  "source_post_text": "Creator post text used as topic seed..."
}
```

## 8. New / Updated Modules

### 8.1 `app/creator_tracking.py` (unchanged from third draft)

```python
def normalize_linkedin_profile_url(url: str) -> str: ...
def get_profile_id(profile_url: str) -> str: ...
def seed_default_profile_if_empty() -> None: ...
def add_tracked_profile(url: str | None) -> dict: ...
def list_tracked_profiles() -> list[dict]: ...
def load_tracked_profile(profile_id: str) -> dict: ...
def save_tracked_profile(profile: dict) -> dict: ...
def check_for_new_posts(profile_id: str) -> list[dict]: ...
def list_unused_posts(profile_id: str) -> list[dict]: ...
def mark_post_used(profile_id: str, post_id: str) -> None: ...
```

Implementation notes:

- Use existing JSON storage style from `app/storage.py`.
- Keep file writes simple and readable.
- Update index counts after each profile save.
- Print important workflow actions to console (project prefers `print()`).

### 8.2 `app/linkedin_playwright_scraper.py` (updated login handling)

Main function (unchanged signature):

```python
def fetch_recent_profile_posts(profile_url: str, max_posts: int = 5) -> list[dict]:
    ...
```

Returned post shape (unchanged):

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

**Updated Playwright strategy:**

1. Determine mode from `LINKEDIN_AUTOMATION_MODE`.
2. If `burner`:
   - Check `has_bootstrapped_burner_session()`. If `False`, return a clear error object instructing the user to run the bootstrap script. Do not attempt login.
   - Launch `chromium.launch_persistent_context(user_data_dir=LINKEDIN_BROWSER_PROFILE_DIR, headless=LINKEDIN_HEADLESS, viewport={...})`. This reuses the already-authenticated session — no login form is filled in by code.
3. If `logged_out`:
   - Launch a plain, non-persistent isolated context.
   - Never submit login forms.
4. Build candidate activity URLs:
   - `{profile_url}/recent-activity/all/`
   - `{profile_url}/recent-activity/shares/`
   - base profile URL as fallback
5. Navigate to the best activity URL.
6. **Check for a login/challenge page** (see Section 8.3) immediately after navigation. If detected, stop and return a clear error object — do not attempt to interact with the login/challenge form in any way.
7. Wait for the page to settle.
8. Scroll slowly once or twice to load recent posts.
9. Extract post containers.
10. Extract post text, post URL, and activity URN where available.
11. Return normalized post objects.

Important (unchanged):

- Do not use the user's installed browser profile.
- Do not import cookies from any browser.
- Do not store personal LinkedIn credentials.
- Do not perform write actions on LinkedIn.
- **New:** Never fill in or submit LinkedIn's login form from code, in either mode. The only place a human ever types burner credentials is inside the manual `scripts/bootstrap_linkedin_session.py` run.

### 8.3 Login/challenge page detection (new)

Add a helper used right after every navigation in burner mode:

```python
def looks_like_login_or_challenge_page(page) -> bool:
    url = page.url
    if "linkedin.com/login" in url or "linkedin.com/checkpoint" in url:
        return True
    # Layered fallback checks, since LinkedIn markup changes:
    if page.locator("input[name='session_password']").count() > 0:
        return True
    if page.locator("text=Let’s do a quick security check").count() > 0:
        return True
    return False
```

If this returns `True`:

- Stop immediately.
- Do not attempt any form interaction.
- Return an error object such as:

```python
{
    "error": "session_expired_or_challenged",
    "message": (
        "The burner session appears to be logged out or blocked by a "
        "LinkedIn verification screen. Re-run "
        "scripts/bootstrap_linkedin_session.py to log in manually, "
        "then try again."
    ),
}
```

- The Streamlit UI should surface this `message` directly to the user.

### 8.4 `app/user_profile.py` (unchanged from third draft)

```python
def load_user_profile() -> dict: ...
def save_user_profile(profile: dict) -> dict: ...
def has_saved_writing_style() -> bool: ...
def get_generation_profile() -> tuple[dict, dict]: ...
def update_writing_style(style: dict, source: str, examples: list[str] | None = None) -> dict: ...
def update_resume_profile(resume_profile: dict, source: str, skipped: bool = False) -> dict: ...
```

## 9. Config Changes

`app/config.py` additions (mostly unchanged, one new path):

```python
USER_PROFILE_PATH = LOCAL_DB_DIR / "user_profile.json"
TRACKED_PROFILE_DIR = LOCAL_DB_DIR / "tracked_profiles"
TRACKED_PROFILE_INDEX_PATH = TRACKED_PROFILE_DIR / "index.json"

LINKEDIN_DEFAULT_TRACK_URL = os.getenv(
    "LINKEDIN_DEFAULT_TRACK_URL",
    "https://www.linkedin.com/in/theburningmonk/",
)

LINKEDIN_AUTOMATION_MODE = os.getenv("LINKEDIN_AUTOMATION_MODE", "logged_out")
LINKEDIN_HEADLESS = os.getenv("LINKEDIN_HEADLESS", "true").lower() == "true"
LINKEDIN_CHECK_MAX_POSTS = int(os.getenv("LINKEDIN_CHECK_MAX_POSTS", "5"))
LINKEDIN_BROWSER_PROFILE_DIR = LOCAL_DB_DIR / "playwright" / "linkedin_burner_profile"
```

Notes on the removed variables from the third draft:

- `LINKEDIN_BURNER_EMAIL` / `LINKEDIN_BURNER_PASSWORD` are **no longer read by the app or the scraper module**. Credentials are only ever typed by a human directly into the LinkedIn login page during the manual bootstrap script — they are never stored in `.env` or in code. This removes an entire class of "automate the login" failure and avoids storing plaintext burner credentials on disk.

Update `ensure_local_db()` so it creates:

```text
schema/local_db/sessions/
schema/local_db/tracked_profiles/
schema/local_db/playwright/
```

## 10. Environment Variables

`example.env`:

```env
# LinkedIn creator tracking with Playwright
LINKEDIN_DEFAULT_TRACK_URL=https://www.linkedin.com/in/theburningmonk/
LINKEDIN_AUTOMATION_MODE=logged_out
LINKEDIN_HEADLESS=true
LINKEDIN_CHECK_MAX_POSTS=5

# Burner account credentials are NOT stored here.
# To use burner mode:
#   1. Set LINKEDIN_AUTOMATION_MODE=burner
#   2. Run: uv run python scripts/bootstrap_linkedin_session.py
#   3. Log in manually in the window that opens (burner account only)
#   4. Close the window once logged in
```

Mode behavior:

- `LINKEDIN_AUTOMATION_MODE=logged_out` — no account login, best for safest testing.
- `LINKEDIN_AUTOMATION_MODE=burner` — requires a prior manual bootstrap run; the app must show a clear error (not attempt login) if `has_bootstrapped_burner_session()` is `False`.

## 11. Dependency Changes (unchanged)

```bash
uv add playwright
uv run playwright install chromium
```

No LinkedIn API package is needed for this draft.

## 12. Streamlit UI Changes

### 12.1 Sidebar: Saved User Profile (unchanged)

Sidebar expander "Saved Profile":

- Writing style status: "Saved" or "Not saved"
- Resume/profile status: "Saved", "Skipped", or "Not saved"
- Buttons: "Edit writing style", "Edit resume/profile", "Reset saved profile"

### 12.2 Sidebar: Tracked Creators (updated)

Sidebar expander "Tracked Creators":

- URL input, "Add creator" button
- Selectbox of tracked creators
- "Check for new posts" button
- Counts for seen, used, and unused posts
- Last checked timestamp
- **New:** if `LINKEDIN_AUTOMATION_MODE=burner` and no bootstrapped session is found, show a persistent info box:
  > "Burner session not set up yet. Run `uv run python scripts/bootstrap_linkedin_session.py` in a terminal, log in manually once, then come back here."
- **New:** if a scrape attempt returns `session_expired_or_challenged`, surface that message in the same spot instead of a generic error.

If the tracked profile list is empty, automatically call `seed_default_profile_if_empty()`.

### 12.3 New Chat Behavior (unchanged)

```text
if no saved writing style:
    writing_style -> save globally -> resume
elif no saved resume and resume was not skipped:
    resume -> save globally -> choose_mode
else:
    choose_mode
```

### 12.4 Choose Workflow Screen (unchanged)

Two cards: "Generate from topic", "Research trending topics". Inside "Generate from topic", topic source options: "Manual topic", "Tracked creator post".

### 12.5 Tracked Creator Topic Screen (unchanged)

- Selectbox of tracked creators.
- Unused posts for selected creator, each showing: short text preview, source URL, fetched time, "Use this post as topic" button.
- On click: run existing post generation graph, save source post metadata into session, mark source post used only after generation succeeds.

## 13. LangGraph Changes (unchanged from third draft)

Current topic generation already accepts `topic`, `writing_style`, `resume_profile`, `messages`, `provider`, `model`, `api_key`.

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

## 14. Storage Migration Plan (unchanged)

This draft is additive. Do not break existing sessions.

1. If `user_profile.json` exists, use it.
2. If it does not exist, keep using the old per-session setup prompts.
3. When the user saves writing style in a new session, write it to `user_profile.json`.
4. When the user saves resume/profile data or skips resume, write that decision to `user_profile.json`.
5. Existing old sessions can continue to contain `writing_style` and `resume_profile`.

Recommended: store `writing_style_snapshot` and `resume_profile_snapshot` in the session only when generation starts, so edits to the global profile later don't retroactively change what a past post used.

## 15. Playwright Implementation Details (updated)

### 15.1 Browser Context

Burner mode (headless reuse of the bootstrapped session):

```python
context = chromium.launch_persistent_context(
    user_data_dir=str(LINKEDIN_BROWSER_PROFILE_DIR),
    headless=LINKEDIN_HEADLESS,
    viewport={"width": 1365, "height": 900},
)
```

Bootstrap only (manual, headed, run via `scripts/bootstrap_linkedin_session.py`):

```python
context = chromium.launch_persistent_context(
    user_data_dir=str(LINKEDIN_BROWSER_PROFILE_DIR),
    headless=False,
    viewport={"width": 1365, "height": 900},
)
```

Only ever use `LINKEDIN_BROWSER_PROFILE_DIR` for this. Do not use:

- Your real Chrome user data directory.
- Your real Edge user data directory.
- Any profile copied from a personal browser.

### 15.2 Login Logic (replaced)

The scraper module itself **never logs in**. Instead:

- **Burner mode:** assumes `LINKEDIN_BROWSER_PROFILE_DIR` already contains a valid session from a prior manual bootstrap run. If `has_bootstrapped_burner_session()` is `False`, refuse to run and return a clear message (Section 8.3 / 6.3).
- On every navigation, check `looks_like_login_or_challenge_page()`. If a login or challenge page is detected mid-run (session expired, flagged, etc.), stop immediately, do not interact with the form, and return a `session_expired_or_challenged` error pointing the user back to the bootstrap script.
- **Logged-out mode:** never submit login forms; only reads public post data where visible.

There is no code path anywhere in the app that fills in a username/password field. The only place that ever happens is a human, manually, inside `scripts/bootstrap_linkedin_session.py`.

### 15.3 Selectors (unchanged)

LinkedIn class names change often, so selectors should be layered:

- Links containing `/feed/update/`
- Elements containing `urn:li:activity`
- Feed update containers such as `div.feed-shared-update-v2`
- Visible post text containers such as `div.update-components-text`
- Fallback page text parsing if structured selectors fail

Extraction should be tolerant:

- If post URL exists but text is missing, skip.
- If text exists but post ID is missing, create a hash-based ID.
- If the page is blocked by a login/challenge wall, return the `session_expired_or_challenged` error object instead of trying to parse the page.

### 15.4 Rate and Behavior (unchanged)

- Manual "Check for new posts" only.
- No background scheduler in this draft.
- Max 5 posts per check by default.
- Small random waits between page actions.
- One or two scrolls only.

## 16. File Structure After This Draft

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

scripts/
  bootstrap_linkedin_session.py

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
  fourth_plan_draft.md
```

## 17. Git Ignore Changes (unchanged)

```gitignore
schema/local_db/*.json
schema/local_db/sessions/
schema/local_db/tracked_profiles/
schema/local_db/playwright/
```

Never commit actual scraped LinkedIn data, browser cookies, or burner account profile data. The `linkedin_burner_profile/` directory in particular contains authenticated session data and must stay out of version control.

## 18. Implementation Order

### Phase 1: Configuration and Persistence

Files: `app/config.py`, `app/user_profile.py`, `app/storage.py`, `example.env`, `.gitignore`

1. Add new config paths and LinkedIn env variables (no credential env vars).
2. Add local DB folder creation.
3. Add global user profile read/write helpers.
4. Save writing style globally.
5. Save resume/profile or skip decision globally.
6. Make new chats reuse saved global profile data.

### Phase 2: Creator Tracking Storage (unchanged)

Files: `app/creator_tracking.py`, `schema/local_db/tracked_profiles/`

1. Normalize LinkedIn profile URLs.
2. Generate stable `profile_id` values.
3. Seed default profile when none exist.
4. Add tracked creator records.
5. Store seen posts and used post IDs.
6. List unused posts.
7. Mark posts used after generation.

### Phase 3: Session Bootstrap Script (new)

Files: `scripts/bootstrap_linkedin_session.py`

1. Implement the manual, headed, persistent-context login script.
2. Print clear step-by-step instructions.
3. Verify the profile directory is populated after the run.
4. Document usage in the README.

### Phase 4: Playwright Scraper (updated)

Files: `app/linkedin_playwright_scraper.py`, `pyproject.toml`, `uv.lock`

1. Add Playwright dependency, install Chromium.
2. Implement `has_bootstrapped_burner_session()`.
3. Implement `looks_like_login_or_challenge_page()`.
4. Implement logged-out mode (no login attempts).
5. Implement burner mode that only ever reuses the bootstrapped persistent context — never logs in from code.
6. Implement recent activity navigation with challenge-page short-circuiting.
7. Extract post text and activity IDs with layered selector fallbacks.
8. Return normalized post records or clear error objects for: no bootstrap found, session expired/challenged, empty results, selector failures.

### Phase 5: Streamlit UI Integration (updated)

Files: `streamlit_ui/app.py`

1. Add saved profile status controls.
2. Add tracked creator sidebar controls.
3. Add "Check for new posts" action.
4. Show seen/used/unused counts.
5. Surface bootstrap-required and session-expired messages clearly, with the exact terminal command to run.
6. Add tracked creator topic source to the generation screen.
7. Pass selected source post into existing graph generation.
8. Save source metadata into session.
9. Mark source post used after successful generation.

### Phase 6: Polish and Guardrails

Files: `app/linkedin_playwright_scraper.py`, `app/creator_tracking.py`, `streamlit_ui/app.py`, `README.md`

1. Add clear Streamlit messages for automation mode and bootstrap status.
2. Show warning that personal accounts must not be used, including inside the bootstrap script's printed instructions.
3. Make empty/blocked LinkedIn pages understandable.
4. Keep all LinkedIn automation read-only.
5. Keep all console visibility through `print()`.
6. Document the bootstrap step clearly in the README as a one-time (or occasional) manual setup step.

## 19. Out of Scope for This Draft (unchanged, plus one addition)

- Full admin dashboard.
- Background cron or automatic scheduled scraping.
- Auto-publishing to LinkedIn.
- Commenting, liking, reposting, following, or messaging.
- LinkedIn official API integration.
- Unofficial/reverse-engineered LinkedIn login or data APIs.
- Multi-user auth.
- MongoDB or DynamoDB migration.
- Browser-cookie import from personal browsers.
- Any code path that programmatically fills in or submits LinkedIn's login form.

## 20. Main Risks

### LinkedIn Blocking / Challenge Screens

Handling:

- The scraper detects login/challenge pages immediately and stops — it never tries to solve or bypass them.
- Recovery is always the manual bootstrap script, run by a human.
- Do not retry aggressively; repeated automated attempts are more likely to increase suspicion, not less.

### UI Selector Breakage

Handling:

- Keep selectors in one scraper module.
- Use several fallback extraction strategies.
- Return empty results with a clear message when extraction fails.

### Burner Account Flagging

Even a burner account, and even with manual bootstrap, can still be limited or banned over time.

Handling:

- Use manual "Check for new posts" only — no scheduler.
- Keep max posts low.
- Reuse a single persistent burner browser context rather than creating new ones.
- Never automate account actions.
- Never use the personal account.
- Treat repeated `session_expired_or_challenged` results as a signal to slow down usage, not to script around the checks.

### Session/Credential Data Sensitivity

Handling:

- The persistent burner profile directory contains authenticated session data — treat it like a secret.
- Store only under `schema/local_db/playwright/`.
- Add it to `.gitignore`.
- Never commit it.
- Never store burner credentials in `.env`, code, or logs — the human types them once, directly into LinkedIn's own login page, during bootstrap only.

## 21. Final Target Experience

1. User opens Streamlit.
2. App already knows saved writing style and resume/profile details.
3. App has the default creator profile ready for testing.
4. If burner mode is selected and no session is bootstrapped yet, the app tells the user to run the bootstrap script once.
5. User runs `scripts/bootstrap_linkedin_session.py`, logs in manually in the window that opens, closes it.
6. User clicks "Check for new posts" in the app.
7. App reuses the bootstrapped session headlessly via Playwright to fetch recent creator posts — no login screen appears.
8. User selects an unused creator post.
9. App generates a new LinkedIn post in the user's own style.
10. App opens the existing post editor chat.
11. The source creator post is marked used and will not be suggested again.

This keeps the third draft's design intact while replacing the failure-prone automated-login step with a one-time manual bootstrap that Playwright can then reuse headlessly and reliably.