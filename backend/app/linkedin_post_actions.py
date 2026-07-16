from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

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
        ".msg-form__contenteditable[contenteditable='true']",
        "[data-testid*='message' i] div[role='textbox'][contenteditable='true']",
        "div[role='textbox'][contenteditable='true']",
        "textarea",
    ]
    for selector in candidates:
        try:
            locators = page.locator(selector)
            for index in range(locators.count() - 1, -1, -1):
                locator = locators.nth(index)
                if not locator.is_visible():
                    continue
                locator.click(timeout=3000)
                try:
                    locator.fill(text, timeout=4000)
                except Exception:
                    locator.press("Control+A", timeout=2000)
                    locator.type(text, delay=12, timeout=5000)
                return True
        except Exception:
            continue
    return False


def _open_message_composer(page: Any) -> tuple[bool, dict[str, Any]]:
    candidates = [
        ("css", "a[href*='/messaging/compose/']"),
        ("css", "a[aria-label^='Message' i]"),
        ("role_link", re.compile("^Message$", re.I)),
        ("role_button", re.compile("^Message$", re.I)),
    ]
    for kind, value in candidates:
        try:
            if kind == "css":
                controls = page.locator(value)
            elif kind == "role_link":
                controls = page.get_by_role("link", name=value)
            else:
                controls = page.get_by_role("button", name=value)
            for index in range(controls.count()):
                control = controls.nth(index)
                if not control.is_visible():
                    continue
                control.click(timeout=5000)
                try:
                    page.locator(
                        ".msg-form__contenteditable[contenteditable='true'], "
                        "div[role='textbox'][contenteditable='true']"
                    ).last.wait_for(state="visible", timeout=8000)
                except Exception:
                    continue
                return True, {"control": kind, "index": index}
        except Exception:
            continue
    return False, {"reason": "message_control_not_found_or_composer_not_opened"}


def _submit_dm(page: Any, message: str) -> tuple[bool, dict[str, Any]]:
    try:
        buttons = page.get_by_role("button", name=re.compile("^Send$", re.I))
        for index in range(buttons.count() - 1, -1, -1):
            button = buttons.nth(index)
            if not button.is_visible() or button.is_disabled():
                continue
            button.click(timeout=5000)
            try:
                page.wait_for_function(
                    """
                    (expected) => {
                      const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
                      const target = clean(expected);
                      const editors = Array.from(
                        document.querySelectorAll(
                          '.msg-form__contenteditable[contenteditable="true"], div[role="textbox"][contenteditable="true"]'
                        )
                      );
                      return !editors.some((node) => clean(node.innerText || node.textContent).includes(target));
                    }
                    """,
                    message,
                    timeout=7000,
                )
                return True, {"send_button_index": index, "confirmed": "composer_cleared"}
            except Exception:
                return False, {"send_button_index": index, "reason": "message_remained_in_composer"}
    except Exception as exc:
        return False, {"reason": "send_button_error", "error": str(exc)}
    return False, {"reason": "send_button_not_found"}


def _editable_still_contains_text(page: Any, text: str) -> bool:
    script = r"""
    (expected) => {
      const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
      const target = clean(expected);
      if (!target) return false;
      const editors = Array.from(document.querySelectorAll('textarea, [contenteditable="true"], div[role="textbox"]'));
      return editors.some((node) => clean(node.value || node.innerText || node.textContent).includes(target));
    }
    """
    try:
        return bool(page.evaluate(script, text))
    except Exception:
        return False


