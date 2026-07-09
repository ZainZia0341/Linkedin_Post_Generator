from app.llms.llm import LLMConfig

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def build_gemini_config(api_key: str = "", model: str = DEFAULT_GEMINI_MODEL) -> LLMConfig:
    return LLMConfig(provider="gemini", model=model, api_key=api_key)
