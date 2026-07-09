from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from app.llms.llm import LLMConfig, invoke_structured
from app.llms.llm_structure_schema import ResumeProfile
from app.llms.prompts import RESUME_SYSTEM_PROMPT, RESUME_USER_PROMPT


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    if not pdf_bytes:
        return ""
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")
        print(f"Extracted text from {len(reader.pages)} resume PDF page(s).")
        return "\n".join(text_parts).strip()
    except Exception as exc:
        print(f"PDF extraction failed: {exc}")
        return ""


def extract_text_from_pdf_path(pdf_path: str | Path) -> str:
    path = Path(pdf_path)
    if not path.exists():
        print(f"Resume PDF not found: {path}")
        return ""
    return extract_text_from_pdf_bytes(path.read_bytes())


def _extract_links(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"https?://[^\s)]+|www\.[^\s)]+", text)))


def _extract_skills(text: str) -> list[str]:
    known_skills = [
        "python",
        "langchain",
        "langgraph",
        "streamlit",
        "machine learning",
        "data analysis",
        "sql",
        "fastapi",
        "mongodb",
        "aws",
        "docker",
        "leadership",
        "product management",
        "marketing",
        "sales",
        "analytics",
    ]
    lower_text = text.lower()
    return [skill.title() for skill in known_skills if skill in lower_text]


def _fallback_resume_profile(resume_text: str) -> ResumeProfile:
    text = resume_text.strip()
    if not text:
        return ResumeProfile(raw_notes="No resume was provided.", confidence=0.0)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    full_name = ""
    for line in lines[:5]:
        if 1 <= len(line.split()) <= 4 and not any(char.isdigit() for char in line):
            full_name = line
            break

    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    links = _extract_links(text)
    if email_match:
        links.append(email_match.group(0))

    achievements = [
        line
        for line in lines
        if any(token in line.lower() for token in ("increased", "reduced", "built", "led", "launched", "improved"))
    ][:5]

    education = [
        line
        for line in lines
        if any(token in line.lower() for token in ("university", "college", "bachelor", "master", "degree"))
    ][:3]

    headline = lines[1] if len(lines) > 1 and lines[1] != full_name else ""
    if not headline:
        headline = "Professional profile extracted from resume"

    return ResumeProfile(
        full_name=full_name,
        headline=headline,
        skills=_extract_skills(text),
        experience_summary=" ".join(lines[:6])[:600],
        achievements=achievements,
        education=education,
        links=list(dict.fromkeys(links)),
        raw_notes=text[:1200],
        confidence=0.55,
    )


def extract_resume_profile(resume_text: str, llm_config: LLMConfig | None = None) -> ResumeProfile:
    if not resume_text.strip():
        print("Resume extraction skipped: no resume text supplied.")
        return ResumeProfile(raw_notes="No resume was provided.", confidence=0.0)

    return invoke_structured(
        config=llm_config,
        schema=ResumeProfile,
        system_prompt=RESUME_SYSTEM_PROMPT,
        user_prompt=RESUME_USER_PROMPT.format(resume_text=resume_text[:12000]),
        fallback_factory=lambda: _fallback_resume_profile(resume_text),
    )


def extract_resume_profile_from_pdf_bytes(
    pdf_bytes: bytes,
    llm_config: LLMConfig | None = None,
) -> ResumeProfile:
    return extract_resume_profile(extract_text_from_pdf_bytes(pdf_bytes), llm_config)
