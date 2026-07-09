# Eighth Plan Draft - Creator Profile Detail Scraping

## Goal

Add automation for scraping saved creator profile details so the app can help
craft reachout messages from a creator's LinkedIn profile context.

The fields to collect are:

- Name
- Headline
- About
- Experience

The new work must not disturb the existing creator add, post scrape, 24-hour
scrape, activity, comment, generation, or Streamlit flows.

## Existing Pieces To Reuse

- FastAPI routes in `app/api/main.py`.
- Pydantic schemas in `app/api/schemas.py`.
- Business logic in `app/api/services.py`.
- DynamoDB repository in `app/db/dynamodb.py`.
- Existing creators table keyed by `user_id` and `creator_id`.
- Creator URL normalization from `app/creator_tracking.py`.
- Existing Playwright setup in `app/linkedin_playwright_scraper.py`.
- Existing LinkedIn automation settings:
  - `LINKEDIN_AUTOMATION_MODE`
  - `LINKEDIN_HEADLESS`
  - `LINKEDIN_BROWSER_PROFILE_DIR`
- Existing Streamlit request helpers and tab structure in `streamlit_ui/app.py`.

No new database table is needed. Profile details can be saved on the existing
creator record under a `profile_details` object.

## New API Requirements

### Scrape Added Creator Profile Details

Add:

```text
POST /creators/profile-details/scrape
```

Request:

```json
{
  "user_id": "test-user-1",
  "creator_ids": ["creator-one"]
}
```

Rules:

- Use the user's already added creators.
- If `creator_ids` is missing, scrape all added creators for that user.
- Use Playwright in the same way as current LinkedIn post scraping.
- In burner mode, keep sequential scraping because one persistent browser profile
  is shared.
- Scrape only public/profile text. Do not like, comment, message, connect, or
  mutate LinkedIn state.
- Save the scraped details onto the existing creator record.
- Update `display_name` when a real name is found.
- Return profile details plus row-level errors.

### Fetch All Creator Details For A User

Add:

```text
GET /users/{user_id}/creators/profile-details?limit=100
```

Rules:

- Return saved profile details for all creators belonging to the user.
- Do not run Playwright.
- Include creators even if details are not scraped yet, with blank detail fields.

### Fetch One Creator Details

Add:

```text
GET /users/{user_id}/creators/{creator_id}/profile-details
```

Rules:

- Return saved profile details for one creator.
- Return `404` if the creator is not saved for that user.
- Do not run Playwright.

## Profile Detail Shape

Use a response object with:

```json
{
  "user_id": "test-user-1",
  "creator_id": "creator-one",
  "profile_url": "https://www.linkedin.com/in/creator-one/",
  "name": "Creator One",
  "headline": "Founder | AI Builder",
  "about": "Profile about text...",
  "experience": ["Founder at Example", "Engineer at Previous"],
  "fetched_at": "2026-07-07T00:00:00+00:00",
  "source": "playwright"
}
```

## Scraper Approach

In `app/linkedin_playwright_scraper.py` add a new function:

```python
fetch_profile_details(profile_url: str) -> dict[str, Any]
```

It will:

- Reuse `_open_context`, login/challenge checks, `_body_text`, and `_error`.
- Open the creator profile URL.
- Extract likely name and headline from the profile top card.
- Extract about text from visible profile sections when available.
- Open `/details/experience/` and extract visible experience rows.
- Return a dictionary with name, headline, about, experience, fetched_at, and
  source.

LinkedIn DOM changes often, so the extractor should use several selectors and
safe fallbacks rather than depending on one exact class name.

## Playwright DOM Research Findings

Test profile used:

```text
https://www.linkedin.com/in/txshep/
```

Observed with the existing burner Playwright session:

- The main profile URL loads the top card and About section.
- The old selectors were unreliable in the current logged-in LinkedIn DOM:
  - `main h1` returned no match.
  - `.text-body-medium.break-words` returned no match.
  - `main li.pvs-list__paged-list-item` returned no match.
- The profile data was visible as text lines inside `main section` elements.
- The first profile/top-card section contained:
  - line 1: name
  - line 2: headline
  - later lines: location, contact info, followers, buttons
- The About section was available on the main profile page as a section whose
  first line is `About`.
- `https://www.linkedin.com/in/txshep/details/about/` returned LinkedIn's
  `This page doesn't exist`, so there is no useful About detail URL for this
  case.
- `https://www.linkedin.com/in/txshep/details/experience/` loaded the dedicated
  Experience page and exposed the full visible experience text inside an
  `Experience` section.

Decision:

- Use the main profile URL for `name`, `headline`, and `about`.
- Use `/details/experience/` for `experience`.
- Do not depend only on class names. Use a section/line-based fallback:
  - find a top-card-like section and read line 1/line 2 for name/headline
  - find a section whose first line is `About`
  - find a section whose first line is `Experience`
- Keep old class selectors as optional first attempts, but treat the line-based
  DOM parser as the primary fallback for logged-in LinkedIn pages.

## Service Approach

In `app/api/services.py` add helpers to:

- Normalize raw scraped details into the API response shape.
- Save details on the existing creator record as `profile_details`.
- Update `profile_details_checked_at`.
- List all saved details for a user.
- Get one saved creator detail record.
- Scrape selected/all creators with the same worker rules as existing scraping.

## Streamlit UI

Add new tabs without removing old tabs:

- `Profile Scrape`
- `Creator Details`

`Profile Scrape` should:

- Let the user select added creators.
- Call `POST /creators/profile-details/scrape`.
- Show scraped name, headline, about, experience, and errors.

`Creator Details` should:

- Load all saved creator details through
  `GET /users/{user_id}/creators/profile-details`.
- Let the user pick one creator and fetch the specific detail endpoint.
- Show name, headline, about, experience, profile URL, and fetched time.

## Testing Plan

Add focused tests later for:

- Profile detail normalization.
- Saving details onto a creator record.
- Listing all saved details for a user.
- Fetching one creator's saved details.
- Mocked profile-detail scraper behavior.

Live LinkedIn profile scraping should remain manual because it depends on
LinkedIn visibility and session state.
