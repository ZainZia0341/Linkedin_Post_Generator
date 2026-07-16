from __future__ import annotations

import hashlib
import random
import re
import time
from datetime import UTC, datetime
from typing import Any

from app.config import (
    LINKEDIN_AUTOMATION_MODE,
    LINKEDIN_BROWSER_PROFILE_DIR,
    LINKEDIN_HEADLESS,
)

_ACTIVITY_RE = re.compile(r"urn:li:activity:\d+")
BOOTSTRAP_COMMAND = "uv run python scripts/bootstrap_linkedin_session.py"
BOOTSTRAP_REQUIRED_MESSAGE = (
    "Burner session not found. Run `uv run python scripts/bootstrap_linkedin_session.py` "
    "once from a terminal to log in manually, then try again."
)
SESSION_EXPIRED_MESSAGE = (
    "The burner session appears to be logged out or blocked by a LinkedIn verification "
    "screen. Re-run scripts/bootstrap_linkedin_session.py to log in manually, then try again."
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _looks_like_connection_degree(text: str) -> bool:
    return bool(re.fullmatch(r"[^A-Za-z0-9]*\d+(?:st|nd|rd|th)\s*", _clean_text(text), flags=re.I))


def _looks_like_headline_saved_as_location(text: str) -> bool:
    cleaned = _clean_text(text)
    return bool(cleaned) and ("|" in cleaned or len(cleaned) > 70) and "," not in cleaned


def _looks_like_invalid_profile_details(name: str, headline: str, location: str) -> bool:
    combined = " ".join(_clean_text(value).lower() for value in (name, headline, location) if value)
    if not _clean_text(name):
        return True
    invalid_phrases = (
        "skip to main content",
        "0 notifications",
        "page not found",
        "profile not found",
        "this profile is not available",
        "member not found",
    )
    return any(phrase in combined for phrase in invalid_phrases) or bool(re.search(r"\b\d+\s+notifications?\b", combined))


def _looks_like_invalid_location(text: str) -> bool:
    cleaned = _clean_text(text)
    if not cleaned:
        return False
    if len(cleaned) > 90:
        return True
    if "|" in cleaned:
        return True
    return bool(
        re.search(
            r"\b(started|served|people|get served|infrastructure|organisations?|organizations?|experience|followers?|connections?)\b",
            cleaned,
            flags=re.I,
        )
    )


def _content_hash(text: str) -> str:
    return hashlib.sha256(_clean_text(text).lower().encode("utf-8")).hexdigest()


def _error(error: str, message: str | None = None) -> list[dict[str, Any]]:
    message = message or error
    print(f"LinkedIn Playwright scraper stopped: {message}")
    return [{"error": error, "message": message, "source": "playwright"}]


def has_bootstrapped_burner_session() -> bool:
    return LINKEDIN_BROWSER_PROFILE_DIR.exists() and any(LINKEDIN_BROWSER_PROFILE_DIR.iterdir())


def _candidate_activity_urls(profile_url: str) -> list[str]:
    base_url = profile_url.strip().rstrip("/")
    return [
        f"{base_url}/recent-activity/all/",
        f"{base_url}/recent-activity/shares/",
        f"{base_url}/",
    ]


def _experience_url(profile_url: str) -> str:
    return f"{profile_url.strip().rstrip('/')}/details/experience/"


def _activity_urn(*values: object) -> str:
    for value in values:
        match = _ACTIVITY_RE.search(str(value or ""))
        if match:
            return match.group(0)
    return ""


def _post_url(url: str, activity_urn: str) -> str:
    if activity_urn:
        return f"https://www.linkedin.com/feed/update/{activity_urn}/"
    return url


def _body_text(page: Any) -> str:
    try:
        return page.locator("body").inner_text(timeout=3000)
    except Exception:
        return ""


def _has_locator(page: Any, selectors: list[str]) -> bool:
    for selector in selectors:
        try:
            if page.locator(selector).count() > 0:
                return True
        except Exception:
            continue
    return False


def _has_login_wall(page: Any) -> bool:
    text = _body_text(page).lower()
    url = getattr(page, "url", "").lower()
    return any(
        marker in text or marker in url
        for marker in (
            "sign in to view",
            "join linkedin",
            "sign in to linkedin",
            "authwall",
            "linkedin.com/login",
        )
    )


def looks_like_login_or_challenge_page(page: Any) -> bool:
    url = getattr(page, "url", "").lower()
    if any(
        marker in url
        for marker in (
            "linkedin.com/login",
            "linkedin.com/checkpoint",
            "linkedin.com/authwall",
            "linkedin.com/signup",
            "challenge",
        )
    ):
        return True

    if _has_locator(
        page,
        [
            "input[name='session_password']",
            "input[autocomplete='current-password']",
            "input[type='password']",
        ],
    ):
        return True

    text = _body_text(page).lower()
    return any(
        marker in text
        for marker in (
            "let's do a quick security check",
            "verify it's you",
            "security verification",
            "quick security check",
            "captcha",
            "two-step verification",
            "phone verification",
        )
    )


def _random_pause(min_seconds: float = 0.4, max_seconds: float = 1.0) -> None:
    time.sleep(random.uniform(min_seconds, max_seconds))


def _scroll_recent_posts(page: Any) -> None:
    for _ in range(2):
        page.mouse.wheel(0, 1400)
        _random_pause(0.8, 1.4)


def _extract_candidates(page: Any) -> list[dict[str, str]]:
    script = """
    () => {
      const roots = new Set();
      const rootSelectors = [
        'div.feed-shared-update-v2',
        'div[data-urn*="activity"]',
        'article',
        'a[href*="/feed/update/"]'
      ];

      for (const selector of rootSelectors) {
        document.querySelectorAll(selector).forEach((node) => {
          const root = node.closest('div.feed-shared-update-v2')
            || node.closest('[data-urn*="activity"]')
            || node.closest('article')
            || node.parentElement;
          if (root) roots.add(root);
        });
      }

      const textSelectors = [
        '.update-components-text',
        '.feed-shared-update-v2__description',
        '[data-test-id="main-feed-activity-card__commentary"]',
        '.break-words'
      ];

      const candidates = [];
      roots.forEach((root) => {
        const texts = [];
        textSelectors.forEach((selector) => {
          root.querySelectorAll(selector).forEach((node) => {
            const text = (node.innerText || '').trim();
            if (text) texts.push(text);
          });
        });
        const rawText = texts.sort((a, b) => b.length - a.length)[0] || (root.innerText || '').trim();
        const links = Array.from(root.querySelectorAll('a[href*="/feed/update/"], a[href*="urn:li:activity"]'))
          .map((node) => node.href)
          .filter(Boolean);
        const dataUrn = root.getAttribute('data-urn')
          || (root.querySelector('[data-urn]') && root.querySelector('[data-urn]').getAttribute('data-urn'))
          || '';
        const authorNode = root.querySelector('.update-components-actor__name, .feed-shared-actor__name, [data-test-app-aware-link] span[aria-hidden="true"]');
        const timeCandidates = [];
        root.querySelectorAll('time, [datetime], .update-components-actor__sub-description, .feed-shared-actor__sub-description, .update-components-actor__supplementary-actor-info').forEach((node) => {
          [node.innerText, node.getAttribute('datetime'), node.getAttribute('aria-label'), node.getAttribute('title')].forEach((value) => {
            if (value && value.trim()) timeCandidates.push(value.trim());
          });
        });
        const timePattern = /(just now|moments ago|seconds ago|a minute ago|an hour ago|yesterday|\\b\\d+\\s*(?:m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)\\b)/i;
        const rootTimeMatch = (root.innerText || '').match(timePattern);
        const postedAtText = (timeCandidates.find((value) => timePattern.test(value)) || (rootTimeMatch && rootTimeMatch[0]) || timeCandidates[0] || '').trim();
        candidates.push({
          raw_text: rawText,
          post_url: links[0] || '',
          data_urn: dataUrn,
          author_name: authorNode ? authorNode.innerText.trim() : '',
          posted_at_text: postedAtText
        });
      });
      return candidates;
    }
    """
    try:
        candidates = page.evaluate(script)
    except Exception as exc:
        print(f"LinkedIn extraction script failed: {exc}")
        return []
    return candidates if isinstance(candidates, list) else []


def _normalize_candidate(candidate: dict[str, Any]) -> dict[str, Any] | None:
    raw_text = _clean_text(str(candidate.get("raw_text", "")))
    if len(raw_text) < 30:
        return None
    if any(marker in raw_text.lower() for marker in ("sign in", "join linkedin", "linkedin member")):
        return None

    activity_urn = _activity_urn(candidate.get("data_urn"), candidate.get("post_url"), raw_text)
    content_hash = _content_hash(raw_text)
    return {
        "post_id": activity_urn or content_hash,
        "post_url": _post_url(str(candidate.get("post_url", "")), activity_urn),
        "raw_text": raw_text,
        "author_name": _clean_text(str(candidate.get("author_name", ""))),
        "posted_at_text": _clean_text(str(candidate.get("posted_at_text", ""))),
        "fetched_at": _now(),
        "content_hash": content_hash,
        "source": "playwright",
    }


def _extract_posts_from_page(page: Any, max_posts: int) -> list[dict[str, Any]]:
    posts = []
    seen_keys: set[str] = set()
    for candidate in _extract_candidates(page):
        if not isinstance(candidate, dict):
            continue
        post = _normalize_candidate(candidate)
        if post is None:
            continue
        key = post["post_id"] or post["content_hash"]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        posts.append(post)
        if len(posts) >= max_posts:
            break
    return posts


def _extract_profile_details_from_page(page: Any) -> dict[str, Any]:
    script = r"""
    () => {
      const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
      const lines = (node) => (node && node.innerText || '')
        .split('\n')
        .map((part) => clean(part))
        .filter(Boolean);
      const firstText = (selectors) => {
        for (const selector of selectors) {
          const node = document.querySelector(selector);
          const text = clean(node && node.innerText);
          if (text) return text;
        }
        return '';
      };
      const visible = (node) => {
        if (!node || !node.getBoundingClientRect) return false;
        const rect = node.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      };
      const imageUrl = (node) => clean(
        node && (node.currentSrc || node.src || node.getAttribute('src') || node.getAttribute('data-delayed-url') || node.getAttribute('data-ghost-url'))
      );
      const firstAttr = (selectors, attrs) => {
        for (const selector of selectors) {
          const node = document.querySelector(selector);
          if (!node) continue;
          for (const attr of attrs) {
            const value = clean(node.getAttribute(attr));
            if (value) return value;
          }
        }
        return '';
      };
      const h1 = document.querySelector('main h1') || document.querySelector('h1');
      const h1Name = clean(h1 && h1.innerText);
      const stripConnectionDegree = (text) => clean((text || '').replace(/\s+[^A-Za-z0-9]*\d+(st|nd|rd|th)$/i, ''));
      const topCardRoot = (() => {
        if (!h1) return document.querySelector('main') || document.body;
        return h1.closest('section')
          || h1.closest('[data-member-id]')
          || h1.closest('[class*="top-card"]')
          || h1.closest('main')
          || document.querySelector('main')
          || document.body;
      })();
      const isDegreeLine = (text) => /^[^A-Za-z0-9]*\d+(st|nd|rd|th)\s*$/i.test(text);
      const isProfileCountLine = (text) => /\bfollowers?\b|\bconnections?\b/i.test(text);
      const isActionLine = (text) => /^(message|pending|more|connect|follow|following|open to|add profile section|enhance profile|skip to main content|\d+\s+notifications?)$/i.test(text);
      const isBadNameLine = (text) => {
        const value = clean(text);
        if (!value || value.length > 80) return true;
        if (isDegreeLine(value) || isProfileCountLine(value) || isActionLine(value)) return true;
        if (value.includes('|') || value.includes(',') || /contact info|linkedin|profile|followers|connections|notifications|skip to main content/i.test(value)) return true;
        return false;
      };
      const cleanLocationLine = (text) => clean(text.replace(/\s*[^A-Za-z0-9]*\s*contact info.*$/i, ''));
      const topCardLines = lines(topCardRoot);
      const h1ProfileName = stripConnectionDegree(h1Name);
      const inferredProfileName = (() => {
        const candidates = [h1ProfileName, ...topCardLines.map(stripConnectionDegree)];
        for (const candidate of candidates) {
          if (!isBadNameLine(candidate)) return candidate;
        }
        return '';
      })();
      const profileName = h1ProfileName || inferredProfileName;
      const profileSlug = profileName.toLowerCase();
      const nameIndex = Math.max(0, topCardLines.findIndex((part) => {
        const stripped = stripConnectionDegree(part);
        return stripped === profileName || part === profileName || part.startsWith(`${profileName} `);
      }));
      const orderedAfterName = topCardLines.slice(nameIndex + 1);
      const headlineFromTopCard = (() => {
        for (const line of orderedAfterName) {
          if (!line || isDegreeLine(line) || isProfileCountLine(line) || isActionLine(line)) continue;
          if (/contact info/i.test(line)) continue;
          if (stripConnectionDegree(line) === profileName) continue;
          return line;
        }
        return '';
      })();
      const locationFromTopCard = (() => {
        for (const line of orderedAfterName) {
          const candidate = cleanLocationLine(line);
          if (!candidate || candidate === headlineFromTopCard || candidate === profileName) continue;
          if (isDegreeLine(candidate) || isProfileCountLine(candidate) || isActionLine(candidate)) continue;
          if (/contact info/i.test(line) && candidate) return candidate;
          if (candidate.includes(',') && !candidate.includes('|')) return candidate;
        }
        return '';
      })();
      const profileImageFromTopCard = (() => {
        const images = Array.from(topCardRoot.querySelectorAll('img')).filter(visible);
        const scored = images
          .map((img) => {
            const src = imageUrl(img);
            const alt = clean(img.getAttribute('alt')).toLowerCase();
            const rect = img.getBoundingClientRect();
            const lowerSrc = src.toLowerCase();
            let score = 0;
            if (!src) score -= 1000;
            if (lowerSrc.includes('profile-displayphoto')) score += 100;
            if (alt && profileSlug && alt.includes(profileSlug)) score += 45;
            if (alt.includes('profile') || alt.includes('photo')) score += 20;
            if (rect.width >= 72 && rect.height >= 72) score += 20;
            if (rect.width > 320 || rect.height > 320) score -= 80;
            if (lowerSrc.includes('profile-backgroundimage') || lowerSrc.includes('company-logo') || lowerSrc.includes('ghost')) score -= 150;
            return { src, score };
          })
          .filter((item) => item.src && item.score > 0)
          .sort((left, right) => right.score - left.score);
        return scored.length ? scored[0].src : '';
      })();
      const sectionText = (labels) => {
        const sections = Array.from(document.querySelectorAll('main section, section, div[data-view-name]'));
        for (const section of sections) {
          const sectionLines = lines(section);
          if (!sectionLines.length) continue;
          const first = sectionLines[0].toLowerCase();
          if (!labels.includes(first)) continue;
          return sectionLines
            .slice(1)
            .filter((part) => !['show all', 'show more', 'see more'].includes(part.toLowerCase()))
            .join('\n');
        }
        return '';
      };
      const selectorName = firstText([
        'main h1',
        '.top-card-layout__title',
        '.pv-text-details__left-panel h1',
        'h1'
      ]);
      const name = stripConnectionDegree(selectorName) || profileName;
      const selectorHeadline = firstText([
        '.text-body-medium.break-words',
        '.top-card-layout__headline',
        '.pv-text-details__left-panel .text-body-medium',
        'main section div.text-body-medium'
      ]);
      const selectorHeadlineValid = (!isDegreeLine(selectorHeadline) && selectorHeadline !== name)
        ? selectorHeadline
        : '';
      const headline = headlineFromTopCard || selectorHeadlineValid;
      const selectorLocation = firstText([
        '.pv-text-details__left-panel .text-body-small.inline.t-black--light.break-words',
        '.pv-text-details__left-panel .text-body-small.t-black--light',
        '.top-card-layout__first-subline',
        'main section .text-body-small.inline.t-black--light.break-words'
      ]);
      const normalizedSelectorLocation = cleanLocationLine(selectorLocation);
      const selectorLocationValid = normalizedSelectorLocation
        && normalizedSelectorLocation !== headline
        && normalizedSelectorLocation !== name
        && !isDegreeLine(normalizedSelectorLocation)
        ? normalizedSelectorLocation
        : '';
      const location = locationFromTopCard || selectorLocationValid;
      const profileImageUrl = profileImageFromTopCard || firstAttr([
        'img.pv-top-card-profile-picture__image--show',
        '.pv-top-card-profile-picture__container img',
        '.pv-top-card-profile-picture__image img',
        '.profile-photo-edit__preview',
        '.top-card-layout__entity-image',
        'main section img[alt*="profile" i]',
        'main section img[alt*="photo" i]'
      ], ['src', 'data-delayed-url', 'data-ghost-url']);
      const about = sectionText(['about']);

      return { name, headline, about, location, profile_image_url: profileImageUrl };
    }
    """
    try:
        details = page.evaluate(script)
    except Exception as exc:
        print(f"LinkedIn profile details extraction failed: {exc}")
        return {}
    return details if isinstance(details, dict) else {}


def _extract_experience_from_page(page: Any) -> list[str]:
    script = r"""
    () => {
      const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
      const lines = (node) => (node && node.innerText || '')
        .split('\n')
        .map((part) => clean(part))
        .filter(Boolean);
      const isNoise = (value) => {
        const lower = clean(value).toLowerCase();
        if (!lower) return true;
        if (['show all', 'show more', 'see more', 'show less', '...'].includes(lower)) return true;
        if (/^(activate to view larger image|opens profile photo|company logo)$/i.test(lower)) return true;
        return false;
      };
      const uniqLines = (values) => {
        const result = [];
        values.forEach((value) => {
          if (!isNoise(value) && result[result.length - 1] !== value) result.push(value);
        });
        return result;
      };
      const hasDateRange = (value) => (
        /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\s*[-–]\s*(?:Present|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b/i
          .test(value || '')
      );
      const roots = new Set();
      const selectors = [
        'main [data-view-name="profile-component-entity"]',
        'main li.pvs-list__paged-list-item',
        'main li',
        '.experience__list li',
        '.profile-section-card'
      ];

      for (const selector of selectors) {
        document.querySelectorAll(selector).forEach((node) => {
          if (node.closest('aside')) return;
          const text = clean(node.innerText);
          if (!text || text.length < 12) return;
          if (selector === 'main li' && !hasDateRange(text)) return;
          const nestedExperienceItems = Array.from(node.querySelectorAll('li'))
            .filter((child) => child !== node && hasDateRange(clean(child.innerText)));
          if (nestedExperienceItems.length) return;
          roots.add(node);
        });
      }

      const items = [];
      roots.forEach((node) => {
        const itemLines = uniqLines(lines(node));
        if (itemLines.length < 2) return;
        const lower = itemLines.join(' ').toLowerCase();
        if (lower.includes('more profiles for you') || lower.includes('people also viewed')) return;
        items.push(itemLines.join('\n'));
      });

      if (items.length) {
        const seen = new Set();
        return items.filter((item) => {
          const key = item.toLowerCase();
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        }).slice(0, 25);
      }

      const sections = Array.from(document.querySelectorAll('main section, section'));
      for (const section of sections) {
        const sectionLines = lines(section);
        if (!sectionLines.length || sectionLines[0].toLowerCase() !== 'experience') continue;
        const experienceLines = sectionLines
          .slice(1)
          .filter((part) => !['show all', 'show more', 'see more'].includes(part.toLowerCase()));
        return experienceLines.length ? [experienceLines.join('\n')] : [];
      }

      return [];
    }
    """
    try:
        experience = page.evaluate(script)
    except Exception as exc:
        print(f"LinkedIn experience extraction failed: {exc}")
        return []
    return [str(item).strip() for item in experience if str(item).strip()] if isinstance(experience, list) else []


def _open_context(playwright: Any, mode: str) -> tuple[Any | None, Any]:
    if mode == "burner":
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(LINKEDIN_BROWSER_PROFILE_DIR),
            headless=LINKEDIN_HEADLESS,
            viewport={"width": 1365, "height": 900},
        )
        return None, context

    browser = playwright.chromium.launch(headless=LINKEDIN_HEADLESS)
    context = browser.new_context(viewport={"width": 1365, "height": 900})
    return browser, context


