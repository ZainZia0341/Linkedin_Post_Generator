from __future__ import annotations

import os
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
LOCAL_DB_DIR: Final[Path] = Path(
    os.getenv("LOCAL_DB_DIR", str(PROJECT_ROOT / "schema" / "local_db"))
)
SESSION_DIR: Final[Path] = LOCAL_DB_DIR / "sessions"
SESSION_INDEX_PATH: Final[Path] = LOCAL_DB_DIR / "sessions_index.json"

DEFAULT_MAX_MESSAGES: Final[int] = int(os.getenv("MAX_CHAT_MESSAGES", "10"))
MAX_REVIEW_ATTEMPTS: Final[int] = int(os.getenv("MAX_REVIEW_ATTEMPTS", "3"))
TAVILY_SEARCH_RESULTS: Final[int] = int(os.getenv("TAVILY_SEARCH_RESULTS", "5"))

DEFAULT_PROVIDER: Final[str] = os.getenv("DEFAULT_LLM_PROVIDER", "groq")

PROVIDER_ENV_KEYS: Final[dict[str, str]] = {
    "groq": "GROQ_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
}

PROVIDER_MODELS: Final[dict[str, list[str]]] = {
    "groq": [
        "groq/compound",  # TPM: 70K
        "groq/compound-mini",  # TPM: 70K
        "openai/gpt-oss-120b",  # TPM: 8K
        "llama-3.3-70b-versatile",  # TPM: 12K
        "qwen/qwen3-32b",  # TPM: 6K
        "qwen/qwen3.6-27b",  # TPM: 8K
        "openai/gpt-oss-20b",  # TPM: 8K
        "openai/gpt-oss-safeguard-20b",  # TPM: 8K
        "meta-llama/llama-4-scout-17b-16e-instruct",  # TPM: 30K
        "llama-3.1-8b-instant",  # TPM: 6K
        "canopylabs/orpheus-v1-english",  # TPM: 1.2K
        "canopylabs/orpheus-arabic-saudi",  # TPM: 1.2K
        "meta-llama/llama-prompt-guard-2-86m",  # TPM: 15K
        "meta-llama/llama-prompt-guard-2-22m"  # TPM: 15K
    ],
    "gemini": [
        "gemini-3.5-flash",
        "gemini-2.5-pro",
        "gemini-3-flash-preview",
        "gemini-2.5-flash",
        "gemini-2.5-flash-preview-09-2025",
        "gemini-3.1-flash-lite",
        "gemini-3.1-flash-lite-preview",
        "gemini-2.5-flash-lite",
        "gemini-flash-lite-latest"
    ],
    "claude": [
        # "claude-fable-5",  # Input: $10.00/M | Output: $50.00/M (Frontier reasoning)
        # "claude-mythos-5",  # Input: $10.00/M | Output: $50.00/M (Limited cyber-range availability)
        "claude-opus-4.8",  # Input: $5.00/M | Output: $25.00/M (Latest flagship)
        "claude-opus-4.7",  # Input: $5.00/M | Output: $25.00/M
        "claude-opus-4.6",  # Input: $5.00/M | Output: $25.00/M
        "claude-opus-4.5",  # Input: $5.00/M | Output: $25.00/M
        "claude-sonnet-4.6",  # Input: $3.00/M | Output: $15.00/M (Standard balanced default)
        "claude-sonnet-4.5",  # Input: $3.00/M | Output: $15.00/M
        "claude-haiku-4.5",  # Input: $1.00/M | Output: $5.00/M (High-speed latency tier)
    ],
}

BUILTIN_WRITING_STYLES: Final[dict[str, dict[str, object]]] = {
    "Clear Builder": {
        "name": "Clear Builder",
        "summary": "Practical, concise, and lesson-driven. Opens with a clear observation, explains the useful idea, then ends with a direct takeaway.",
        "tone": "helpful, grounded, professional",
        "hooks": ["A simple thing I learned:", "Most teams miss this:", "Here is the practical version:"],
        "sentence_patterns": ["Short opener", "One idea per paragraph", "Bulleted takeaways"],
        "formatting_patterns": ["brief paragraphs", "1-3 bullets", "direct CTA"],
        "vocabulary": ["practical", "clear", "useful", "learned", "better"],
        "calls_to_action": ["What would you add?", "Save this for later.", "Try this in your next workflow."],
        "hashtags": ["#LinkedIn", "#CareerGrowth", "#BuildingInPublic"],
        "avoid": ["hype", "vague claims", "unverified metrics"],
    },
    "Story Driven": {
        "name": "Story Driven",
        "summary": "Narrative style with a concrete moment, reflection, and human lesson. Good for personal growth and career posts.",
        "tone": "warm, reflective, honest",
        "hooks": ["I used to think...", "A few months ago, I noticed...", "This changed how I work:"],
        "sentence_patterns": ["Personal setup", "Contrast", "Lesson"],
        "formatting_patterns": ["short story blocks", "emotional turn", "closing insight"],
        "vocabulary": ["noticed", "learned", "shifted", "realized", "practice"],
        "calls_to_action": ["Have you seen this too?", "What has your experience been?", "I am still learning this."],
        "hashtags": ["#CareerLessons", "#Leadership", "#PersonalGrowth"],
        "avoid": ["overly polished claims", "generic motivation", "long paragraphs"],
    },
    "Research Analyst": {
        "name": "Research Analyst",
        "summary": "Evidence-led style that frames a trend, explains why it matters, and turns research into specific takeaways.",
        "tone": "analytical, precise, useful",
        "hooks": ["The interesting signal is not...", "A trend worth watching:", "The data points to one thing:"],
        "sentence_patterns": ["Trend statement", "Why it matters", "Actionable implication"],
        "formatting_patterns": ["numbered points", "source-aware claims", "compact conclusion"],
        "vocabulary": ["signal", "trend", "evidence", "market", "implication"],
        "calls_to_action": ["What signal are you watching?", "How are you preparing for this?", "Worth tracking closely."],
        "hashtags": ["#IndustryTrends", "#AI", "#Strategy"],
        "avoid": ["unsupported forecasts", "clickbait", "large unsourced numbers"],
    },
}


def ensure_local_db() -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    if not SESSION_INDEX_PATH.exists():
        SESSION_INDEX_PATH.write_text("[]\n", encoding="utf-8")


def get_models_for_provider(provider: str) -> list[str]:
    return PROVIDER_MODELS.get(provider.lower(), [])


def get_env_api_key(provider: str) -> str:
    env_name = PROVIDER_ENV_KEYS.get(provider.lower(), "")
    return os.getenv(env_name, "").strip() if env_name else ""
