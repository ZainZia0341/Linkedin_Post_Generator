# 17 July Frontend Plan: New Taplio-Style Screens

## Purpose

This document defines the frontend plan and records the isolated Taplio-style screens implemented on 17 July. Existing creator, scraping, generation, and comment routes remain independent.

## 17 July Implementation Update

Added isolated routes and components:

- `/prospects`: own-post sync/tracking, engagement scraping, account-wide deduplicated prospects, filters, and eligibility indicators.
- `/networking`: selected-post recipients, reply/connect/DM actions, preview-mode default, Live Playwright confirmation, per-recipient results, and action history.
- `/content`: four-column Ideas, In Progress, Ready to Post, and Published pipeline backed by content statuses.
- `/content/post-builder`: idea/URL input, topic suggestions, variations, formats, tones, angles, structures, lengths, multiple drafts, copy, and AI thread refinement.
- `/brainstorm`: goal-based idea research, source links, copy actions, follow-up directions, and direct handoff into a prefilled Post Builder.
- `/content/carousels`: manual or AI-assisted copy, deterministic built-in templates, stable 4:5 slide preview, thumbnail navigation, slide editing, add/delete, save, and multi-page PDF download.
- `/content/images`: post-context Gemini generation with style as the only visual input, plus a saved local asset grid, open, and delete.
- `/generate`: contextual image generation from the current post draft with the same style-only control.

Not exposed as complete features: historical Analytics, scheduling, and real LinkedIn publishing. Their backend contracts and durable execution requirements are not complete, so the UI does not pretend those workflows exist.

The new work must remain separate from the current Creators, Ready to Comment, Generate, Comments, History, and Dashboard implementations.

## Current Frontend Baseline

### Already available

- Creator list, single add, bulk import, update, delete, copy, and profile detail views.
- Selected/all creator post scraping with scrape-job progress.
- Selected/all creator profile scraping with scrape-job progress.
- Ready to Comment scraped-post cards, details, filters, and export flow.
- Post generation with length, tone, style, thread history, and refinement.
- Comment generation and comment refinement.
- Dashboard and history views for current generation and creator data.

### Backend capability exposed by the new UI

- Syncing and listing the user's own LinkedIn posts through Prospect Hub.
- Scraping and listing engagers for a tracked own post.
- Sending experimental replies, connection requests, and DMs through Networking with preview mode as the default.
- Listing experimental LinkedIn action logs in Networking.
- Generating and managing post-builder drafts, content statuses, carousels, and images.

### Remaining UI areas

- Durable Networking campaign progress, pause/resume, and scheduled execution.
- LinkedIn account analytics for 7/30/90 days.
- Server-side carousel render jobs and image bundles. Browser-rendered PDF download is implemented.
- Scheduling and publishing workflow.

## Isolation Strategy

Do not add these features inside the existing creator or Ready to Comment page components. Add independent top-level routes and feature modules:

| Navigation tab | Route | Responsibility |
| --- | --- | --- |
| Prospect Hub | `/prospects` | Deduplicated people who engaged with the user's own posts. |
| Networking | `/networking` | Reply, connection, and DM campaign preview/execution/history. |
| Analytics | `/analytics` | LinkedIn growth and content performance for 7/30/90 days. |
| Content | `/content` | Drafts, article generation, carousels, images, and later scheduling. |

Suggested module boundaries:

- `features/prospects`
- `features/networking`
- `features/analytics`
- `features/content`
- separate API clients and query keys for each feature
- shared primitives only for generic table, pagination, job progress, confirmation, and error presentation

Existing routes should not import new feature state. New screens may link to existing generation threads, but should not move or rewrite current generation code during the first implementation.

## Backend Readiness Matrix

| Screen | Backend readiness | Frontend decision |
| --- | --- | --- |
| Prospect Hub | MVP implemented | Uses the account-wide aggregation endpoint; production cursor pagination and normalized storage remain. |
| Networking | Experimental UI implemented | Uses current low-level action APIs with preview mode by default and explicit Live Playwright confirmation. Durable campaigns remain. |
| Analytics | Missing historical API | Build shell/design after analytics response contract is approved; do not fake charts from latest counts. |
| Article/URL generation | Implemented | Secure extraction and builder integration are available. |
| Content workflow | MVP implemented | Four statuses reuse existing thread records. |
| Carousel | Structured editor and browser PDF implemented | Templates keep one design across slides; production server-side render jobs remain unavailable. |
| Image generation | Development implementation complete | Gemini generation and local asset serving are available; production object storage remains. |
| Scheduling | Missing real publishing | Do not present scheduling as functional until publishing is implemented and verified. |

