from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, SecretStr

from app.config import get_env_api_key
from app.llms.llm_structure_schema import ApiKeyCheck

SchemaT = TypeVar("SchemaT", bound=BaseModel)


@dataclass(slots=True)
class LLMConfig:
    provider: str
    model: str
    api_key: str = ""
    temperature: float = 0.2

    def resolved_api_key(self) -> str:
        return (self.api_key or get_env_api_key(self.provider)).strip().strip('"')


def create_chat_model(config: LLMConfig):
    provider = config.provider.lower().strip()
    api_key = config.resolved_api_key()
    if not api_key:
        raise ValueError(f"No API key configured for provider '{config.provider}'.")

    if provider == "groq":
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=config.model,
            api_key=SecretStr(api_key),
            temperature=config.temperature,
        )
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=config.model,
            api_key=SecretStr(api_key),
            temperature=config.temperature,
        )
    if provider == "claude":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model_name=config.model,
            api_key=SecretStr(api_key),
            temperature=config.temperature,
        )
    raise ValueError(f"Unsupported provider '{config.provider}'.")


def invoke_structured(
    config: LLMConfig | None,
    schema: type[SchemaT],
    system_prompt: str,
    user_prompt: str,
    fallback_factory: Callable[[], SchemaT] | None,
) -> SchemaT:
    if config is None or not config.resolved_api_key():
        message = "LLM skipped: no API key available."
        if fallback_factory is None:
            raise RuntimeError(message)
        print(f"{message} Using deterministic fallback.")
        return fallback_factory()

    try:
        print(f"LLM call started: provider={config.provider}, model={config.model}")
        chat_model = create_chat_model(config)
        structured = chat_model.with_structured_output(schema)
        result = structured.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        )
        print("LLM call completed with structured output.")
        if isinstance(result, schema):
            return result
        return schema.model_validate(result)
    except Exception as exc:
        if fallback_factory is None:
            raise RuntimeError(f"LLM call failed: {exc}") from exc
        print(f"LLM call failed, using deterministic fallback: {exc}")
        return fallback_factory()


def test_provider_api_key(config: LLMConfig) -> ApiKeyCheck:
    if not config.resolved_api_key():
        return ApiKeyCheck(ok=False, message="API key is empty.")
    try:
        print(f"Testing API key for {config.provider} using {config.model}.")
        model = create_chat_model(config)
        response = model.invoke("Reply with exactly: ok")
        content = getattr(response, "content", "")
        if "ok" in str(content).lower():
            return ApiKeyCheck(ok=True, message="API key and model responded successfully.")
        return ApiKeyCheck(ok=True, message="API key worked, but the model returned a non-standard response.")
    except Exception as exc:
        print(f"API key test failed: {exc}")
        return ApiKeyCheck(ok=False, message=str(exc))
