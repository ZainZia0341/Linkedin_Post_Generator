# Comments And Post Generation Backend Plan

## Goal

Support the new comment generation/editor flow and the simplified post
generation flow with backend-first APIs. The frontend should send explicit
controls instead of hiding them inside prompt text.

## Implemented API Changes

### Generate Comment

Endpoint:

```text
POST /comments/generate
```

Request now supports:

```json
{
  "user_id": "test-user-1",
  "creator_id": "creator-id",
  "post_id": "urn:li:activity:123",
  "style": "Add Value",
  "tone": "Professional",
  "length": "Medium"
}
```

Supported comment styles:

- Add Value
- Congratulate
- Agree
- Disagree
- Challenge
- Expert Insight

Supported lengths:

- Short
- Medium
- Long

Supported tones include:

- Professional
- Casual
- Friendly
- Direct
- Thoughtful

Backward compatibility:

- `comment_topic` still exists as a legacy alias.
- New clients should send `style`, `tone`, and `length`.

Response now includes:

```json
{
  "thread_id": "comment-thread-id",
  "style": "Add Value",
  "tone": "Professional",
  "length": "Medium",
  "comment": "Generated comment text"
}
```

Every generated comment creates a normal thread record in the existing threads
table with:

```json
{
  "topic_source": "comment_generation",
  "source": {
    "type": "comment",
    "creator_id": "...",
    "post_id": "...",
    "comment_style": "...",
    "tone": "...",
    "length": "..."
  }
}
```

### Modify Comment

Endpoint:

```text
POST /comments/modify
```

Request:

```json
{
  "user_id": "test-user-1",
  "thread_id": "comment-thread-id",
  "modification_message": "Make this sound more conversational.",
  "style": "Add Value",
  "tone": "Casual",
  "length": "Medium"
}
```

Behavior:

- Loads the existing comment thread.
- Verifies that the thread source is `type: comment`.
- Loads the original creator activity for context.
- Sends the current comment, conversation history, creator post, style, tone,
  and length to the LLM.
- Updates the thread `current_post`, conversation, modification count, and
  modified timestamp.
- Updates the saved activity engagement comment so history/mark-comment flows
  use the latest comment.

### Thread Detail

Existing endpoint reused by the drawer:

```text
GET /users/{user_id}/threads/{thread_id}
```

This works for comment threads because comment edits now reuse the same thread
table as post generation.

### Generate Post

Endpoint:

```text
POST /posts/generate
```

Request now supports:

```json
{
  "user_id": "test-user-1",
  "idea": "AI agents for SaaS automation",
  "post_length": "Medium",
  "tone": "Professional",
  "writing_style": "Clear Builder",
  "topic_source": "manual"
}
```

The endpoint no longer accepts a post template field in the request body.

Generation instructions now explicitly tell the post graph:

- requested post length
- requested tone
- requested writing style
- do not use a CTA template
- do not follow a prebuilt post template

## Prompting Changes

Comment generation prompt now receives:

- creator post
- comment style
- tone
- length
- user profile

Comment modification prompt now receives:

- creator post
- current comment
- user edit request
- conversation history
- comment style
- tone
- length
- user profile

Post generation prompt now receives the new generation controls instead of a
frontend-selected template.

## Acceptance Criteria

- FastAPI docs show `style`, `tone`, and `length` on comment generation.
- Comment generation returns a `thread_id`.
- `POST /comments/modify` can revise a generated comment using that thread id.
- `GET /users/{user_id}/threads/{thread_id}` returns comment thread details.
- FastAPI docs show `post_length`, `tone`, and `writing_style` on post
  generation.
- Comment mark/history still use the latest generated or modified comment.

## Next Backend Work

- Add server-side filtering so thread lists can exclude comment threads from the
  post draft sidebar if needed.
- Persist multiple comment variants per activity instead of keeping only the
  latest activity-level comment pointer.
- Add action execution endpoints for actually posting/sending comments later.
