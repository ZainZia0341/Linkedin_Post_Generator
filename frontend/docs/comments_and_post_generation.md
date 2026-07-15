# Comments And Post Generation Frontend Plan

## Goal

Update the comment generation workspace, AI comment editor drawer, Ready to
Comment cards, and Generate screen to match the new backend API controls.

## Implemented UI Changes

### Ready To Comment Cards

- Added the `Generate Comment` button back to scraped post cards.
- Clicking it opens:

```text
/comments/generate?creator_id=...&post_id=...
```

### Comment Generation Workspace

The workspace keeps the existing target-post card and comment variation grid.

Controls now send real backend payload fields:

- `style`
- `tone`
- `length`

Style options:

- Add Value
- Congratulate
- Agree
- Disagree
- Challenge
- Expert Insight

Tone options:

- Professional
- Casual
- Friendly
- Direct
- Thoughtful

Length options:

- Short
- Medium
- Long

Removed/kept out:

- No final workspace section is created.
- Comment editing happens through the right-side AI editor drawer.

### Comment Variations

Each generated variation stores:

- comment text
- style label
- tone
- length
- backend `thread_id`

The pencil button opens the editor drawer with the variation's `thread_id`.

### AI Comment Editor Drawer

The drawer now uses backend comment-thread editing instead of local placeholder
suggestions.

Behavior:

- On open, it calls existing thread detail API:

```text
GET /users/{user_id}/threads/{thread_id}
```

- Custom improve input calls:

```text
POST /comments/modify
```

- Preset buttons also call `POST /comments/modify`.
- The updated comment is written back into the visible variation card.
- Save/mark actions continue to use the existing comment mark endpoint.

### Generate Post Screen

Removed:

- Post type/template dropdown.
- Any template-style dependency from the UI payload.

Kept controls:

- Topic
- Writing style
- Tone
- Length

Post generation payload now sends:

```json
{
  "user_id": "test-user-1",
  "idea": "topic text",
  "post_length": "Medium",
  "tone": "Professional",
  "writing_style": "Clear Builder",
  "topic_source": "manual"
}
```

No CTA style control is shown.

## Files Touched

- `frontend/components/PostsScrapingView.tsx`
- `frontend/components/CommentGenerationView.tsx`
- `frontend/components/CommentEditorDrawer.tsx`
- `frontend/components/GeneratePostView.tsx`
- `frontend/lib/api.ts`
- `frontend/lib/types.ts`
- `frontend/lib/constants.ts`
- `frontend/app/globals.css`

Backend support files:

- `backend/app/api/schemas.py`
- `backend/app/api/main.py`
- `backend/app/api/services.py`
- `backend/app/llms/prompts.py`
- `backend/test/test_scripts/test_fastapi_services.py`

## Acceptance Checks

- Ready to Comment card shows `Generate Comment`.
- Comment generation requests include `style`, `tone`, and `length`.
- Pencil opens the right-side editor drawer.
- Drawer improve actions call `POST /comments/modify`.
- Drawer loads latest comment state from the thread detail endpoint.
- Final workspace is not rendered.
- Generate Post screen has no post template dropdown and no CTA style control.
- Generate Post requests include `post_length`, `tone`, and `writing_style`.
