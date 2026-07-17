# 17 July Backend Plan: Taplio Feature Gap Closure

## Purpose

This document compares the requested Taplio-style features with the backend, records the 17 July implementation, and keeps the remaining production work explicit.

## 17 July Implementation Update

Implemented additively without creating a new DynamoDB table:

- Advanced post-builder generation with variation, format, tone, angle, structure, length, and draft-count inputs.
- Safe public article extraction with redirect, private-network, content-type, response-size, and readable-body checks.
- Four-stage content items (`idea`, `in_progress`, `ready`, `published`) stored in existing thread records.
- Account-wide Prospect Hub aggregation from the existing embedded own-post engager records.
- Structured carousel generation, manual creation, listing, editing, and persistence through a reserved existing activity partition. Carousel slides are text documents rendered with deterministic frontend templates.
- Gemini image generation from post context and a selected style through the configurable `GEMINI_IMAGE_MODEL`, with local development asset storage and metadata in a reserved existing activity partition.
- Image listing, serving, and deletion APIs.

The existing synchronous LinkedIn post sync, engager scrape, reply, connection request, DM, and action-log APIs were preserved. Analytics history, campaign workers, server-side carousel rendering, scheduling, and real LinkedIn publishing remain future work for the reasons documented below. The frontend can download a multi-page PDF from the saved structured slides without generating slide images.

## Safety Guardrails

- Keep every currently working endpoint and response contract unchanged.
- Build new functionality through additive services, routes, fields, and workers.
- Keep the existing creator post scraper and creator profile scraper independent from the experimental own-post networking APIs.
- Do not enable automatic LinkedIn write actions until dry-run, eligibility checks, idempotency, limits, and durable job tracking are complete.
- Treat LinkedIn selectors as replaceable configuration because the DOM changes frequently.
- Prefer official LinkedIn publishing and analytics APIs when approved access is available. Playwright remains a less stable fallback.

## Current Backend Inventory

### Implemented and in current use

| Capability | Current status | Notes |
| --- | --- | --- |
| Post generation | Implemented | Supports length, tone, writing style, thread creation, and refinement. |
| Post idea brainstorming | Implemented in backend | The endpoint exists even if its current frontend navigation is not enabled. |
| Comment generation | Implemented | Generated comments and comment threads are stored. |
| Comment refinement | Implemented | Chat-like modification is supported through thread-aware APIs. |
| Similar posts from creator activity | Implemented | Uses scraped creator activity as generation context. |
| Creator management | Implemented | Add, import, list, update, and delete operations exist. |
| Creator post scraping | Implemented | Supports selected or all creators and asynchronous scrape-job status. |
| Creator profile scraping | Implemented | Supports selected or all creators and asynchronous scrape-job status. |
| Scrape result export | Implemented | Existing scraped post data can be exported. |

### Experimental own-post and networking foundation

The following backend endpoints already exist and should be preserved while they are hardened:

| Endpoint | What it currently does | Remaining gap |
| --- | --- | --- |
| `POST /linkedin/posts/publish` | Tracks metadata for an already published LinkedIn post. | Despite its name, it does not publish a post to LinkedIn. Rename only through a future alias, not by breaking this route. |
| `POST /linkedin/posts/sync-recent` | Scrapes recent posts from the user's LinkedIn profile and stores tracked own posts. | Selector hardening, async execution, pagination, and reliable diagnostics. |
| `GET /users/{user_id}/linkedin/posts` | Lists tracked own posts with source and time filters. | Cursor pagination and richer analytics fields. |
| `POST /linkedin/posts/{post_id}/engagement/scrape` | Scrapes visible commenters and reaction dialog members for one tracked post. | Async execution, load-more coverage, repost handling, and durable progress. |
| `GET /linkedin/posts/{post_id}/engagers` | Lists stored engagers for one post. | Account-wide aggregation is available separately; cursor pagination remains future work. |
| `GET /users/{user_id}/linkedin/prospects` | Deduplicates stored engagers across tracked posts for Prospect Hub. | Production-scale indexing, cursor pagination, and enrichment remain future work. |
| `POST /linkedin/actions/comment-replies` | Replies to selected stored commenters. | One shared reply, synchronous execution, and no scheduled policy engine. |
| `POST /linkedin/actions/connection-requests` | Sends connection requests to selected profiles or engagers. | Needs campaign jobs, caps, approval preview, and better targeting. |
| `POST /linkedin/actions/dms` | Sends one message to selected profiles or eligible first-degree engagers. | No per-person personalization and no durable campaign progress. |
| `GET /users/{user_id}/linkedin/action-logs` | Returns sent, skipped, and failed action history. | Cursor pagination, campaign grouping, and long-term retention policy. |

