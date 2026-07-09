"""
# Second Plan Draft

This file keeps the requested `second_plan_draft.py` name while using a
Markdown-style Python docstring so it remains valid Python.

## Source Review

- The referenced `docs/first_plan_draft.py` did not exist. The actual plan file
  is `docs/first_plan_draft.md`.
- The existing app modules were mostly empty placeholders, so this pass created
  the first working implementation rather than only adjusting existing logic.
- The requested stack is now represented in the project: Python, Streamlit,
  LangChain, LangGraph, Groq/Gemini/Claude wrappers, Tavily search integration,
  Pydantic structured schemas, local JSON storage, pytest fixtures, and Docker.

## Implemented Flow

1. User configures provider, model, and API key in the Streamlit sidebar.
2. User tests the API key before starting a new chat.
3. New chat creates a local JSON session with a `chat1`, `chat2`, etc. name.
4. User either pastes a previous LinkedIn post for style extraction or selects
   one of three built-in styles.
5. User optionally uploads/pastes resume data. The app extracts profile details
   and allows JSON editing before saving.
6. User chooses between:
   - Generate a LinkedIn post from a topic.
   - Research trending topic ideas based on saved profile details.
7. Topic generation runs the LangGraph workflow:
   - memory checker
   - Tavily web research when `TAVILY_API_KEY` is present
   - structured post generation
   - structured post review
   - retry up to `MAX_REVIEW_ATTEMPTS`
8. Chat edit mode runs the LangGraph workflow:
   - memory checker
   - guardrail classifier
   - hard-coded off-topic reply when blocked
   - structured post modification when allowed
   - structured review with retry cap
9. Local sessions preserve chat state, current post, style JSON, resume JSON,
   workflow step, search results, and review metadata.

## What Was Added

- `app/config.py`: app constants, provider model lists, local DB paths, built-in
  writing styles, and runtime defaults.
- `app/llms/`: provider factories and structured output helper with deterministic
  fallback when no API key is available.
- `app/writing_style_extract.py`: structured style extraction plus offline
  heuristic fallback.
- `app/extract_resume_details.py`: PDF/text resume extraction plus structured
  profile fallback.
- `app/storage.py`: local JSON session storage in `schema/local_db`.
- `app/graph_state.py`, `app/conditional_edges.py`, and `app/nodes/`: LangGraph
  workflow for generation and chat edits.
- `app/deep_research_agent.py`: official Deep Agents implementation using
  `from deepagents import create_deep_agent`, a Tavily search tool, webpage
  fetching with `httpx`, HTML-to-Markdown conversion with `markdownify`, a
  research sub-agent, and source-backed final report extraction.
- `app/langchain_deep_search.py`: research helper for the second card. It now
  tries the official Deep Agents workflow first when an LLM key and Tavily key
  are available, then converts the report into the existing `ResearchResults`
  UI schema. If Deep Agents cannot run, it falls back to the local focused-task
  planner so the app remains usable. Fallback results are explicitly labeled
  with `research_engine` and `status_message`.
- `app/travily_tool.py`: shared Tavily search tool module. It reads
  `TAVILY_API_KEY`, binds `TavilySearch` to the selected chat model for search
  planning, and runs multiple Tavily searches before post generation or allowed
  post edits.
- `app/post_formatting.py`: adaptive LinkedIn post formatter and formatting
  validator. It keeps short posts compact, allows longer posts when the topic
  needs depth, separates paragraphs with blank lines, and keeps relevant
  hashtags on the final line.
- `streamlit_ui/app.py`: full Streamlit UI matching the requested sidebar and
  step-by-step main workflow.
- `test/test_data/`: sample previous post, resume text, and topic.
- `test/test_responses/`: expected fixture outputs.
- `test/test_scripts/test_core_workflow.py`: offline tests for extraction,
  storage, graph generation, guardrail blocking, and research fallback.
- `Testing.ipynb`: graph visualization cell using
  `graph.get_graph().draw_mermaid_png()`.
- `dockerFile` and `Dockerfile`: Streamlit container setup for port `7860`.
- `example.env`: reorganized into sections and extended with app/runtime/search
  variables.

## Structured Output Usage

Every LLM-facing operation uses a Pydantic schema:

- `WritingStyle`
- `ResumeProfile`
- `GuardrailDecision`
- `GeneratedPost`
- `PostReview`
- `ResearchResults`

When no key is available or an API call fails, the app prints the failure and
uses deterministic local fallback logic. This keeps tests runnable without paid
or live API calls.

## Local Storage

Current storage is JSON-file based:

- Index: `schema/local_db/sessions_index.json`
- Sessions: `schema/local_db/sessions/{session_id}.json`

Raw API keys are not saved in session JSON. The UI keeps the key in Streamlit
session state and stores only provider/model in local chat records.

## Console Output

The implementation uses `print()` for workflow visibility, as requested. It does
not configure Python logging.

## Tests and Edge Cases Covered

- Empty/no-key LLM fallback path.
- Empty/no-key Tavily fallback path.
- Multi-query search planning for niche/current terms.
- Adaptive formatting checks for wall-of-text posts, overly long paragraphs,
  and hashtag placement.
- String boolean coercion for structured outputs from models that return
  `"false"` instead of `false`.
- Official Deep Agents availability and fallback behavior.
- Fallback research output grouping so source snippets do not show as raw
  findings such as `Tavily answer`.
- Built-in writing styles.
- Previous-post style extraction.
- Resume text extraction.
- Local storage create/update/load/list lifecycle.
- Topic-to-post graph execution without external APIs.
- Off-topic chat message blocked by the guardrail.
- Research card asking for more details when no profile exists.
- Research fallback returning topic ideas when details are supplied.

## Limitations

- Live trend quality depends on `TAVILY_API_KEY`. Without it, the app returns
  safe placeholder research angles and asks the user to verify facts.
- Model names can change at provider side. The UI provides curated defaults, but
  provider availability should be checked during API-key testing.
- Resume PDF extraction depends on embedded text. Scanned image PDFs need OCR,
  which is not implemented in this pass.
- Local JSON storage is suitable for local/HuggingFace prototype use, but it is
  not multi-user production storage. The structure is ready to replace later
  with MongoDB or DynamoDB.
- API keys are not persisted by design, so a returning user may need to re-enter
  the key in the sidebar.
"""