def _click_submit_for_filled_editor(page: Any, text: str) -> tuple[bool, dict[str, Any]]:
    script = r"""
    (expected) => {
      const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
      const target = clean(expected);
      const visible = (node) => {
        const rect = node.getBoundingClientRect();
        const style = window.getComputedStyle(node);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      };
      const enabled = (button) => !button.disabled && button.getAttribute('aria-disabled') !== 'true';
      const buttonLabel = (button) => clean(button.getAttribute('aria-label') || button.innerText || button.textContent);
      const isCommentActionButton = (button) => {
        let node = button;
        for (let depth = 0; depth < 5 && node; depth += 1) {
          const marker = `${node.getAttribute('componentkey') || ''} ${node.getAttribute('id') || ''}`;
          if (/commentButtonSection|replyButtonSection/i.test(marker)) return true;
          node = node.parentElement;
        }
        return false;
      };
      const looksLikeSubmit = (button) => {
        if (isCommentActionButton(button)) return false;
        const label = buttonLabel(button);
        if (!label) return false;
        return /^(Reply|Post|Comment|Send)$/i.test(label)
          || /^(Reply|Post|Comment|Send)\b/i.test(label)
          || /post comment|submit reply|send reply/i.test(label);
      };
      const editors = Array.from(document.querySelectorAll('textarea, [contenteditable="true"], div[role="textbox"]'))
        .filter((node) => visible(node) && clean(node.value || node.innerText || node.textContent).includes(target));
      const editor = editors[editors.length - 1] || document.activeElement;
      if (!editor || !visible(editor)) return { clicked: false, reason: 'filled_editor_not_found' };

      const editorRect = editor.getBoundingClientRect();
      let scope = editor;
      const scopedCandidates = [];
      for (let depth = 0; depth < 8 && scope; depth += 1) {
        Array.from(scope.querySelectorAll ? scope.querySelectorAll('button') : []).forEach((button) => {
          if (visible(button) && enabled(button) && looksLikeSubmit(button)) scopedCandidates.push(button);
        });
        if (scopedCandidates.length) break;
        scope = scope.parentElement;
      }

      const allCandidates = Array.from(document.querySelectorAll('button'))
        .filter((button) => visible(button) && enabled(button) && looksLikeSubmit(button));
      const candidates = scopedCandidates.length ? scopedCandidates : allCandidates;
      const ranked = candidates
        .map((button) => {
          const rect = button.getBoundingClientRect();
          const belowPenalty = rect.top + 8 < editorRect.top ? 5000 : 0;
          const distance = Math.abs(rect.top - editorRect.bottom) + Math.abs(rect.left - editorRect.right) + belowPenalty;
          return { button, distance, label: buttonLabel(button) };
        })
        .sort((a, b) => a.distance - b.distance);
      if (!ranked.length) return { clicked: false, reason: 'submit_button_not_found' };
      ranked[0].button.click();
      return { clicked: true, label: ranked[0].label, distance: ranked[0].distance };
    }
    """
    try:
        result = page.evaluate(script, text)
        if isinstance(result, dict):
            return bool(result.get("clicked")), result
    except Exception as exc:
        return False, {"reason": str(exc)}
    return False, {"reason": "unknown_submit_failure"}


def _submit_filled_editor(page: Any, text: str) -> ActionExecutionResult:
    clicked, metadata = _click_submit_for_filled_editor(page, text)
    if clicked:
        _random_pause(1.0, 1.6)
        if not _editable_still_contains_text(page, text):
            return ActionExecutionResult(ok=True, final_text=text, raw_metadata={"submit": metadata})

    try:
        page.keyboard.press("Control+Enter")
        _random_pause(1.0, 1.6)
        if not _editable_still_contains_text(page, text):
            fallback_metadata = {"submit": metadata, "fallback": "Control+Enter"}
            return ActionExecutionResult(ok=True, final_text=text, raw_metadata=fallback_metadata)
    except Exception:
        pass

    reason = str(metadata.get("reason") or "Reply text stayed in the editor after submit.")
    return ActionExecutionResult(
        ok=False,
        final_text=text,
        error_message=f"Could not confirm comment reply was submitted: {reason}",
        raw_metadata={"submit": metadata},
    )