## Prospect Hub Tab

### Goal

Show one person once even if they liked and commented on multiple owned posts.

### Layout

- Compact summary row: total prospects, new prospects, commenters, likers, and contacted prospects.
- Search and filter bar.
- Dense paginated table or list built for repeated selection.
- Prospect detail drawer opened from a row.
- Persistent bulk action bar only when one or more people are selected.

### Filters

- Engagement type: all, commented, liked, reposted when actor identities exist.
- Connection degree.
- Engagement period.
- Source post.
- Contact state: never contacted, contacted, skipped, failed.
- Eligibility: can reply, can DM, can connect.

### Row fields

- person and profile link
- headline with a two-line limit in the table only
- connection degree
- merged engagement types
- engagement count and last engagement time
- source-post count
- latest action status
- selection checkbox

### Detail drawer

- full name and full headline
- profile URL and degree
- every source post and engagement type
- comment text and timestamp when available
- reply/DM/connect eligibility with a clear reason
- action history

The drawer should close on outside click unless a confirmation or action request is actively running.

### Required states

- initial loading skeleton
- no tracked own posts
- posts exist but engagement has not been scraped
- no engagers found, with scraper warning details
- partial data or stale connection degree
- paginated results and retryable API error

## Networking Tab

### Goal

Create controlled campaigns from selected prospects without mixing campaign state into Prospect Hub or creator scraping.

### Internal tabs

- `Create Campaign`
- `Running`
- `History`
- `Policies` only after scheduled automation is approved

### Create Campaign flow

1. Select action type: reply, connection request, or DM.
2. Select prospects from Prospect Hub or apply saved filters.
3. Configure shared or personalized content.
4. Request backend preview.
5. Review eligible and skipped recipients.
6. Confirm a preview or Live Playwright campaign.
7. Navigate to campaign progress.

### Reply campaign

- Show the source comment and post before editing a reply.
- Support a shared template or reviewed per-comment text.
- Do not offer reply action to a liker who has no comment reference.
- Show missing/stale comment references as skipped, not as frontend errors.

### Connection campaign

- Show the reason each prospect was selected.
- Show already connected, pending invitation, and previously contacted states.
- Support an optional note only when the backend confirms the flow is supported.
- Require a final confirmation for real sends.

### Personalized DM campaign

- Display one editable message preview per recipient.
- Highlight unresolved template variables.
- Allow recipients to be removed before approval.
- Never generate and send all messages from one unreviewed click.
- Show first-degree eligibility before the campaign starts.

### Progress screen

- processed/total counter
- succeeded, skipped, failed counts
- current account cooldown or limit state
- per-recipient result rows
- cancel button when cancellation is supported
- clear partial-success result instead of a single generic success message

### Safety UX

- Default to preview mode.
- Use explicit confirmation for real LinkedIn writes.
- Keep buttons disabled while a request is being accepted.
- Do not optimistically mark an action sent.
- Surface LinkedIn challenge/login states immediately.

## Analytics Tab

### Goal

Present honest historical data for the user's own LinkedIn account and tracked posts.

### Period control

Use a segmented control for `7 days`, `30 days`, and `90 days`. The selected period changes all cards and charts through one backend analytics query.

### Summary metrics

- followers and period growth
- impressions
- reactions
- comments
- reposts when available
- total engagement and engagement rate
- profile views when available
- posts published

### Views

- `Overview`: summary cards and daily trend charts.
- `Posts`: sortable performance table for owned posts.
- `Audience`: follower and reach metrics only when available.
- `Data Status`: last successful snapshot, missing dates, warnings, and account limitations.

### Analytics rules

- Do not replace unavailable values with zero.
- Label partial data and the first snapshot date.
- Keep totals independent of local table filters unless a metric explicitly describes the filtered result.
- Use tooltips to define engagement and engagement rate.
- Never build a historical chart by repeating the latest value.

## Content Tab

The `/content` route should own its own sub-navigation:

- `Drafts`
- `From Article`
- `Carousels`
- `Images`
- `Schedule` after real publishing is available

This keeps unfinished content workflows out of the existing Generate screen.

## Drafts Sub-Tab

### Workflow columns or filters

- Draft
- In Progress
- Ready
- Scheduled
- Published
- Failed
- Archived

### List behavior

- Status tabs with counts from the backend.
- Search and sort by updated date.
- Compact content cards or rows with topic, excerpt, assets, status, updated time, and owner.
- Open a content editor without changing the existing generation-thread page.
- Link to the originating generation thread when one exists.

### Editor behavior