def fetch_recent_profile_posts(profile_url: str, max_posts: int = 5) -> list[dict[str, Any]]:
    mode = LINKEDIN_AUTOMATION_MODE.strip().lower()
    if mode not in {"logged_out", "burner"}:
        return _error("invalid_automation_mode", "LINKEDIN_AUTOMATION_MODE must be 'logged_out' or 'burner'.")

    if mode == "burner" and not has_bootstrapped_burner_session():
        return _error("burner_session_not_found", BOOTSTRAP_REQUIRED_MESSAGE)

    print(f"Starting read-only LinkedIn Playwright scrape in {mode} mode.")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return _error("playwright_unavailable", f"Playwright is not available: {exc}")

    browser = None
    context = None
    try:
        with sync_playwright() as playwright:
            browser, context = _open_context(playwright, mode)
            page = context.new_page()
            last_error = ""

            for url in _candidate_activity_urls(profile_url):
                print(f"Opening LinkedIn activity URL: {url}")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    if mode == "burner" and looks_like_login_or_challenge_page(page):
                        return _error("session_expired_or_challenged", SESSION_EXPIRED_MESSAGE)
                    if mode == "logged_out" and _has_login_wall(page):
                        last_error = "LinkedIn hid recent activity behind a login wall in logged-out mode."
                        continue

                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception:
                        pass
                    _random_pause()

                    if mode == "burner" and looks_like_login_or_challenge_page(page):
                        return _error("session_expired_or_challenged", SESSION_EXPIRED_MESSAGE)

                    _scroll_recent_posts(page)
                    posts = _extract_posts_from_page(page, max_posts)
                    if posts:
                        print(f"LinkedIn scraper extracted {len(posts)} post candidate(s).")
                        return posts

                    if mode == "logged_out" and _has_login_wall(page):
                        last_error = "LinkedIn hid recent activity behind a login wall in logged-out mode."
                except Exception as exc:
                    last_error = f"Could not read LinkedIn activity page: {exc}"

            if last_error:
                return _error("linkedin_page_unavailable", last_error)
            return _error("no_visible_posts", "No visible LinkedIn posts were found for this profile.")
    except Exception as exc:
        return _error("playwright_run_failed", f"Playwright browser run failed: {exc}")
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