def _open_comment_reply_editor(page: Any, comment: Any) -> tuple[Any | None, dict[str, Any]]:
    editor_selector = (
        "[data-testid='ui-core-tiptap-text-editor-wrapper'] "
        "[contenteditable='true'][role='textbox'][aria-label='Text editor for creating comment'], "
        "[contenteditable='true'][role='textbox'][aria-label='Text editor for creating comment']"
    )
    try:
        target_rect = comment.evaluate(
            """node => {
                const rect = node.getBoundingClientRect();
                return { top: rect.top, bottom: rect.bottom, left: rect.left, right: rect.right };
            }"""
        )
        page.evaluate(
            """selector => {
                document.querySelectorAll(selector).forEach((editor) => {
                    const rect = editor.getBoundingClientRect();
                    const style = window.getComputedStyle(editor);
                    if (rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none') {
                        editor.setAttribute('data-ai-spark-existing-editor', 'true');
                    }
                });
            }""",
            editor_selector,
        )
        reply_button = comment.get_by_role("button", name=re.compile(r"^Reply$", re.I)).first
        if reply_button.count() <= 0:
            return None, {"reason": "comment_reply_control_not_found"}
        reply_button.click(timeout=5000)
    except Exception as exc:
        return None, {"reason": "comment_reply_control_click_failed", "error": str(exc)}

    script = r"""
    ({ selector, targetRect }) => {
      const visible = (node) => {
        const rect = node.getBoundingClientRect();
        const style = window.getComputedStyle(node);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      };
      const candidates = Array.from(document.querySelectorAll(selector))
        .filter((editor) => visible(editor))
        .map((editor) => {
          const rect = editor.getBoundingClientRect();
          const existedBeforeClick = editor.getAttribute('data-ai-spark-existing-editor') === 'true';
          const abovePenalty = rect.top + 12 < targetRect.bottom ? 10000 : 0;
          const existingPenalty = existedBeforeClick ? 5000 : 0;
          const distance = Math.abs(rect.top - targetRect.bottom) + Math.abs(rect.left - targetRect.left);
          return { editor, rect, existedBeforeClick, score: abovePenalty + existingPenalty + distance };
        })
        .sort((a, b) => a.score - b.score);
      if (!candidates.length) return { found: false, reason: 'reply_editor_not_found' };
      const newlyVisible = candidates.filter((candidate) => !candidate.existedBeforeClick);
      if (!newlyVisible.length) return { found: false, reason: 'new_reply_editor_not_visible_yet' };
      const target = newlyVisible[0];
      target.editor.setAttribute('data-ai-spark-target-reply-editor', 'true');
      return {
        found: true,
        score: Math.round(target.score),
        existed_before_click: target.existedBeforeClick,
        top: Math.round(target.rect.top),
        left: Math.round(target.rect.left),
      };
    }
    """
    started = time.monotonic()
    last_metadata: dict[str, Any] = {"found": False, "reason": "reply_editor_not_found"}
    while time.monotonic() - started < 15:
        try:
            result = page.evaluate(script, {"selector": editor_selector, "targetRect": target_rect})
            if isinstance(result, dict):
                last_metadata = result
                if result.get("found"):
                    editor = page.locator("[data-ai-spark-target-reply-editor='true']").last
                    if editor.count() > 0 and editor.is_visible(timeout=1000):
                        return editor, {
                            **result,
                            "waited_seconds": round(time.monotonic() - started, 2),
                        }
        except Exception as exc:
            last_metadata = {"found": False, "reason": "reply_editor_detection_failed", "error": str(exc)}
        time.sleep(0.25)
    return None, {
        **last_metadata,
        "waited_seconds": round(time.monotonic() - started, 2),
    }


def _fill_comment_reply_editor(editor: Any, text: str) -> tuple[bool, dict[str, Any]]:
    try:
        editor.click(timeout=4000)
        existing_text = str(editor.inner_text(timeout=2000) or "")
        if existing_text.strip():
            editor.press("End", timeout=2000)
            if not existing_text[-1:].isspace():
                editor.type(" ", delay=10, timeout=2000)
            editor.type(text, delay=12, timeout=10000)
            method = "append_after_linkedin_mention"
        else:
            editor.fill(text, timeout=5000)
            method = "fill_empty_editor"
        final_text = str(editor.inner_text(timeout=2000) or "")
        return text.strip() in final_text.strip(), {
            "method": method,
            "preserved_existing_text": bool(existing_text.strip()),
            "editor_text": final_text,
        }
    except Exception as exc:
        return False, {"reason": "reply_editor_fill_failed", "error": str(exc)}


