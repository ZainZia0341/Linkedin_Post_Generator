from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any

from app.linkedin_playwright_scraper import (
    LINKEDIN_AUTOMATION_MODE,
    BOOTSTRAP_REQUIRED_MESSAGE,
    SESSION_EXPIRED_MESSAGE,
    _open_context,
    _random_pause,
    has_bootstrapped_burner_session,
    looks_like_login_or_challenge_page,
)


_ACTION_LOCK = threading.Lock()
_MIN_SECONDS_BETWEEN_ACTIONS = 2.5
_last_action_at = 0.0


@dataclass(slots=True)
class ActionExecutionResult:
    ok: bool
    final_text: str = ""
    error_message: str = ""
    raw_metadata: dict[str, Any] | None = None


def _rate_limit() -> None:
    global _last_action_at
    with _ACTION_LOCK:
        elapsed = time.monotonic() - _last_action_at
        if elapsed < _MIN_SECONDS_BETWEEN_ACTIONS:
            time.sleep(_MIN_SECONDS_BETWEEN_ACTIONS - elapsed)
        _last_action_at = time.monotonic()


def _browser_preflight() -> str:
    mode = LINKEDIN_AUTOMATION_MODE.strip().lower()
    if mode not in {"logged_out", "burner"}:
        return "LINKEDIN_AUTOMATION_MODE must be 'logged_out' or 'burner'."
    if mode == "burner" and not has_bootstrapped_burner_session():
        return BOOTSTRAP_REQUIRED_MESSAGE
    if mode == "logged_out":
        return "LinkedIn write actions require burner mode with an authenticated browser profile."
    return ""


def _with_page(callback) -> ActionExecutionResult:
    preflight_error = _browser_preflight()
    if preflight_error:
        return ActionExecutionResult(ok=False, error_message=preflight_error)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return ActionExecutionResult(ok=False, error_message=f"Playwright is not available: {exc}")

    browser = None
    context = None
    try:
        with sync_playwright() as playwright:
            browser, context = _open_context(playwright, "burner")
            page = context.new_page()
            _rate_limit()
            return callback(page)
    except Exception as exc:
        return ActionExecutionResult(ok=False, error_message=str(exc))
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


def _check_session(page: Any) -> ActionExecutionResult | None:
    if looks_like_login_or_challenge_page(page):
        return ActionExecutionResult(ok=False, error_message=SESSION_EXPIRED_MESSAGE)
    return None


def _fill_message_box(page: Any, text: str) -> bool:
    candidates = [
        "div[role='textbox']",
        "textarea",
        "[contenteditable='true']",
    ]
    for selector in candidates:
        locator = None
        try:
            locator = page.locator(selector).last
            if locator.count() > 0:
                locator.click(timeout=3000)
                locator.fill(text, timeout=3000)
                return True
        except Exception:
            if locator is None:
                continue
            try:
                locator.type(text, delay=12, timeout=3000)
                return True
            except Exception:
                continue
    return False


def send_connection_request(profile_url: str, note: str = "") -> ActionExecutionResult:
    def run(page: Any) -> ActionExecutionResult:
        page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        session_error = _check_session(page)
        if session_error:
            return session_error
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        _random_pause()

        clicked = False
        for pattern in (r"^Connect$", r"More"):
            try:
                button = page.get_by_role("button", name=re.compile(pattern, re.I)).first
                if button.count() > 0:
                    button.click(timeout=4000)
                    clicked = True
                    _random_pause(0.5, 0.9)
                    break
            except Exception:
                continue
        if not clicked:
            return ActionExecutionResult(ok=False, error_message="Could not find Connect button.")

        if note:
            try:
                add_note = page.get_by_role("button", name=re.compile("Add a note", re.I)).first
                if add_note.count() > 0:
                    add_note.click(timeout=3000)
                    _random_pause(0.3, 0.6)
                    textarea = page.locator("textarea").first
                    textarea.fill(note[:290], timeout=3000)
            except Exception:
                pass

        for label in (r"^Send$", r"^Done$"):
            try:
                button = page.get_by_role("button", name=re.compile(label, re.I)).first
                if button.count() > 0:
                    button.click(timeout=4000)
                    return ActionExecutionResult(ok=True, final_text=note)
            except Exception:
                continue
        return ActionExecutionResult(ok=False, error_message="Could not submit connection request.")

    return _with_page(run)


def send_dm(profile_url: str, message: str) -> ActionExecutionResult:
    def run(page: Any) -> ActionExecutionResult:
        page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
        session_error = _check_session(page)
        if session_error:
            return session_error
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        _random_pause()

        try:
            button = page.get_by_role("button", name=re.compile("^Message$", re.I)).first
            if button.count() <= 0:
                return ActionExecutionResult(ok=False, error_message="Could not find Message button.")
            button.click(timeout=4000)
        except Exception as exc:
            return ActionExecutionResult(ok=False, error_message=f"Could not open message composer: {exc}")

        _random_pause(0.8, 1.2)
        if not _fill_message_box(page, message):
            return ActionExecutionResult(ok=False, error_message="Could not fill message composer.")

        try:
            send_button = page.get_by_role("button", name=re.compile("^Send$", re.I)).last
            send_button.click(timeout=4000)
            return ActionExecutionResult(ok=True, final_text=message)
        except Exception as exc:
            return ActionExecutionResult(ok=False, error_message=f"Could not send message: {exc}")

    return _with_page(run)


def reply_to_comment(post_url: str, comment_ref: dict[str, str], reply_text: str) -> ActionExecutionResult:
    def run(page: Any) -> ActionExecutionResult:
        target_url = comment_ref.get("comment_permalink") or post_url
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        session_error = _check_session(page)
        if session_error:
            return session_error
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        _random_pause()

        comment_text = (comment_ref.get("comment_text") or "").strip()
        name = (comment_ref.get("name") or "").strip()
        locator = None
        for selector in ("article.comments-comment-item", ".comments-comment-item", "[class*='comment-item']"):
            try:
                roots = page.locator(selector)
                count = min(roots.count(), 40)
                for index in range(count):
                    item = roots.nth(index)
                    text = item.inner_text(timeout=1000)
                    if (comment_text and comment_text[:80] in text) or (name and name in text):
                        locator = item
                        break
                if locator:
                    break
            except Exception:
                continue
        if locator is None:
            locator = page.locator("body")

        try:
            reply_button = locator.get_by_role("button", name=re.compile("Reply", re.I)).first
            if reply_button.count() <= 0:
                return ActionExecutionResult(ok=False, error_message="Could not find Reply button for stored comment.")
            reply_button.click(timeout=4000)
        except Exception as exc:
            return ActionExecutionResult(ok=False, error_message=f"Could not open reply editor: {exc}")

        _random_pause(0.5, 0.9)
        if not _fill_message_box(page, reply_text):
            return ActionExecutionResult(ok=False, error_message="Could not fill comment reply editor.")

        for label in (r"^Reply$", r"^Post$"):
            try:
                button = page.get_by_role("button", name=re.compile(label, re.I)).last
                if button.count() > 0:
                    button.click(timeout=4000)
                    return ActionExecutionResult(ok=True, final_text=reply_text)
            except Exception:
                continue
        return ActionExecutionResult(ok=False, error_message="Could not submit comment reply.")

    return _with_page(run)