def fetch_profile_details(profile_url: str) -> dict[str, Any]:
    mode = LINKEDIN_AUTOMATION_MODE.strip().lower()
    if mode not in {"logged_out", "burner"}:
        return _error("invalid_automation_mode", "LINKEDIN_AUTOMATION_MODE must be 'logged_out' or 'burner'.")[0]

    if mode == "burner" and not has_bootstrapped_burner_session():
        return _error("burner_session_not_found", BOOTSTRAP_REQUIRED_MESSAGE)[0]

    print(f"Starting read-only LinkedIn profile detail scrape in {mode} mode.")
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return _error("playwright_unavailable", f"Playwright is not available: {exc}")[0]

    browser = None
    context = None
    try:
        with sync_playwright() as playwright:
            browser, context = _open_context(playwright, mode)
            page = context.new_page()
            profile_url = profile_url.strip().rstrip("/") + "/"

            print(f"Opening LinkedIn profile URL: {profile_url}")
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            if mode == "burner" and looks_like_login_or_challenge_page(page):
                return _error("session_expired_or_challenged", SESSION_EXPIRED_MESSAGE)[0]
            if mode == "logged_out" and _has_login_wall(page):
                return _error("linkedin_profile_unavailable", "LinkedIn hid profile details behind a login wall.")[0]

            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            _random_pause()

            details = _extract_profile_details_from_page(page)
            experience: list[str] = []

            try:
                page.goto(_experience_url(profile_url), wait_until="domcontentloaded", timeout=30000)
                if mode == "burner" and looks_like_login_or_challenge_page(page):
                    return _error("session_expired_or_challenged", SESSION_EXPIRED_MESSAGE)[0]
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                _random_pause()
                experience = _extract_experience_from_page(page)
            except Exception as exc:
                print(f"Could not read LinkedIn experience page: {exc}")

            name = _clean_text(str(details.get("name", "")))
            headline = _clean_text(str(details.get("headline", "")))
            location = _clean_text(str(details.get("location", "")))
            if _looks_like_connection_degree(headline):
                headline = ""
            if not headline and _looks_like_headline_saved_as_location(location):
                headline = location
                location = ""
            if location == headline:
                location = ""
            if _looks_like_invalid_location(location):
                location = ""
            if _looks_like_invalid_profile_details(name, headline, location):
                return _error(
                    "linkedin_profile_not_found",
                    "LinkedIn profile page was not found or did not expose a valid creator profile.",
                )[0]

            return {
                "name": name,
                "headline": headline,
                "about": _clean_text(str(details.get("about", ""))),
                "location": location,
                "profile_image_url": str(details.get("profile_image_url", "")).strip(),
                "experience": experience,
                "fetched_at": _now(),
                "source": "playwright",
            }
    except Exception as exc:
        return _error("playwright_run_failed", f"Playwright browser run failed: {exc}")[0]
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