def _submit_comment_reply_editor(page: Any, editor: Any, text: str) -> ActionExecutionResult:
    script = r"""
    (editor) => {
      const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
      const visible = (node) => {
        const rect = node.getBoundingClientRect();
        const style = window.getComputedStyle(node);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      };
      const enabled = (button) => !button.disabled && button.getAttribute('aria-disabled') !== 'true';
      const labelFor = (button) => clean(button.getAttribute('aria-label') || button.innerText || button.textContent);
      const editorRect = editor.getBoundingClientRect();
      const candidates = [];
      let scope = editor;
      for (let depth = 0; depth < 10 && scope; depth += 1) {
        Array.from(scope.querySelectorAll ? scope.querySelectorAll('button') : []).forEach((button) => {
          if (!visible(button) || !enabled(button) || !/^Reply$/i.test(labelFor(button))) return;
          const rect = button.getBoundingClientRect();
          const marker = `${button.getAttribute('componentkey') || ''} ${button.parentElement?.getAttribute('componentkey') || ''} ${button.parentElement?.id || ''}`;
          const markerBonus = /commentButtonSection/i.test(marker) ? -1000 : 0;
          const abovePenalty = rect.top + 8 < editorRect.top ? 5000 : 0;
          const distance = Math.abs(rect.top - editorRect.bottom) + Math.abs(rect.left - editorRect.right);
          candidates.push({ button, rect, marker, score: markerBonus + abovePenalty + distance });
        });
        if (candidates.length) break;
        scope = scope.parentElement;
      }
      candidates.sort((a, b) => a.score - b.score);
      if (!candidates.length) return { clicked: false, reason: 'final_reply_button_not_found' };
      const target = candidates[0];
      target.button.click();
      return {
        clicked: true,
        label: labelFor(target.button),
        marker: target.marker.slice(0, 180),
        score: Math.round(target.score),
      };
    }
    """
    try:
        result = editor.evaluate(script)
    except Exception as exc:
        result = {"clicked": False, "reason": "final_reply_button_click_failed", "error": str(exc)}

    if not isinstance(result, dict) or not result.get("clicked"):
        return ActionExecutionResult(
            ok=False,
            final_text=text,
            error_message="Could not find the final Reply button after opening the reply editor.",
            raw_metadata={"submit": result if isinstance(result, dict) else {}},
        )

    started = time.monotonic()
    while time.monotonic() - started < 15:
        try:
            if editor.count() <= 0 or not editor.is_visible(timeout=500):
                return ActionExecutionResult(
                    ok=True,
                    final_text=text,
                    raw_metadata={
                        "submit": result,
                        "confirmation": "reply_editor_closed",
                        "waited_seconds": round(time.monotonic() - started, 2),
                    },
                )
            current_text = str(editor.inner_text(timeout=500) or "")
            if text.strip() not in current_text.strip():
                return ActionExecutionResult(
                    ok=True,
                    final_text=text,
                    raw_metadata={
                        "submit": result,
                        "confirmation": "reply_text_cleared",
                        "waited_seconds": round(time.monotonic() - started, 2),
                    },
                )
        except Exception:
            return ActionExecutionResult(
                ok=True,
                final_text=text,
                raw_metadata={
                    "submit": result,
                    "confirmation": "reply_editor_detached",
                    "waited_seconds": round(time.monotonic() - started, 2),
                },
            )
        time.sleep(0.25)

    return ActionExecutionResult(
        ok=False,
        final_text=text,
        error_message="Reply button was clicked, but LinkedIn did not close or clear the reply editor.",
        raw_metadata={
            "submit": result,
            "confirmation": "reply_editor_remained_open",
            "waited_seconds": round(time.monotonic() - started, 2),
        },
    )


def _profile_vanity_name(profile_url: str) -> str:
    path_parts = [unquote(part) for part in urlparse(profile_url).path.split("/") if part]
    try:
        profile_index = path_parts.index("in")
    except ValueError:
        return ""
    if profile_index + 1 >= len(path_parts):
        return ""
    return path_parts[profile_index + 1].strip().lower()


