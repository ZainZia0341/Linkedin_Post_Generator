from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.linkedin_playwright_scraper import (
    LINKEDIN_AUTOMATION_MODE,
    BOOTSTRAP_REQUIRED_MESSAGE,
    SESSION_EXPIRED_MESSAGE,
    _clean_text,
    _error,
    _open_context,
    _random_pause,
    has_bootstrapped_burner_session,
    looks_like_login_or_challenge_page,
)


@dataclass(slots=True)
class EngagementScrapeResult:
    engagers: list[dict[str, Any]] = field(default_factory=list)
    like_count: int = 0
    comment_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _hash_text(value: str) -> str:
    return hashlib.sha256(_clean_text(value).lower().encode("utf-8")).hexdigest()


def _profile_key(engager: dict[str, Any]) -> str:
    return str(
        engager.get("profile_url")
        or engager.get("profile_urn")
        or engager.get("name")
        or _hash_text(str(engager))
    ).strip()


def _merge_engagers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        key = _profile_key(item)
        existing = merged.setdefault(key, dict(item))
        types = set(existing.get("engagement_types") or [])
        types.update(str(value) for value in item.get("engagement_types") or [])
        existing["engagement_types"] = sorted(types)
        for field_name in (
            "profile_url",
            "profile_urn",
            "name",
            "headline",
            "connection_degree",
            "comment_text",
            "comment_permalink",
            "comment_urn",
            "comment_text_hash",
            "comment_timestamp_text",
        ):
            if item.get(field_name):
                existing[field_name] = item[field_name]
        raw = dict(existing.get("raw_metadata") or {})
        raw.update(dict(item.get("raw_metadata") or {}))
        existing["raw_metadata"] = raw
    return list(merged.values())


