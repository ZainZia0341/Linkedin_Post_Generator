# Chrome Extension Scraping Snapshot - 21 July 2026

## Goal

Move the active creator post and profile scraping workflow from backend-launched
Playwright windows to the Chrome profile where the LinkedIn burner account is
already signed in. The existing frontend still starts and monitors the same
FastAPI scrape jobs. Users do not have to start a separate scrape inside the
extension.

The old Playwright implementation and direct backend endpoints are retained for
an intentional rollback, but the normal asynchronous post/profile scrape jobs
do not fall back to Playwright.

## Current Flow

1. The frontend starts the existing async creator-post or creator-profile job.
2. FastAPI processes creators one at a time.
3. Before each creator, FastAPI chooses a fresh random delay between
   `SCRAPE_INTER_CREATOR_DELAY_MIN_SECONDS` and
   `SCRAPE_INTER_CREATOR_DELAY_MAX_SECONDS`.
4. FastAPI queues one extension task and waits for its bounded result.
5. The extension polls FastAPI, claims the task, and opens an inactive LinkedIn
   tab in the already signed-in Chrome profile.
6. The content script extracts post or profile data from the live DOM and sends
   the result to FastAPI.
7. FastAPI validates, deduplicates, and saves the data through the existing
   repository code. Existing frontend job-status polling shows progress,
   creator counts, post counts, and errors.

Chrome does not provide a truly invisible page with the user's normal session.
The extension therefore uses an inactive background tab. It should not steal
focus, but the temporary tab can be visible in Chrome's tab strip.

## Implemented Files

- `manifest.json`: Manifest V3 permissions, background worker, popup, options,
  and LinkedIn content script.
- `background.js`: task polling, inactive-tab navigation, extraction requests,
  result reporting, and connection state.
- `content.js`: structural DOM extraction for creator posts, reposts, profile
  fields, and experience entries without relying on LinkedIn's hashed classes.
- `popup.html` / `popup.js`: enabled state, backend connection, last task, and
  errors.
- `options.html` / `options.js`: local backend URL and optional shared token.
- `styles.css`: extension popup/options styling.

Backend integration is in `backend/app/extension_scraping.py`, with extension
routes in `backend/app/api/main.py`. The active async job functions in
`backend/app/api/services.py` explicitly use the extension transport. Existing
direct Playwright functions are unchanged and remain callable by their legacy
endpoints.

## FastAPI Extension Endpoints

- `POST /extension/heartbeat`: records a connected extension instance.
- `GET /extension/tasks/next`: heartbeat plus claim-next-task operation.
- `POST /extension/tasks/{task_id}/result`: reports extracted data or an error.
- `GET /extension/status`: reports connection and queued/active task counts.

If `EXTENSION_API_TOKEN` is set in FastAPI, enter the same token in the
extension settings. A blank value on both sides is allowed for local-only use.

## Install In Chrome

1. Start the local backend from `backend`:

   ```powershell
   uv run uvicorn app.api.main:app --reload --host 127.0.0.1 --port 7860
   ```

2. Open the Chrome profile where the burner account is already logged in to
   LinkedIn.
3. Open `chrome://extensions`.
4. Enable **Developer mode**.
5. Click **Load unpacked**.
6. Select `D:\Linkedin_Post_Generator\extention`.
7. Pin **AI Spark LinkedIn Scraper** from Chrome's Extensions menu.
8. Open the extension, click **Settings**, and keep the backend URL as
   `http://localhost:7860`. Enter the shared token only if the backend has one.
9. Click **Test connection**, then ensure the popup reports **Connected**.

After installation, use **Run Scraping** in the frontend exactly as before. The
extension automatically claims tasks; there is no separate run button. Keep
Chrome and the local FastAPI process running until the scrape job finishes.

After changing extension source files, return to `chrome://extensions` and
click the extension's reload icon.

## Configuration