def _wait_for_invite_dialog(page: Any, timeout_seconds: float = 20.0) -> tuple[bool, dict[str, Any]]:
    modal_selectors = (
        "[data-test-modal][role='dialog']",
        "div.artdeco-modal.send-invite[role='dialog']",
        "div[role='dialog'][aria-labelledby='send-invite-modal']",
    )
    action_selectors = (
        "button[aria-label='Send without a note']",
        "button[aria-label='Add a note']",
    )
    started = time.monotonic()
    last_error = ""
    while time.monotonic() - started < timeout_seconds:
        for selector in action_selectors:
            try:
                locator = page.locator(selector).last
                if locator.count() > 0 and locator.is_visible(timeout=1000):
                    labels = []
                    for action_selector in action_selectors:
                        action = page.locator(action_selector).last
                        if action.count() > 0 and action.is_visible(timeout=500):
                            labels.append(str(action.get_attribute("aria-label", timeout=500) or ""))
                    return True, {
                        "selector": selector,
                        "labels": labels,
                        "url": page.url,
                        "waited_seconds": round(time.monotonic() - started, 2),
                    }
            except Exception as exc:
                last_error = str(exc)
        time.sleep(0.25)

    script = r"""
    () => {
      const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
      const visible = (node) => {
        const rect = node.getBoundingClientRect();
        const style = window.getComputedStyle(node);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      };
      const labels = Array.from(document.querySelectorAll('button'))
        .filter((button) => visible(button) && !button.disabled && button.getAttribute('aria-disabled') !== 'true')
        .map((button) => clean(button.getAttribute('aria-label') || button.innerText || button.textContent))
        .filter((label) => /add a note|send without (?:a )?note|send invitation/i.test(label));
      return { ready: labels.length > 0, labels: labels.slice(0, 6), url: window.location.href };
    }
    """
    last_metadata: dict[str, Any] = {"ready": False, "error": last_error}
    try:
        result = page.evaluate(script)
        if isinstance(result, dict):
            last_metadata = result
            if result.get("ready"):
                return True, {
                    **result,
                    "waited_seconds": round(time.monotonic() - started, 2),
                }
    except Exception as exc:
        last_metadata = {"ready": False, "error": str(exc)}
    return False, {
        **last_metadata,
        "waited_seconds": round(time.monotonic() - started, 2),
    }


def _click_connect_control(page: Any, profile_url: str) -> tuple[bool, dict[str, Any]]:
    vanity_name = _profile_vanity_name(profile_url)
    candidate_metadata: list[dict[str, Any]] = []
    invitation_links = page.locator("a[href*='/preload/custom-invite/']")

    try:
        link_count = min(invitation_links.count(), 30)
    except Exception:
        link_count = 0

    matching_links: list[tuple[Any, str, str]] = []
    for index in range(link_count):
        link = invitation_links.nth(index)
        try:
            href = str(link.get_attribute("href", timeout=1000) or "")
            aria_label = str(link.get_attribute("aria-label", timeout=1000) or "")
            href_vanity = (parse_qs(urlparse(href).query).get("vanityName") or [""])[0].strip().lower()
            candidate_metadata.append(
                {
                    "index": index,
                    "href": href,
                    "aria_label": aria_label,
                    "vanity_name": href_vanity,
                }
            )
            if vanity_name and href_vanity == vanity_name:
                matching_links.append((link, href, aria_label))
        except Exception:
            continue

    if not matching_links:
        return False, {
            "reason": "profile_specific_connect_control_not_found",
            "requested_vanity_name": vanity_name,
            "invitation_links": candidate_metadata[:10],
        }

    last_dialog_metadata: dict[str, Any] = {}
    for link, href, aria_label in matching_links:
        try:
            link.scroll_into_view_if_needed(timeout=4000)
            link.click(timeout=5000)
            dialog_ready, dialog_metadata = _wait_for_invite_dialog(page)
            last_dialog_metadata = dialog_metadata
            if dialog_ready:
                return True, {
                    "method": "profile_specific_invitation_link",
                    "requested_vanity_name": vanity_name,
                    "href": href,
                    "aria_label": aria_label,
                    "dialog": dialog_metadata,
                }
        except Exception as exc:
            last_dialog_metadata = {"error": str(exc)}

    return False, {
        "reason": "invite_dialog_not_opened",
        "requested_vanity_name": vanity_name,
        "matched_link_count": len(matching_links),
        "dialog": last_dialog_metadata,
    }


