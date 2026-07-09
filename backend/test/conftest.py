from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def disable_live_tavily_tests(monkeypatch):
    if os.getenv("ALLOW_LIVE_TAVILY_TESTS") == "1":
        return
    monkeypatch.setattr("app.travily_tool.get_tavily_api_key", lambda: "")


@pytest.fixture(autouse=True)
def disable_live_llm_tests(monkeypatch):
    if os.getenv("ALLOW_LIVE_LLM_TESTS") == "1":
        return
    monkeypatch.setattr("app.llms.llm.get_env_api_key", lambda provider: "")