```text
SCRAPE_INTER_CREATOR_DELAY_MIN_SECONDS=0
SCRAPE_INTER_CREATOR_DELAY_MAX_SECONDS=240
EXTENSION_SCRAPE_TASK_TIMEOUT_SECONDS=300
EXTENSION_SCRAPE_TASK_LEASE_SECONDS=120
EXTENSION_API_TOKEN=
```

The default delay selects a new value from 0 through 240 seconds for every
creator. Restart FastAPI after changing environment values.

## Data Notes

- Post results keep the existing post ID, URL, text, fetched time, hash, and
  source fields.
- Reposts are separated into reposter commentary and original-post text/author
  fields by repeated nested author-card structure.
- Profile results keep the existing headline, about, location, email, avatar,
  and experience shape.
- FastAPI remains responsible for validation, deduplication, `is_new`, saving,
  job progress, and error reporting.

## Profile Extraction Correction

The first extension profile test exposed a LinkedIn SDUI DOM variant that is
different from the older semantic profile markup:

- Experience rows are lazy-mounted `div` elements whose stable structural hint
  is `componentkey="entity-collection-item-..."`. Only grouped-company child
  roles still use `li`, which is why the original extension pass returned only
  two Amazon roles while ignoring the other visible positions.
- The About card can be mounted after the initial viewport. The extension now
  scans keyed/labelled About containers while scrolling the profile page and
  stops before the next profile section.
- Experience extraction now collects top-level entity rows and grouped-company
  child roles while scrolling the details page. Results are accumulated across
  lazy/virtualized viewports and deduplicated instead of being limited to the
  currently mounted list nodes.
- Avatar extraction is now restricted to the profile identity area. An image
  linked to another `/in/...` profile is rejected, and a candidate must match
  the current profile link or the scraped profile name. There is no arbitrary
  sidebar/image fallback; when no trustworthy image exists, the saved URL is
  empty and the frontend renders initials.

This was an extension extractor compatibility issue with LinkedIn's current
DOM, not a frontend profile-image mapping issue. The frontend reads the saved
`profile_image_url` for the matching `creator_id`; the incorrect image seen in
the UI had therefore been saved by the earlier broad extension selector.

Experience parsing now follows the two structural shapes LinkedIn mixes on the
same details page. A flat `entity-collection-item` is parsed as one role. A
grouped item uses its outer company header plus each direct dated `li` role.
The parser identifies descriptions with `data-testid="expandable-text-box"`,
uses the styled title paragraph and paragraph order, and does not depend on
LinkedIn's generated CSS class names.

## Post Extraction Correction

- Relative post age is read only from actor timestamp metadata such as
  `.update-components-actor__sub-description`. Supported units now include
  seconds, minutes, hours, days, weeks, months, and years.
- The scraper no longer searches the complete post body for a timestamp. That
  fallback incorrectly interpreted content such as `100M rows` as a post age
  when the real LinkedIn timestamp was `1w`.
- A repost without commentary keeps `is_repost=true` and the nested original
  post fields, but saves an empty `repost_text`. Duplicate outer text is
  compared with the original post after whitespace and hashtag normalization.

After this file changes, reload **AI Spark LinkedIn Scraper** from
`chrome://extensions` and scrape the creator profile again. A successful
rescrape overwrites the previously incomplete About, experience, and avatar
fields.

## Limits And Troubleshooting

- If the popup says **Needs attention**, confirm FastAPI is running on port
  7860 and the token matches.
- If FastAPI reports a session/challenge error, open LinkedIn in that Chrome
  profile and complete login or verification manually.
- LinkedIn DOM changes can require updates to `content.js`; extraction uses
  stable URLs, labels, text, and nesting where possible instead of hashed CSS
  classes.
- Extension tasks and scrape-job state are currently process-local. Restarting
  FastAPI while a job is running loses that job. Scraping remains a local
  workflow; the deployed Lambda continues to serve API/data operations with
  scraping disabled.