### Current persistence behavior

- Own LinkedIn posts are stored in the existing activity storage under a reserved own-post creator identity.
- Engagers and action logs are embedded with the tracked own-post metadata.
- A person is deduplicated within a post and can contain multiple engagement types such as `like` and `comment`.
- Account-wide action-log checks are used to avoid repeating some actions to the same profile.
- No new table is required for a small experimental MVP.
- Embedded per-post storage will become inefficient for an account-wide Prospect Hub, long analytics history, campaign pagination, and concurrent workers. A normalized store should therefore be approved before production scale. This can be a new table or an agreed indexed record pattern in an existing table.

## Requested Feature Assessment

| Requested feature | Assessment | Backend work still required |
| --- | --- | --- |
| Send connection request to people who liked or commented | Partial, experimental | Existing endpoint works from stored engagers. Add campaign preview, durable queue, limits, progress, and cross-post selection. |
| Auto DM post engagers | Partial, experimental | Existing endpoint sends a shared DM. Add first-degree eligibility refresh, personalization, campaign jobs, and an approval policy. |
| Auto reply to post comments | Partial, experimental | Existing endpoint replies to selected commenters. Add polling policy, per-comment templates, progress, and idempotent scheduling. |
| Personalized DMs in bulk | Not implemented | Add recipient variable rendering, per-recipient preview, approval, campaign execution, and result logs. |
| Add the right people to the network in bulk | Partial | Batch connection exists, but there is no definition or ranking of the "right" people. Add explicit filters/scoring and campaign controls. |
| Prospect Hub of likers/commenters | Implemented for stored engager data | Account-wide aggregation now deduplicates existing per-post engager records. Cursor pagination and normalized production storage remain future work. |
| 7/30/90 day analytics | Not implemented as history | Some latest post counts can be stored, but there are no periodic snapshots or historical series. |
| Carousel generator | Structured editor backend implemented | Manual and AI-assisted slide documents are complete. The frontend provides deterministic templates and browser PDF download; server-side render jobs remain. |
| Generate post from article or URL | Implemented | Secure extraction feeds the advanced builder. Protected/paywalled pages remain unsupported. |
| Draft/in-progress/ready workflow | Implemented as an MVP | Existing thread records now support additive content statuses. Scheduling and version-conflict handling remain. |
| Generate image for a post | Development implementation complete | Gemini generation and local asset serving are available. Production needs object storage, quotas, and async jobs. |
| Schedule and publish to LinkedIn | Not implemented | The existing `publish` endpoint only tracks a post. Real publishing needs approved API access or a separately accepted Playwright risk. |

## Phase 1: Stabilize Existing Experimental Networking APIs

### 1.1 Selector and extraction hardening

- Centralize all own-post, reaction-dialog, comment, reply, connection, and DM selectors in one module.
- Prefer role, accessible name, `aria-*`, `data-*`, stable URNs, and canonical URLs over generated CSS classes.
- Record selector-stage diagnostics such as page opened, post located, reaction dialog opened, comments expanded, and targets extracted.
- Return a warning when visible aggregate counts are non-zero but extracted people are zero.
- Continue deduplicating people by stable profile URN first and canonical profile URL second.
- Keep a comment's stable URN/permalink when available. Use text hash plus author and timestamp only as a fallback.

### 1.2 Durable jobs

Convert long-running own-post operations into additive job APIs while preserving the current synchronous endpoints during migration:

- `POST /linkedin/jobs/post-sync`
- `POST /linkedin/jobs/engagement-scrape`
- `POST /linkedin/jobs/actions`
- `GET /linkedin/jobs/{job_id}`
- `POST /linkedin/jobs/{job_id}/cancel`

Each job response should include:

- `job_id`, `job_type`, `status`, `created_at`, `started_at`, `completed_at`
- `total_targets`, `processed_targets`, `succeeded`, `skipped`, `failed`
- current post/profile identifier
- warnings and per-target errors
- result summary and action-log references

