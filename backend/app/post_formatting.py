from __future__ import annotations

import re

HASHTAG_RE = re.compile(r"#[A-Za-z0-9_]+")


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def _extract_hashtags(text: str) -> tuple[str, list[str]]:
    tags = list(dict.fromkeys(HASHTAG_RE.findall(text)))
    without_tags = HASHTAG_RE.sub("", text)
    without_tags = re.sub(r"[ \t]{2,}", " ", without_tags)
    without_tags = re.sub(r"\n{3,}", "\n\n", without_tags).strip()
    return without_tags, tags[:5]


def _chunk_sentences(sentences: list[str], target_paragraphs: int) -> list[str]:
    if not sentences:
        return []
    target_paragraphs = max(1, min(target_paragraphs, len(sentences)))
    chunks: list[list[str]] = [[] for _ in range(target_paragraphs)]
    for index, sentence in enumerate(sentences):
        chunk_index = min(index * target_paragraphs // len(sentences), target_paragraphs - 1)
        chunks[chunk_index].append(sentence)
    return [" ".join(chunk).strip() for chunk in chunks if chunk]


def desired_paragraph_count(word_count: int) -> int:
    if word_count <= 45:
        return 1
    if word_count <= 90:
        return 2
    if word_count <= 150:
        return 3
    if word_count <= 230:
        return 4
    return 5


def format_linkedin_post(post: str) -> str:
    text = post.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    text, hashtags = _extract_hashtags(text)
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]

    if len(paragraphs) <= 1:
        compact = re.sub(r"\s+", " ", text).strip()
        word_count = len(compact.split())
        sentences = _sentences(compact)
        if word_count > 45 and len(sentences) > 1:
            paragraphs = _chunk_sentences(sentences, desired_paragraph_count(word_count))
        else:
            paragraphs = [compact]

    formatted: list[str] = []
    for paragraph in paragraphs:
        cleaned = re.sub(r"[ \t]+", " ", paragraph).strip()
        if cleaned:
            formatted.append(cleaned)

    if hashtags:
        formatted.append(" ".join(hashtags))

    return "\n\n".join(formatted).strip()


def formatting_issues(post: str) -> list[str]:
    text = post.strip()
    if not text:
        return ["Post is empty."]

    issues: list[str] = []
    word_count = len(text.split())
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]

    if word_count > 45 and len(paragraphs) < 2:
        issues.append("Post reads as one wall of text; add blank lines between short paragraphs.")

    max_paragraph_chars = 520 if word_count > 180 else 420
    long_paragraphs = [
        paragraph
        for paragraph in paragraphs
        if len(paragraph) > max_paragraph_chars and not paragraph.lstrip().startswith(("-", "*", "1.", "2.", "3."))
    ]
    if long_paragraphs:
        issues.append("One or more paragraphs are too long for LinkedIn scanning.")

    if len(paragraphs) > 7:
        issues.append("Post has too many separated paragraphs; tighten it unless the topic requires depth.")

    hashtag_matches = HASHTAG_RE.findall(text)
    if len(hashtag_matches) > 5:
        issues.append("Use no more than five relevant hashtags.")
    if hashtag_matches:
        last_paragraph = paragraphs[-1] if paragraphs else ""
        if not all(tag in last_paragraph for tag in hashtag_matches[-min(len(hashtag_matches), 5) :]):
            issues.append("Move hashtags to the final line.")

    return issues