def _click_invite_submit(page: Any) -> tuple[bool, dict[str, Any]]:
    modal_selectors = (
        "[data-test-modal][role='dialog']",
        "div.artdeco-modal.send-invite[role='dialog']",
        "div[role='dialog'][aria-labelledby='send-invite-modal']",
    )
    exact_selectors = (
        "div[role='dialog'][aria-labelledby='send-invite-modal'] button[aria-label='Send without a note']",
        "[data-test-modal][role='dialog'] button[aria-label='Send without a note']",
        "button[aria-label='Send without a note']",
    )
    labels = (
        r"^Send$",
        r"^Done$",
        r"Send without (?:a )?note",
        r"Send invitation",
        r"^Invite$",
    )
    script = r"""
    () => {
      const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
      const visible = (node) => {
        const rect = node.getBoundingClientRect();
        const style = window.getComputedStyle(node);
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      };
      const buttons = Array.from(document.querySelectorAll('button'))
        .filter((button) => visible(button) && !button.disabled && button.getAttribute('aria-disabled') !== 'true');
      const button = buttons.find((node) => /^(Send|Done|Invite)$|send without (?:a )?note|send invitation/i.test(clean(node.getAttribute('aria-label') || node.innerText || node.textContent)));
      if (!button) return { clicked: false, reason: 'invite_submit_not_found' };
      const label = clean(button.getAttribute('aria-label') || button.innerText || button.textContent);
      button.click();
      return { clicked: true, label };
    }
    """
    started = time.monotonic()
    last_reason = "invite_submit_not_found"
    while time.monotonic() - started < 20:
        for selector in exact_selectors:
            try:
                button = page.locator(selector).last
                if button.count() > 0 and button.is_visible(timeout=1000):
                    button.click(timeout=5000)
                    try:
                        page.locator(",".join(modal_selectors)).last.wait_for(state="hidden", timeout=15000)
                    except Exception as exc:
                        return False, {
                            "reason": "invite_dialog_remained_open_after_submit",
                            "selector": selector,
                            "error": str(exc),
                            "waited_seconds": round(time.monotonic() - started, 2),
                        }
                    _random_pause(0.8, 1.3)
                    return True, {
                        "method": "exact_selector",
                        "selector": selector,
                        "waited_seconds": round(time.monotonic() - started, 2),
                    }
            except Exception as exc:
                last_reason = str(exc)
        for label in labels:
            try:
                button = page.get_by_role("button", name=re.compile(label, re.I)).last
                if button.count() > 0:
                    button.click(timeout=5000)
                    _random_pause(0.8, 1.3)
                    return True, {"method": "role", "label": label, "waited_seconds": round(time.monotonic() - started, 2)}
            except Exception as exc:
                last_reason = str(exc)
                continue
        try:
            result = page.evaluate(script)
            if isinstance(result, dict):
                clicked = bool(result.get("clicked"))
                if clicked:
                    _random_pause(0.8, 1.3)
                    return True, {"method": "script", **result, "waited_seconds": round(time.monotonic() - started, 2)}
                last_reason = str(result.get("reason") or last_reason)
        except Exception as exc:
            last_reason = str(exc)
        time.sleep(0.25)
    return False, {"reason": last_reason, "waited_seconds": round(time.monotonic() - started, 2)}