- Save explicit revisions.
- Detect version conflict before overwriting another edit.
- Change status through allowed transitions.
- Attach generated images or carousels.
- Show publishing metadata only for scheduled/published items.

Recent generation threads must not be presented as drafts unless they have a content-item record and workflow status.

## From Article Sub-Tab

### Flow

1. Enter an HTTP/HTTPS URL.
2. Display extraction loading separately from generation loading.
3. Show extracted title, source, canonical URL, date, and content preview.
4. Show extraction warnings and require confirmation.
5. Choose existing post length, tone, and writing style controls.
6. Generate into a new content item and thread.

### Failure states

- invalid or unsafe URL
- unsupported content type
- timeout or oversized response
- login/paywall page
- no readable article body
- generation failure after successful extraction

The UI should not claim that paywalled or protected content can be bypassed.

## Carousel Sub-Tab

### Implemented screens

- carousel list
- manual creation or AI-assisted copy form
- slide editor
- deterministic theme selection and browser PDF export

### Editor

- Stable slide canvas dimensions.
- Thumbnail rail for slide order.
- Editable label, headline, and supporting-text fields.
- Add and delete slide actions; every new slide inherits the active template.
- One shared design template across all slides so the carousel remains visually consistent.
- AI generates structured text only. It does not generate separate slide images.
- Multi-page PDF download renders the exact current slide canvases in the browser.

Keep carousel editing and export state separate from normal post generation state.

## Images Sub-Tab

### Screens and controls

- post content used automatically as image context
- supported style control as the only visual choice
- generation progress
- result grid and asset detail
- delete unused asset with confirmation

### Required states

- quota/cost limit reached
- provider unavailable
- safety rejection
- generation timeout/failure
- generated but storage upload failed

The Generate screen uses its current draft automatically. Image Studio accepts post content directly. Both use a fixed LinkedIn-friendly 4:5 output and render stored asset URLs returned by the backend.

## Schedule Sub-Tab

This tab should remain hidden or clearly unavailable until real publishing exists. The backend endpoint currently named `POST /linkedin/posts/publish` only tracks a post and must not be treated as a publishing action.

When enabled, the screen needs:

- ready content selection
- timezone-aware date/time picker
- final post and asset preview
- LinkedIn account state
- schedule, reschedule, and cancel actions
- failed publish recovery
- published post ID and direct URL

## API Client and Caching Plan

- Keep current `frontend/lib/api.ts` contracts stable.
- Add feature-specific clients such as `api/prospects`, `api/networking`, `api/analytics`, and `api/content`.
- Use independent query keys for each feature and user account.
- Cache list/detail reads and invalidate only the affected feature after a mutation.
- Poll only active jobs or campaigns; stop polling after a terminal status.
- Preserve loaded screens during tab navigation and show a lightweight refreshing state instead of clearing existing data.
- Do not cache sensitive generated message previews longer than necessary.

## Implementation Order

1. Add isolated routes and feature module shells after backend contracts are accepted.
2. Build Prospect Hub read-only list and detail drawer.
3. Add networking campaign preview and preview-mode progress.
4. Enable real actions only after backend safety controls and live tests pass.
5. Build analytics once snapshots and the period API contain real data.
6. Build content workflow and drafts.
7. Add article extraction/generation.
8. Add the carousel editor, deterministic templates, and browser PDF download.
9. Add image jobs and asset library.
10. Add scheduling only after actual publishing is available.

## Frontend Acceptance Criteria

- Existing pages retain their current routes, state, and API behavior.
- Each new area has its own top-level tab, route, module, API client, and query state.
- Prospect Hub does not perform cross-post aggregation in the browser.
- Networking always shows eligibility and preview before a real write.
- Long-running operations use backend job progress and terminal states.
- Analytics never displays fabricated historical values.
- Draft status is backed by a content record, not inferred from a thread timestamp.
- Article, carousel, image, and schedule errors are specific and recoverable.
- Responsive layouts do not overlap, truncate commands, or hide critical status.

## Limitations to Communicate in the UI

- LinkedIn automation can fail after UI changes or authentication challenges.
- Automatic actions are scheduled polling, not real-time events.
- Some engagers, repost identities, profile views, or analytics may be unavailable.
- Connection degree can be stale until the profile/engagement data is refreshed.
- A campaign can partially succeed; each recipient has an independent result.
- Article pages behind access controls cannot be extracted.
- Scheduling is unavailable until a real LinkedIn publishing method is approved.

## Change Scope

The new screens use separate routes, components, and API calls. Existing creator, Ready to Comment, generation, comment, history, and dashboard behavior was not rewritten to support them.