def _extract_visible_comments(page: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    script = r"""
    () => {
      const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
      const roots = new Set();
      const selectors = [
        'article.comments-comment-item',
        '.comments-comment-item',
        '[data-test-id*="comment"]',
        '[data-testid*="commentList"] [id^="replaceableComment_urn:li:comment"]',
        '[id^="replaceableComment_urn:li:comment"]',
        '[class*="comment-item"]'
      ];
      selectors.forEach((selector) => {
        document.querySelectorAll(selector).forEach((node) => {
          const commentRoot = node.closest('[componentkey*="replaceableComment_urn:li:comment"]')
            || node.closest('[id*="replaceableComment_urn:li:comment"]')
            || node;
          roots.add(commentRoot);
        });
      });

      const profileHref = (root) => {
        const anchors = Array.from(root.querySelectorAll('a[href*="/in/"], a[href*="/company/"]'));
        const href = anchors.map((node) => node.href).find(Boolean) || '';
        if (!href) return '';
        try {
          const url = new URL(href);
          url.search = '';
          url.hash = '';
          return url.toString();
        } catch {
          return href;
        }
      };

      const findText = (root, selectors) => {
        for (const selector of selectors) {
          const node = root.querySelector(selector);
          const text = clean(node && node.innerText);
          if (text) return text;
        }
        return '';
      };

      const comments = [];
      roots.forEach((root) => {
        const name = findText(root, [
          '.comments-post-meta__name-text',
          '.comments-comment-meta__description-title',
          'a[href*="/in/"] span[aria-hidden="true"]',
          'a[href*="/in/"] p span',
          'a[href*="/in/"] span',
          'a[href*="/in/"]'
        ]);
        const normalizedName = clean(
          name
            .replace(/,\s*(Open to work\s*)?(Verified Profile\s*)?(You|1st|2nd|3rd).*$/i, '')
            .replace(/\s+(Author|You|1st|2nd|3rd)$/i, '')
        );
        const profileParagraphs = Array.from(root.querySelectorAll('a[href*="/in/"] p'))
          .map((node) => clean(node.innerText))
          .filter(Boolean);
        const headline = findText(root, [
          '.comments-post-meta__headline',
          '.comments-comment-meta__headline',
          '[class*="headline"]'
        ]) || profileParagraphs.find((value) => (
          value !== normalizedName
          && !value.includes(normalizedName)
          && !/^(Author|You|1st|2nd|3rd|\d+\s*[mhdwy])\b/i.test(value)
        )) || '';
        const text = findText(root, [
          '.comments-comment-item__main-content',
          '.comments-comment-item-content-body',
          '[data-testid="expandable-text-box"]',
          '[class*="commentary"]',
          '[class*="comments-comment-text"]',
          'span[dir="ltr"]'
        ]) || clean(root.innerText);
        const permalinkNode = root.querySelector('a[href*="commentUrn"], a[href*="comment"], a[href*="/feed/update/"]');
        const commentPermalink = permalinkNode ? permalinkNode.href : '';
        const componentKey = root.getAttribute('componentkey') || root.getAttribute('id') || '';
        const componentUrn = (componentKey.match(/replaceableComment_(urn:li:comment:\([^)]+\))/) || [])[1] || '';
        const commentUrn = root.getAttribute('data-id')
          || root.getAttribute('data-urn')
          || (commentPermalink.match(/commentUrn=([^&]+)/) || [])[1]
          || componentUrn
          || '';
        const timestamp = findText(root, ['time', 'a[href*="comment"] time', '[class*="timestamp"]'])
          || Array.from(root.querySelectorAll('p, span'))
            .map((node) => clean(node.innerText))
            .find((value) => /^\d+\s*[mhdwy]\b/i.test(value))
          || '';
        const profileUrl = profileHref(root);
        const cleanName = clean(
          name
            .replace(/,\s*(Open to work\s*)?(Verified Profile\s*)?(You|1st|2nd|3rd).*$/i, '')
            .replace(/\s*•\s*(You|1st|2nd|3rd).*$/i, '')
            .replace(/\s+(Author|You|1st|2nd|3rd)$/i, '')
        );
        const cleanText = clean(text);
        const rawText = clean(root.innerText);
        const degreeMatch = rawText.match(/(?:^|\s|[•·])(1st|2nd|3rd)(?:\s|$)/i);
        const normalizedHeadline = clean(headline) === cleanName ? '' : clean(headline);
        if (cleanText && (cleanName || profileUrl)) {
          comments.push({
            profile_url: profileUrl,
            profile_urn: '',
            name: cleanName,
            headline: normalizedHeadline,
            connection_degree: degreeMatch ? degreeMatch[1] : '',
            comment_text: cleanText,
            comment_permalink: commentPermalink,
            comment_urn: commentUrn,
            comment_timestamp_text: timestamp,
            raw_text: rawText
          });
        }
      });

      const deduped = [];
      const seen = new Set();
      comments.forEach((comment) => {
        const key = comment.comment_urn || `${comment.profile_url}|${comment.name}|${comment.comment_text}`;
        if (seen.has(key)) return;
        seen.add(key);
        deduped.push(comment);
      });
      return {
        comments: deduped,
        roots_seen: roots.size,
        body_text_length: clean(document.body && document.body.innerText).length
      };
    }
    """
    result = page.evaluate(script)
    if not isinstance(result, dict):
        return [], {}
    comments = result.get("comments") if isinstance(result.get("comments"), list) else []
    return [item for item in comments if isinstance(item, dict)], result


def _extract_visible_reactors(page: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    script = r"""
    () => {
      const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
      const queryAllDeep = (selector) => {
        const matches = [];
        const visit = (root) => {
          if (!root || !root.querySelectorAll) return;
          root.querySelectorAll(selector).forEach((node) => matches.push(node));
          root.querySelectorAll('*').forEach((node) => {
            if (node.shadowRoot) visit(node.shadowRoot);
          });
        };
        visit(document);
        return matches;
      };
      const roots = new Set();
      const selectors = [
        '[class*="social-details-reactors"] li',
        '[class*="reaction"] li',
        'li.artdeco-list__item',
        '[data-test-modal] li',
        '[data-test-modal] [role="listitem"]',
        '[data-test-modal] a[href*="/in/"]',
        '[role="dialog"] li',
        '[role="dialog"] [role="listitem"]',
        '[role="dialog"] a[href*="/in/"]',
        '.artdeco-modal a[href*="/in/"]'
      ];
      selectors.forEach((selector) => {
        queryAllDeep(selector).forEach((node) => {
          const root = node.closest('li')
            || node.closest('[role="listitem"]')
            || node.closest('[data-view-name]')
            || node.parentElement
            || node;
          roots.add(root);
        });
      });
      const reactors = [];
      roots.forEach((root) => {
        const profileNode = root.querySelector('a[href*="/in/"], a[href*="/company/"]');
        let profileUrl = profileNode ? profileNode.href : '';
        if (profileUrl) {
          try {
            const url = new URL(profileUrl);
            url.search = '';
            url.hash = '';
            profileUrl = url.toString();
          } catch {}
        }
        const lines = (root.innerText || root.textContent || '')
          .split('\n')
          .map(clean)
          .filter(Boolean);
        const name = lines.find((line) => !/^(connect|follow|message|pending|1st|2nd|3rd)$/i.test(line)) || '';
        const headline = lines.find((line) => line !== name && !/^(connect|follow|message|pending)$/i.test(line)) || '';
        const degree = (lines.find((line) => /^(1st|2nd|3rd)/i.test(line)) || '').replace(/[^A-Za-z0-9]/g, '');
        if (profileUrl || name) {
          reactors.push({
            profile_url: profileUrl,
            profile_urn: '',
            name,
            headline,
            connection_degree: degree,
            raw_text: clean(root.innerText)
          });
        }
      });
      const deduped = [];
      const seen = new Set();
      reactors.forEach((reactor) => {
        const key = reactor.profile_url || reactor.name;
        if (!key || seen.has(key)) return;
        seen.add(key);
        deduped.push(reactor);
      });
      return { reactors: deduped, roots_seen: roots.size };
    }
    """
    result = page.evaluate(script)
    if not isinstance(result, dict):
        return [], {}
    reactors = result.get("reactors") if isinstance(result.get("reactors"), list) else []
    return [item for item in reactors if isinstance(item, dict)], result


def _open_reactions_dialog(page: Any) -> bool:
    role_names = [
        r"^(?!open reactions menu).*\b\d+\s+reactions?\b.*$",
        r"^view\s+.*reactions?.*$",
    ]
    for label in role_names:
        for role in ("button", "link"):
            try:
                control = page.get_by_role(role, name=re.compile(label, re.I)).first
                if control.count() > 0:
                    control.click(timeout=3000)
                    _random_pause(0.8, 1.4)
                    return True
            except Exception:
                continue

    locators = [
        "button[aria-label*='reaction' i]:not([aria-label*='menu' i]):not([aria-label*='button state' i])",
        "a[aria-label*='reaction' i]:not([aria-label*='menu' i])",
        "span.social-details-social-counts__reactions-count",
        ".social-details-social-counts__reactions-count",
    ]
    for selector in locators:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0:
                locator.click(timeout=3000)
                _random_pause(0.8, 1.4)
                return True
        except Exception:
            continue

    script = r"""
    () => {
      const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
      const controls = [];
      const visit = (root) => {
        if (!root || !root.querySelectorAll) return;
        root.querySelectorAll('button, a, [role="button"]').forEach((node) => controls.push(node));
        root.querySelectorAll('*').forEach((node) => {
          if (node.shadowRoot) visit(node.shadowRoot);
        });
      };
      visit(document);
      const target = controls.find((node) => {
        const label = clean(node.getAttribute('aria-label') || '');
        const text = clean(node.innerText || '');
        const combined = `${label} ${text}`;
        if (/reaction button state/i.test(combined)) return false;
        if (/open reactions menu/i.test(combined)) return false;
        if (/comment|repost|send|reply/i.test(label)) return false;
        return /\b\d+\s+reactions?\b/i.test(combined) || /^view\s+.*reactions?/i.test(combined);
      });
      if (!target) return false;
      target.click();
      return true;
    }
    """
    try:
        clicked = bool(page.evaluate(script))
        if clicked:
            _random_pause(0.8, 1.4)
            return True
    except Exception:
        pass
    return False


def _visible_reaction_count(page: Any) -> int:
    script = r"""
    () => {
      const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
      const controls = [];
      const visit = (root) => {
        if (!root || !root.querySelectorAll) return;
        root.querySelectorAll('button, a, [role="button"]').forEach((node) => controls.push(node));
        root.querySelectorAll('*').forEach((node) => {
          if (node.shadowRoot) visit(node.shadowRoot);
        });
      };
      visit(document);
      for (const node of controls) {
        const label = clean(node.getAttribute('aria-label') || '');
        const text = clean(node.innerText || '');
        const combined = `${label} ${text}`;
        if (/reaction button state|open reactions menu/i.test(combined)) continue;
        const match = combined.match(/\b(\d+)\s+reactions?\b/i);
        if (match) return Number(match[1]) || 0;
      }
      return 0;
    }
    """
    try:
        return int(page.evaluate(script) or 0)
    except Exception:
        return 0


def _load_more_comments(page: Any) -> None:
    for _ in range(3):
        clicked = False
        for label in ("Load more comments", "Show more comments", "View more comments"):
            try:
                button = page.get_by_role("button", name=re.compile(label, re.I)).first
                if button.count() > 0:
                    button.click(timeout=2500)
                    clicked = True
                    _random_pause(0.8, 1.2)
                    break
            except Exception:
                continue
        page.mouse.wheel(0, 800)
        _random_pause(0.4, 0.8)
        if not clicked:
            break


def scrape_linkedin_post_engagement(
    post_url: str,
    include_likes: bool = True,
    include_comments: bool = True,
) -> EngagementScrapeResult:
    mode = LINKEDIN_AUTOMATION_MODE.strip().lower()
    if mode not in {"logged_out", "burner"}:
        return EngagementScrapeResult(
            errors=[{"error": "invalid_automation_mode", "message": "LINKEDIN_AUTOMATION_MODE must be 'logged_out' or 'burner'."}]
        )
    if mode == "burner" and not has_bootstrapped_burner_session():
        return EngagementScrapeResult(
            errors=[{"error": "burner_session_not_found", "message": BOOTSTRAP_REQUIRED_MESSAGE}]
        )

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return EngagementScrapeResult(errors=[{"error": "playwright_unavailable", "message": str(exc)}])

    browser = None
    context = None
    try:
        with sync_playwright() as playwright:
            browser, context = _open_context(playwright, mode)
            page = context.new_page()
            page.goto(post_url, wait_until="domcontentloaded", timeout=30000)
            if mode == "burner" and looks_like_login_or_challenge_page(page):
                return EngagementScrapeResult(
                    errors=[{"error": "session_expired_or_challenged", "message": SESSION_EXPIRED_MESSAGE}]
                )
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            _random_pause()

            engagers: list[dict[str, Any]] = []
            diagnostics: dict[str, Any] = {"post_url": post_url}
            warnings: list[str] = []

            if include_comments:
                _load_more_comments(page)
                comments, comment_diagnostics = _extract_visible_comments(page)
                diagnostics["comments"] = comment_diagnostics
                for comment in comments:
                    text = str(comment.get("comment_text", ""))
                    engagers.append(
                        {
                            **comment,
                            "engagement_types": ["comment"],
                            "comment_text_hash": _hash_text(text),
                            "scraped_at": _now(),
                            "source": "playwright",
                            "raw_metadata": {"raw_text": comment.get("raw_text", "")},
                        }
                    )
                if not comments:
                    warnings.append("No visible commenters were extracted. LinkedIn selectors may need review.")

            if include_likes:
                reaction_count_hint = _visible_reaction_count(page)
                diagnostics["visible_reaction_count"] = reaction_count_hint
                opened = _open_reactions_dialog(page)
                diagnostics["likes_dialog_opened"] = opened
                if opened:
                    for _ in range(4):
                        page.mouse.wheel(0, 1200)
                        _random_pause(0.3, 0.7)
                    reactors, reactor_diagnostics = _extract_visible_reactors(page)
                    diagnostics["likes"] = reactor_diagnostics
                    for reactor in reactors:
                        engagers.append(
                            {
                                **reactor,
                                "engagement_types": ["like"],
                                "scraped_at": _now(),
                                "source": "playwright",
                                "raw_metadata": {"raw_text": reactor.get("raw_text", "")},
                            }
                        )
                    if not reactors and reaction_count_hint > 0:
                        warnings.append("Reaction dialog opened but no likers were extracted. LinkedIn selectors may need review.")
                elif reaction_count_hint > 0:
                    warnings.append("Could not open LinkedIn reactions dialog for likes.")

            merged = _merge_engagers(engagers)
            return EngagementScrapeResult(
                engagers=merged,
                like_count=sum(1 for item in merged if "like" in item.get("engagement_types", [])),
                comment_count=sum(1 for item in merged if "comment" in item.get("engagement_types", [])),
                warnings=warnings,
                diagnostics=diagnostics,
            )
    except Exception as exc:
        return EngagementScrapeResult(errors=[{"error": "playwright_run_failed", "message": str(exc)}])
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