def _fill_connection_note(page: Any, note: str) -> dict[str, Any]:
    if not note:
        return {"note": "empty"}
    started = time.monotonic()
    try:
        add_note = page.get_by_role("button", name=re.compile("Add a note", re.I)).first
        while time.monotonic() - started < 8:
            if add_note.count() > 0:
                add_note.click(timeout=3000)
                _random_pause(0.3, 0.6)
                break
            time.sleep(0.25)
    except Exception:
        pass

    short_note = note[:290]
    for selector in ("textarea", "div[role='textbox']", "[contenteditable='true']"):
        try:
            box = page.locator(selector).last
            if box.count() > 0:
                box.click(timeout=3000)
                box.fill(short_note, timeout=3000)
                return {"note": "filled", "selector": selector}
        except Exception:
            continue
    return {"note": "not_filled"}


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

        clicked, connect_metadata = _click_connect_control(page, profile_url)
        if not clicked:
            connect_error = (
                "Could not open connection request dialog."
                if connect_metadata.get("reason") == "invite_dialog_not_opened"
                else "Could not find Connect button for the requested profile."
            )
            return ActionExecutionResult(
                ok=False,
                error_message=connect_error,
                raw_metadata={"connect": connect_metadata},
            )

        note_metadata = _fill_connection_note(page, note)
        if note and note_metadata.get("note") == "not_filled":
            return ActionExecutionResult(
                ok=False,
                final_text=note,
                error_message="Could not fill connection note.",
                raw_metadata={"connect": connect_metadata, "note": note_metadata},
            )

        sent, send_metadata = _click_invite_submit(page)
        if sent:
            return ActionExecutionResult(
                ok=True,
                final_text=note,
                raw_metadata={"connect": connect_metadata, "note": note_metadata, "send": send_metadata},
            )
        return ActionExecutionResult(
            ok=False,
            final_text=note,
            error_message="Could not submit connection request.",
            raw_metadata={"connect": connect_metadata, "note": note_metadata, "send": send_metadata},
        )

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

        opened, open_metadata = _open_message_composer(page)
        if not opened:
            return ActionExecutionResult(
                ok=False,
                error_message="Could not open message composer.",
                raw_metadata={"composer": open_metadata},
            )

        _random_pause(0.8, 1.2)
        if not _fill_message_box(page, message):
            return ActionExecutionResult(
                ok=False,
                error_message="Could not fill message composer.",
                raw_metadata={"composer": open_metadata},
            )

        sent, send_metadata = _submit_dm(page, message)
        if sent:
            return ActionExecutionResult(
                ok=True,
                final_text=message,
                raw_metadata={"composer": open_metadata, "send": send_metadata},
            )
        return ActionExecutionResult(
            ok=False,
            final_text=message,
            error_message="Could not confirm that the message was sent.",
            raw_metadata={"composer": open_metadata, "send": send_metadata},
        )

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
        comment_urn = (comment_ref.get("comment_urn") or "").strip()
        name = (comment_ref.get("name") or "").strip()
        locator = None
        selectors = (
            "[componentkey*='replaceableComment_urn:li:comment']",
            "[id*='replaceableComment_urn:li:comment']",
            "article.comments-comment-item",
            ".comments-comment-item",
            "[class*='comment-item']",
        )
        for selector in selectors:
            try:
                roots = page.locator(selector)
                count = min(roots.count(), 80)
                for index in range(count):
                    item = roots.nth(index)
                    text = item.inner_text(timeout=1000)
                    attrs = ""
                    try:
                        attrs = " ".join(
                            str(value or "")
                            for value in (
                                item.get_attribute("componentkey", timeout=500),
                                item.get_attribute("id", timeout=500),
                                item.get_attribute("data-urn", timeout=500),
                            )
                        )
                    except Exception:
                        attrs = ""
                    if (
                        (comment_urn and comment_urn in attrs)
                        or (comment_text and comment_text[:80] in text)
                        or (name and name in text)
                    ):
                        locator = item
                        break
                if locator:
                    break
            except Exception:
                continue
        if locator is None:
            locator = page.locator("body")

        editor, open_metadata = _open_comment_reply_editor(page, locator)
        if editor is None:
            return ActionExecutionResult(
                ok=False,
                error_message="Could not open the reply editor for the stored comment.",
                raw_metadata={"open_reply": open_metadata},
            )

        filled, fill_metadata = _fill_comment_reply_editor(editor, reply_text)
        if not filled:
            return ActionExecutionResult(
                ok=False,
                final_text=reply_text,
                error_message="Could not fill the opened comment reply editor.",
                raw_metadata={"open_reply": open_metadata, "fill": fill_metadata},
            )

        submit_result = _submit_comment_reply_editor(page, editor, reply_text)
        submit_result.raw_metadata = {
            "open_reply": open_metadata,
            "fill": fill_metadata,
            **(submit_result.raw_metadata or {}),
        }
        return submit_result

    return _with_page(run)
