from app.llms.llm import LLMConfig

DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-5"


def build_claude_config(api_key: str = "", model: str = DEFAULT_CLAUDE_MODEL) -> LLMConfig:
    return LLMConfig(provider="claude", model=model, api_key=api_key)