For local development an existing job record pattern can be reused. For production, use a durable queue and worker such as SQS plus a worker service. In-memory tasks are not reliable across restarts, multiple server processes, or serverless execution.

### 1.3 Shared account safety controls

- One serial action queue per LinkedIn account.
- Configurable hourly and daily limits across replies, DMs, connections, and read scraping.
- Randomized delay ranges rather than one fixed delay.
- Cooldown after challenge, login failure, rate warning, or unexpected page state.
- Idempotency key on campaign creation and each recipient action.
- Do not retry ambiguous write failures automatically. Verify outcome first.
- Keep `dry_run: true` as the default for all new write-action APIs.
- Store a reason for every skipped recipient.

## Phase 2: Prospect Hub

### 2.1 Account-wide prospect endpoint

Add an aggregated endpoint without changing the current per-post endpoint:

`GET /users/{user_id}/linkedin/prospects`

Suggested query fields:

- `engagement_type=like|comment|repost`
- `connection_degree=1st|2nd|3rd|unknown`
- `post_id`
- `engaged_from`, `engaged_to`
- `action_status=never_contacted|contacted|failed|skipped`
- `search`
- `cursor`, `limit`

Suggested prospect response fields:

- stable `prospect_id`, profile URN, canonical profile URL
- name, headline, connection degree, profile image when available
- merged engagement types and total engagement count
- source post IDs and post excerpts
- first and last engagement timestamps
- latest comment text and stable comment reference when available
- DM, reply, and connection eligibility
- latest action status and action-log summary

### 2.2 Storage decision

For a small data set, the endpoint may scan and merge the existing embedded engager maps. This avoids a migration but will not scale well. Before production, create an indexed prospect representation because account-wide scans will become slow and expensive.

The production representation should support:

- one prospect per user account and stable LinkedIn identity
- many source posts per prospect
- engagement and action history
- cursor pagination
- atomic eligibility/cooldown updates

This is additive and does not require removing existing embedded data. A backfill can copy current engagers into the normalized representation.

### 2.3 Reposts limitation

Aggregate repost counts may be visible while the identities of people who reposted are not exposed in the current LinkedIn page. Prospect Hub can only list reposters when LinkedIn exposes a stable actor list in the authenticated UI. It must not invent actor identities from an aggregate count.

## Phase 3: Networking Campaigns

### 3.1 Preview before execution

Add a preview operation that performs no LinkedIn write:

`POST /linkedin/action-campaigns/preview`

It should return eligible and skipped recipients with reasons such as:

- already first-degree
- not first-degree for DM
- connection request already sent
- action already performed
- missing profile URL
- missing stable comment reference
- outside campaign filters
- account limit reached

### 3.2 Campaign creation and status

- `POST /linkedin/action-campaigns`
- `GET /linkedin/action-campaigns/{campaign_id}`
- `GET /users/{user_id}/linkedin/action-campaigns`
- `POST /linkedin/action-campaigns/{campaign_id}/cancel`

Campaign types:

- `comment_reply`
- `connection_request`
- `dm`

Campaign input should accept prospect IDs and optional post filters. The worker should create one action record per recipient and reuse the existing low-level Playwright services.

### 3.3 Personalized bulk DMs

The existing DM endpoint sends one shared message. Personalized bulk DM needs a separate, reviewable flow:

1. Select eligible first-degree prospects.
2. Render a message per recipient from approved variables such as first name, headline, engagement type, comment excerpt, and post topic.
3. Return every rendered message for preview.
4. Require approval before execution.
5. Send through the account queue and log the final text and result.

Do not combine AI generation and sending into one unreviewed request. Unsupported or missing variables should produce a preview error, not malformed text.

### 3.4 Defining the "right people"

The backend cannot objectively know the right people without user-defined criteria. Add explicit filters and a transparent score, for example:

- engagement recency and frequency
- commenter versus liker
- connection degree
- allowed headline/role keywords
- location when available
- exclusion and cooldown lists

Return score components so the user can understand why a prospect qualifies. Do not use hidden or sensitive-attribute inference.

### 3.5 What "auto" requires

There is no reliable engagement webhook in the current scraper architecture. Automatic replies, DMs, or connections therefore require scheduled polling:

1. Periodically sync recent own posts.
2. Scrape engagement for changed/recent posts.
3. Upsert newly discovered prospects.
4. Evaluate an enabled user policy.
5. Create a dry-run or approval campaign, or execute only when explicit auto mode has been accepted.

