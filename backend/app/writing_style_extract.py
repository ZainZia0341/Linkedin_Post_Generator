from __future__ import annotations

import re

from app.config import BUILTIN_WRITING_STYLES
from app.llms.llm import LLMConfig, invoke_structured
from app.llms.llm_structure_schema import WritingStyle
from app.llms.prompts import WRITING_STYLE_SYSTEM_PROMPT, WRITING_STYLE_USER_PROMPT


def builtin_writing_styles() -> list[WritingStyle]:
    return [WritingStyle.model_validate(style) for style in BUILTIN_WRITING_STYLES.values()]


def get_builtin_writing_style(name: str) -> WritingStyle:
    style = BUILTIN_WRITING_STYLES.get(name)
    if style is None:
        style = BUILTIN_WRITING_STYLES["Clear Builder"]
    return WritingStyle.model_validate(style)


def _find_hashtags(text: str) -> list[str]:
    tags = re.findall(r"#[A-Za-z0-9_]+", text)
    return list(dict.fromkeys(tags))


def _split_sentences(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def _fallback_style(previous_post: str) -> WritingStyle:
    text = previous_post.strip()
    sentences = _split_sentences(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first_line = lines[0] if lines else "Start with a direct hook."

    avg_sentence_words = 0
    if sentences:
        avg_sentence_words = round(
            sum(len(sentence.split()) for sentence in sentences) / len(sentences)
        )

    formatting = []
    if any(line.startswith(("-", "*")) for line in lines):
        formatting.append("uses bullet points")
    if any(line[:2].isdigit() or line.startswith(("1.", "2.", "3.")) for line in lines):
        formatting.append("uses numbered takeaways")
    if len(lines) > 4:
        formatting.append("uses short separated paragraphs")
    if not formatting:
        formatting.append("uses compact paragraphs")

    tone = "clear and practical"
    lower_text = text.lower()
    if any(word in lower_text for word in ("learned", "realized", "mistake", "journey")):
        tone = "reflective and personal"
    if any(word in lower_text for word in ("data", "trend", "research", "signal")):
        tone = "analytical and evidence-led"

    vocabulary = []
    for word in re.findall(r"\b[A-Za-z][A-Za-z'-]{4,}\b", lower_text):
        if word not in vocabulary:
            vocabulary.append(word)
        if len(vocabulary) == 8:
            break

    return WritingStyle(
        name="Extracted Style",
        summary=f"{tone.capitalize()} style with an opening hook and {avg_sentence_words or 'short'}-word average sentences.",
        tone=tone,
        hooks=[first_line[:160]],
        sentence_patterns=[
            "short hook first" if first_line else "direct opening",
            f"around {avg_sentence_words} words per sentence" if avg_sentence_words else "short sentences",
            "one clear idea per paragraph",
        ],
        formatting_patterns=formatting,
        vocabulary=vocabulary,
        calls_to_action=["Invite comments or a practical next step."],
        hashtags=_find_hashtags(text),
        avoid=["do not invent personal details", "avoid generic hype"],
        confidence=0.55 if text else 0.0,
    )


def extract_writing_style(previous_post: str, llm_config: LLMConfig | None = None) -> WritingStyle:
    if not previous_post.strip():
        print("Writing style extraction skipped: no previous post supplied.")
        return get_builtin_writing_style("Clear Builder")

    return invoke_structured(
        config=llm_config,
        schema=WritingStyle,
        system_prompt=WRITING_STYLE_SYSTEM_PROMPT,
        user_prompt=WRITING_STYLE_USER_PROMPT.format(previous_post=previous_post.strip()),
        fallback_factory=lambda: _fallback_style(previous_post),
    )
