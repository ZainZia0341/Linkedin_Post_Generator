# Sixth Plan Draft Fixes

This file tracks the fixes and additions requested after the first FastAPI test pass.

## Problems Found

- The OpenAPI examples for `/posts/generate` and `/posts/modify` expose `provider`,
  `model`, and `api_key`, so Swagger sends placeholder values like `"string"`.
- Those placeholder values are treated as real LLM config and produce errors such as
  `Unsupported provider 'string'`.
- LLM API keys are available in `.env`, but the LLM resolver only checks process
  environment variables for provider keys.
- The post-search fallback adds generic software-development context even when the
  user idea does not mention software development.
- `generation_style` is unclear: it currently behaves like a loose writing-style
  variation, but the intended use is one selected post creation style.
- `topic_source` is unclear in the docs and request schema.
- Burner-profile LinkedIn scraping can fail for multiple creators because a
  persistent browser profile cannot be opened in parallel.
- There is no API yet for AI-generated comments on saved creator posts.
- There is no API yet for marking creator posts as commented.
- There is no API yet for listing creator posts that have already been commented on.

## Fixes To Make

- Use provider, model, and API key from config or `.env` for post generation,
  creator-activity generation, post modification, brainstorming, and comment
  generation.
- Keep manual provider/model/api key input only on `/llms/test-key`.
- Change the default configured LLM to Gemini with `gemini-3.1-flash-lite`.
- Make `.env` provider keys work even when they are not exported into the shell.
- Remove provider/model/api_key fields from content-generation request schemas.
- Add clearer schema descriptions and examples for:
  - `idea`: the topic or instruction to create a post about.
  - `generation_style`: one post creation template such as
    `Create a controversial post about a topic`.
  - `topic_source`: tracking metadata for where the idea came from, defaulting to
    `manual`.
- Add post creation style prompts for:
  - `Create posts from scratch`
  - `Create a post about a topic`
  - `Create a controversial post about a topic`
  - `Create a top mistakes post about a topic`
  - `Create a daily routine post about a topic`
  - `Create a how to start post about a topic`
  - `Create a motivational post about a topic`
  - `Create a skills to become successful post about a topic`
  - `Create a do's and don'ts post about a topic`
- Pass the selected generation style into the post-generation graph so the LLM gets
  a concrete style/template instruction.
- Improve deterministic Tavily fallback queries so they use the actual topic text
  and avoid injecting software-development terms unless the topic asks for them.
- Run scraper requests sequentially when `LINKEDIN_AUTOMATION_MODE=burner`, while
  keeping parallel scraping available for non-persistent logged-out mode.
- Add an AI comment generation endpoint that accepts `user_id`, `creator_id`,
  `post_id`, and `comment_topic`, then generates a short LinkedIn comment from the
  saved creator post.
- Add comment topics based on the UI idea: `Add Value`, `Congratulate`, `Agree`,
  `Disagree`, `Challenge`, and `Expert Insight`.
- Store generated comment metadata on the existing creator activity record.
- Add a separate endpoint to mark or unmark a saved creator post as commented.
- Add a list endpoint that returns creator posts marked as commented, with a
  default limit of 10 and an adjustable `limit` query parameter.
- Add targeted tests for the new request schemas, config fallback, search query
  behavior, scraper worker behavior, and comment engagement flow.

## Notes

- `topic_source` is not a prompt style. It is tracking metadata for analytics and
  filtering, for example `manual`, `brainstorm`, or `creator_activity`.
- `generation_style` should be a post creation action, not an API provider/model
  value and not the API key.
- If the LLM planner fails, Tavily queries come from deterministic Python fallback
  code. Bad fallback queries are a code issue, not proof that the AI is choosing
  poor searches.