The policy must store its schedule, last run, selected post scope, action type, eligibility rules, message template, limits, and enabled state.

## Phase 4: LinkedIn Analytics for 7, 30, and 90 Days

### 4.1 Metrics and definitions

- Followers count: profile-level snapshot.
- Impressions: sum or per-post series from LinkedIn post analytics where available.
- Reactions: latest count and delta per post.
- Comments: latest count and delta per post.
- Reposts: aggregate count when available.
- Engagement count: reactions + comments + reposts.
- Engagement rate: engagement count divided by impressions, with explicit zero handling.
- Profile views: profile-level metric only when visible to the authenticated account.
- Number of posts: tracked own posts published in the selected period.

### 4.2 Snapshot collection

Latest values alone cannot produce 7/30/90 day charts. Add periodic immutable snapshots:

- profile analytics snapshot, normally once per day
- own-post analytics snapshot for recent active posts
- scraper run metadata and warning state

Suggested APIs:

- `POST /linkedin/jobs/analytics-sync`
- `GET /users/{user_id}/linkedin/analytics?period=7d|30d|90d`
- `GET /users/{user_id}/linkedin/analytics/posts?period=30d&cursor=...`

The summary endpoint should return totals, period deltas, daily series, and data completeness warnings.

Analytics data must have at least 90 days of retention. It must not inherit the three-day retention rule used for scraped creator posts.

### 4.3 Analytics limitations

- Some metrics depend on account type, LinkedIn permissions, and what the authenticated UI exposes.
- Profile views may be partial or unavailable.
- DOM-based analytics can break when LinkedIn changes its page.
- Historical data cannot be reconstructed for dates before snapshots begin unless LinkedIn exposes those values.
- Official LinkedIn analytics APIs are the preferred long-term path but require approved products and scopes.

## Phase 5: Write, Asset, and Publishing Workflows

### 5.1 Content workflow records

Generation threads are conversations, not a complete publishing workflow. Add an additive content-item model associated with a thread:

- status: `draft`, `in_progress`, `ready`, `scheduled`, `published`, `failed`, `archived`
- title, current text, current revision, author/user
- source type and source metadata
- asset references
- scheduled time and timezone
- published post ID and URL
- created, updated, scheduled, and published timestamps

Suggested APIs:

- `POST /users/{user_id}/content-items`
- `GET /users/{user_id}/content-items?status=draft&cursor=...`
- `GET /users/{user_id}/content-items/{content_id}`
- `PATCH /users/{user_id}/content-items/{content_id}`
- `POST /users/{user_id}/content-items/{content_id}/status`
- `DELETE /users/{user_id}/content-items/{content_id}`

Use a revision/version field for optimistic concurrency so two edits do not silently overwrite each other.

### 5.2 Generate from an article or URL

Use a two-step flow:

1. `POST /content-sources/extract` validates and extracts a URL.
2. `POST /posts/from-source` generates from the approved extracted source.

Extraction requirements:

- allow only HTTP and HTTPS
- block local, private, metadata, and loopback addresses to prevent SSRF
- enforce redirect, timeout, response-size, and content-type limits
- extract title, author, publication date, canonical URL, and readable body
- preserve source attribution and extraction warnings
- do not bypass logins or paywalls
- reject unsupported documents cleanly

JavaScript-only, protected, or poorly structured pages may not be extractable. The user should be able to provide text manually as a fallback.

### 5.3 Carousel generator

Create a structured slide document first. AI may fill the text, but it must not generate a separate image for each slide:

- topic and source input
- slide count and format
- cover, content slides, and closing slide
- editable title/body/emphasis fields per slide
- one shared theme identifier for every slide
- deterministic frontend rendering and validation warnings

Suggested APIs:

- `POST /carousels`
- `POST /carousels/generate`
- `GET /carousels/{carousel_id}`
- `PATCH /carousels/{carousel_id}`

The current frontend renders the structured slides with one built-in template and downloads a multi-page PDF locally. A future server-side export service may store generated files in object storage when durable share links, background rendering, or high-volume export are required.

### 5.4 Image generation

