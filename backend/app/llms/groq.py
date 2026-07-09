from app.llms.llm import LLMConfig

DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


def build_groq_config(api_key: str = "", model: str = DEFAULT_GROQ_MODEL) -> LLMConfig:
    return LLMConfig(provider="groq", model=model, api_key=api_key)
