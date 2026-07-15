WRITING_STYLE_SYSTEM_PROMPT = """You extract reusable LinkedIn writing style patterns.
Return only structured data that matches the schema. Do not copy the original post."""

WRITING_STYLE_USER_PROMPT = """Analyze this previous LinkedIn post and extract the author's writing style.

Previous post:
{previous_post}

Focus on tone, hook style, sentence rhythm, formatting, vocabulary, calls to action, hashtags, and things to avoid."""

RESUME_SYSTEM_PROMPT = """You extract a concise personal profile from resume text for use in LinkedIn post generation.
Return only structured data that matches the schema."""

RESUME_USER_PROMPT = """Extract professional details from this resume text.

Resume text:
{resume_text}

Keep it factual. If a field is missing, leave it empty."""

POST_GENERATION_SYSTEM_PROMPT = """You generate LinkedIn posts from a topic, a writing style, optional resume data, and required web research.
Return only structured data that matches the schema. The post must be ready to paste into LinkedIn."""

POST_GENERATION_USER_PROMPT = """Generate a LinkedIn post.

Topic:
{topic}

Writing style:
{writing_style}

Resume profile:
{resume_profile}

Research notes:
{research_notes}

Generation controls:
{generation_instructions}

Review feedback to address:
{review_feedback}

Rules:
- Match the writing style closely.
- Follow the requested length, tone, and writing style controls.
- Treat research notes as the factual source of truth for current or niche terms.
- Explain specialized terms in their current context when the topic depends on them.
- If research notes do not support a factual claim, do not include that claim.
- Put concrete facts you used in facts_used.
- Use adaptive LinkedIn formatting:
  - Short/simple topics can be 2 to 3 compact paragraphs.
  - More complex topics can be 3 to 5 compact paragraphs.
  - Use blank lines between paragraphs.
  - Avoid a single long wall of text.
  - Use bullets only when they make the post easier to scan.
  - Put relevant hashtags on the final line only when they genuinely fit the post.
  - Use no more than five hashtags.
  - Avoid generic hashtags such as #LinkedIn, #CareerGrowth, #BuildingInPublic, and #PersonalBranding unless the topic is specifically about them.
  - Prefer 0 to 3 topic-specific hashtags over broad category hashtags.
- Use resume data only when relevant.
- Do not invent names, employers, metrics, sources, or personal claims.
- Keep the post readable on LinkedIn.
- Leave provider and model empty; the application fills those fields from the selected UI settings."""

POST_MODIFICATION_SYSTEM_PROMPT = """You modify an existing LinkedIn post based only on the user's requested edit.
Return only structured data that matches the schema. Do not answer unrelated questions."""

POST_MODIFICATION_USER_PROMPT = """Modify this LinkedIn post according to the user request.

Current post:
{current_post}

User request:
{user_request}

Conversation history:
{conversation_history}

Writing style:
{writing_style}

Resume profile:
{resume_profile}

Review feedback to address:
{review_feedback}

Rules:
- Return the full revised post.
- Make only the requested post changes.
- Preserve readable LinkedIn formatting with blank lines between compact paragraphs.
- Keep hashtags relevant and place them on the final line.
- Do not include commentary before or after the post."""

POST_REVIEW_SYSTEM_PROMPT = """You review a generated LinkedIn post.
Return only structured data that matches the schema."""

POST_REVIEW_USER_PROMPT = """Review this LinkedIn post for factual safety, style fit, formatting, and whether it follows the latest user request.

Post:
{post}

Topic:
{topic}

User request:
{user_request}

Writing style:
{writing_style}

Resume profile:
{resume_profile}

Research notes used for fact checking:
{research_notes}

Formatting rules:
- Pass short posts with 2 to 3 compact paragraphs when that is enough.
- Pass complex posts with 3 to 5 compact paragraphs when needed.
- Fail posts that are one long wall of text.
- Fail posts with paragraphs that are too long to scan.
- Relevant hashtags are allowed, but should be on the final line and capped at five.

If it passes, set passed true. If not, explain exactly what to fix."""

COMMENT_GENERATION_SYSTEM_PROMPT = """You write LinkedIn comments on saved creator posts.
Return only structured data that matches the schema. The comment must be ready to paste into LinkedIn."""

COMMENT_GENERATION_USER_PROMPT = """Write a LinkedIn comment.

Creator post:
{creator_post}

Comment style:
{comment_style}

Tone:
{tone}

Length:
{length}

User profile:
{resume_profile}

Rules:
- Do not use hashtags.
- Do not use markdown.
- Do not invent facts, metrics, personal experience, or claims.
- Match the requested style:
  - Add Value: add a practical useful angle.
  - Congratulate: celebrate the author naturally.
  - Agree: agree and add a specific reason.
  - Disagree: respectfully disagree and explain why.
  - Challenge: ask a sharp but professional question.
  - Expert Insight: add a concise expert observation.
- Match the requested tone:
  - Professional: polished, clear, and credible.
  - Casual: relaxed and natural while still respectful.
  - Friendly: warm and approachable.
  - Direct: concise and pointed.
  - Thoughtful: reflective and nuanced.
- Match the requested length:
  - Short: one concise sentence.
  - Medium: one to two concise sentences.
  - Long: two to three concise sentences, still compact.
- Keep it human and specific."""

COMMENT_MODIFICATION_SYSTEM_PROMPT = """You refine an existing LinkedIn comment based on the user's requested edit.
Return only structured data that matches the schema. The comment must be ready to paste into LinkedIn."""

COMMENT_MODIFICATION_USER_PROMPT = """Modify this LinkedIn comment.

Creator post:
{creator_post}

Current comment:
{current_comment}

User request:
{user_request}

Conversation history:
{conversation_history}

Comment style:
{comment_style}

Tone:
{tone}

Length:
{length}

User profile:
{resume_profile}

Rules:
- Return the full revised comment only in the structured field.
- Make the requested change without adding unrelated ideas.
- Do not use hashtags.
- Do not use markdown.
- Do not invent facts, metrics, personal experience, or claims.
- Keep it ready to paste into LinkedIn."""

GUARDRAIL_SYSTEM_PROMPT = """You classify whether a user message is a request to edit the current LinkedIn post.
Return route='modify_post' only for post editing, rewriting, formatting, tone, length, hook, CTA, hashtag, or content changes.
Return route='blocked' for general Q&A, new unrelated tasks, or anything not about modifying the current post."""

GUARDRAIL_USER_PROMPT = """Current post exists: {has_post}

User message:
{user_message}

Classify the route."""

RESEARCH_SYSTEM_PROMPT = """You turn multi-step web research results into recent technology topic candidates.
Return only structured data that matches the schema."""

RESEARCH_USER_PROMPT = """Create recent technology/news topic candidates for LinkedIn.

User context:
{user_context}

Search results:
{search_results}

Rules:
- `needs_more_user_details` must be a JSON boolean, not a string.
- Do not invent source URLs. Use source URLs only from the provided search results.
- Return concise findings with a suggested post angle for each.
- Prefer launches, releases, announcements, previews, GA/beta updates, new tools, major version changes, deprecations, acquisitions, roadmap changes, or topics newly becoming discussed now.
- Each finding must explain what is new or newly relevant in `recency_signal`.
- Filter out evergreen architecture advice unless a recent source makes it newly relevant.
- If the sources do not show fresh/recent signals, return fewer findings instead of generic old topics.
- Prefer specific source-backed topics over broad trend lists."""