- Add a provider-neutral image-generation service driven by post context plus one selected style.
- Run generation as an async job because provider latency can be high.
- Store prompt, provider, dimensions, status, cost metadata, safety result, and object-storage URL.
- Associate one or more assets with a content item or generation thread.
- Add per-user quotas and explicit error reporting.
- Do not store large image base64 strings in DynamoDB records.

Suggested APIs:

- `POST /image-jobs`
- `GET /image-jobs/{job_id}`
- `GET /users/{user_id}/assets`
- `DELETE /users/{user_id}/assets/{asset_id}`

### 5.5 Scheduling and real publishing

The current `POST /linkedin/posts/publish` endpoint records a post after publication; it does not publish it. Real scheduling requires:

- a durable scheduler and queue
- timezone-aware `scheduled_at`
- idempotent publish attempts
- retry rules and failure notifications
- storage of returned post ID and URL
- cancellation and rescheduling

The preferred method is the official LinkedIn publishing API after access and scopes are approved. Playwright publishing is technically possible but has higher selector, account, and policy risk and should be a separately approved implementation.

## Data and Migration Strategy

1. Preserve existing thread, activity, creator, profile, and experimental own-post records.
2. Add fields only with backward-compatible defaults.
3. Introduce normalized prospect, campaign, analytics snapshot, content item, and asset records only after their access patterns are approved.
4. Backfill existing own-post engagers into Prospect Hub records without deleting embedded engager data.
5. Version new response contracts and retain current experimental endpoint behavior until the new workers are verified.
6. Add cursor pagination to all growing collections.

Trying to force campaigns, 90-day time series, content assets, and cross-post prospects into a single embedded own-post object is possible only for a small demo. It is not a production-safe storage design because of item-size limits, scans, concurrent updates, and pagination requirements.

## Test and Rollout Plan

### Automated tests

- Unit tests for normalization, deduplication, eligibility, scoring, template rendering, and analytics calculations.
- Repository tests for pagination, conditional writes, idempotency, and backward compatibility.
- API contract tests for old and new endpoints.
- Worker tests for resume, cancellation, partial failure, and non-retryable ambiguous writes.
- Fixture-based selector tests using sanitized captured HTML.

### Controlled live tests

- Use a dedicated test LinkedIn account and small recipient sets.
- Run dry-run first, then one real action of each type.
- Verify the LinkedIn result after every write before increasing limits.
- Test login expiry, challenge pages, missing dialogs, duplicate actions, and interrupted browser sessions.

### Rollout order

1. Stabilize extraction and diagnostics.
2. Add durable jobs, limits, and idempotency.
3. Add Prospect Hub aggregation.
4. Add manual approved campaigns.
5. Add personalized DM previews.
6. Start daily analytics snapshots.
7. Add content workflow and URL extraction.
8. Add carousel and image jobs.
9. Add scheduling only after a publishing method is approved.
10. Consider automatic policies only after manual campaigns are reliable.

## Acceptance Criteria

- Existing production routes and current frontend flows continue to pass their tests unchanged.
- Prospect Hub returns one deduplicated person across multiple own posts.
- Every write action has preview, eligibility, idempotency, account limits, progress, and a durable log.
- Partial failures never report the entire campaign as successful.
- Analytics returns honest 7/30/90 day series and identifies missing data.
- URL extraction blocks unsafe destinations and preserves source information.
- Draft, carousel, and image records are independent from existing generation threads but can reference them.
- Actual publishing is not represented as implemented until a post is verifiably created on LinkedIn.

## Important Limitations Summary

- LinkedIn DOM automation is fragile and can stop working after a UI update.
- Automated actions can trigger LinkedIn restrictions and must remain rate-limited and user-controlled.
- True real-time auto actions are unavailable without an event source; this architecture uses scheduled polling.
- Repost actor identities may not be available even when a repost count is visible.
- DMs generally require an eligible messaging relationship; stored connection degree can become stale and should be rechecked.
- Profile views and some analytics may be unavailable for some accounts.
- Data collection starts when snapshot jobs are enabled; unavailable historical values cannot be invented.
- Article extraction cannot bypass paywalls, login pages, or access controls.
- LinkedIn publishing is not currently implemented by the endpoint named `publish`.

## Change Scope

The 17 July implementation is additive. Existing endpoint contracts and working scraper paths remain unchanged. The new MVP reuses current thread and activity records; production-scale campaigns, analytics, rendered files, and publishing still require the durable architecture described in this document.
