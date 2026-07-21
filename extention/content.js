function cleanText(value) {
  return (value || "").replace(/\s+/g, " ").trim();
}

function pageError() {
  const url = window.location.href.toLowerCase();
  const body = cleanText(document.body?.innerText).toLowerCase();
  if (
    url.includes("/login") ||
    url.includes("/checkpoint") ||
    url.includes("/authwall") ||
    body.includes("sign in to linkedin") ||
    body.includes("security verification") ||
    body.includes("quick security check") ||
    body.includes("two-step verification") ||
    body.includes("phone verification") ||
    body.includes("captcha")
  ) {
    return {
      code: "session_expired_or_challenged",
      error: "The Chrome burner session is logged out or LinkedIn is showing a verification challenge."
    };
  }
  return null;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function scrollRecentPosts() {
  for (let index = 0; index < 2; index += 1) {
    window.scrollBy({ top: 1400, behavior: "smooth" });
    await delay(900 + Math.random() * 600);
  }
}

function extractPostCandidates() {
  const roots = new Set();
  const rootSelectors = [
    "div.feed-shared-update-v2",
    "div[data-urn*='activity']",
    "article",
    "a[href*='/feed/update/']"
  ];
  for (const selector of rootSelectors) {
    document.querySelectorAll(selector).forEach((node) => {
      const root = node.closest("div.feed-shared-update-v2")
        || node.closest("[data-urn*='activity']")
        || node.closest("article")
        || node.parentElement;
      if (root) roots.add(root);
    });
  }

  const textSelectors = [
    ".update-components-text",
    ".feed-shared-update-v2__description",
    "[data-test-id='main-feed-activity-card__commentary']",
    ".break-words"
  ];
  const profileHref = (anchor) => {
    try {
      const url = new URL(anchor.href, window.location.origin);
      return /^\/in\/[^/]+\/?$/.test(url.pathname);
    } catch (_) {
      return false;
    }
  };
  const profileCard = (anchor, root) => {
    let container = anchor;
    let paragraphs = [];
    let cursor = anchor;
    for (let depth = 0; depth < 5 && cursor && cursor !== root; depth += 1) {
      const lines = Array.from(cursor.querySelectorAll("p"))
        .map((node) => cleanText(node.innerText))
        .filter(Boolean);
      if (lines.length >= 2) {
        container = cursor;
        paragraphs = lines;
        break;
      }
      cursor = cursor.parentElement;
    }
    const stripProfile = (value) => cleanText(value)
      .replace(/^view\s+/i, "")
      .replace(/[\u2019']s\s+profile.*$/i, "")
      .replace(/\s+profile.*$/i, "");
    const labelName = stripProfile(anchor.getAttribute("aria-label"));
    const imageName = stripProfile(anchor.querySelector("img")?.alt);
    const anchorName = cleanText(anchor.innerText);
    const hasEvidence = paragraphs.length >= 2
      || Boolean(anchor.querySelector("img, figure"))
      || /profile/i.test(cleanText(anchor.getAttribute("aria-label")));
    if (!hasEvidence) return null;
    const name = paragraphs.find((line) => (
      line.length <= 120
      && !/^(follow|connect|message)$/i.test(line)
      && !/^(just now|moments ago|\d+\s*(?:m|h|d|w|mo|yr)s?)/i.test(line)
    )) || labelName || imageName || anchorName;
    if (!name || name.length > 160) return null;
    return {
      anchor,
      container,
      href: anchor.href,
      name,
      score: paragraphs.length + (anchor.querySelector("img, figure") ? 2 : 0) + (labelName ? 1 : 0)
    };
  };
  const longestText = (entries) => entries
    .map((entry) => entry.text)
    .filter(Boolean)
    .sort((left, right) => right.length - left.length)[0] || "";
  const comparablePostText = (value) => cleanText(value)
    .toLowerCase()
    .replace(/\bhashtag\s+#?/g, "#")
    .replace(/[\u201c\u201d]/g, '"')
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/\s*\.\.\.\s*more$/i, "")
    .replace(/\s+/g, " ")
    .trim();
  const isDuplicatePostText = (left, right) => {
    const first = comparablePostText(left);
    const second = comparablePostText(right);
    if (!first || !second) return false;
    if (first === second) return true;
    const shorter = first.length <= second.length ? first : second;
    const longer = first.length > second.length ? first : second;
    return shorter.length >= 80
      && longer.includes(shorter)
      && shorter.length / longer.length >= 0.85;
  };

  const candidates = [];
  roots.forEach((root) => {
    const textEntries = [];
    const seenTextNodes = new Set();
    textSelectors.forEach((selector) => {
      root.querySelectorAll(selector).forEach((node) => {
        if (seenTextNodes.has(node)) return;
        seenTextNodes.add(node);
        const text = cleanText(node.innerText);
        if (text) textEntries.push({ node, text });
      });
    });
    const rootText = cleanText(root.innerText);
    const profileCards = [];
    Array.from(root.querySelectorAll("a[href*='/in/']"))
      .filter(profileHref)
      .forEach((anchor) => {
        const card = profileCard(anchor, root);
        if (!card) return;
        const duplicateIndex = profileCards.findIndex((existing) => (
          existing.href === card.href
          && (existing.container.contains(card.anchor) || card.container.contains(existing.anchor))
        ));
        if (duplicateIndex < 0) profileCards.push(card);
        else if (card.score > profileCards[duplicateIndex].score) profileCards[duplicateIndex] = card;
      });
    profileCards.sort((left, right) => {
      if (left.anchor === right.anchor) return 0;
      const position = left.anchor.compareDocumentPosition(right.anchor);
      return position & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
    });

    let nestedPost = null;
    if (profileCards.length >= 2) {
      const outerAuthor = profileCards[0].anchor;
      let cursor = profileCards[1].anchor;
      while (cursor.parentElement && cursor.parentElement !== root && !cursor.parentElement.contains(outerAuthor)) {
        cursor = cursor.parentElement;
        nestedPost = cursor;
      }
    }
    const nestedEntries = nestedPost ? textEntries.filter((entry) => nestedPost.contains(entry.node)) : [];
    const commentaryEntries = nestedPost
      ? textEntries.filter((entry) => !nestedPost.contains(entry.node) && !entry.node.contains(nestedPost))
      : [];
    const originalPostText = longestText(nestedEntries);
    const repostText = longestText(commentaryEntries);
    const effectiveRepostText = isDuplicatePostText(repostText, originalPostText) ? "" : repostText;
    const isRepost = Boolean(/\breposted this\b/i.test(rootText) || (nestedPost && originalPostText));
    const directText = longestText(textEntries) || rootText;
    const rawText = isRepost && originalPostText ? originalPostText : directText;
    const links = Array.from(root.querySelectorAll("a[href*='/feed/update/'], a[href*='urn:li:activity']"))
      .map((node) => node.href)
      .filter(Boolean);
    const dataUrn = root.getAttribute("data-urn")
      || root.querySelector("[data-urn]")?.getAttribute("data-urn")
      || "";
    const authorNode = root.querySelector(
      ".update-components-actor__name, .feed-shared-actor__name, [data-test-app-aware-link] span[aria-hidden='true']"
    );
    const timeCandidates = [];
    root.querySelectorAll(
      "time, [datetime], .update-components-actor__sub-description, .feed-shared-actor__sub-description, .update-components-actor__supplementary-actor-info"
    ).forEach((node) => {
      [node.innerText, node.getAttribute("datetime"), node.getAttribute("aria-label"), node.getAttribute("title")]
        .forEach((value) => {
          if (value?.trim()) timeCandidates.push(value.trim());
        });
    });
    const timePattern = /(?:^|[\s\u2022\u00b7])(just now|moments ago|seconds ago|a minute ago|an hour ago|yesterday|\d+\s*(?:secs?|seconds?|mins?|minutes?|hrs?|hours?|days?|weeks?|wks?|months?|mos?|years?|yrs?|s|m|h|d|w|mo|y)(?:\s+ago)?)(?=$|[\s\u2022\u00b7])/i;
    const postedAtText = timeCandidates
      .map((value) => cleanText(value).match(timePattern)?.[1] || "")
      .find(Boolean) || "";
    candidates.push({
      raw_text: rawText,
      post_url: links[0] || "",
      data_urn: dataUrn,
      author_name: profileCards[0]?.name || cleanText(authorNode?.innerText),
      posted_at_text: postedAtText,
      is_repost: isRepost,
      repost_text: isRepost ? effectiveRepostText : "",
      original_post_text: isRepost ? rawText : "",
      original_author_name: isRepost ? profileCards[1]?.name || "" : "",
      original_author_url: isRepost ? profileCards[1]?.href || "" : ""
    });
  });
  return candidates;
}

function extractProfileDetails() {
  const lines = (node) => (node?.innerText || "")
    .split("\n")
    .map(cleanText)
    .filter(Boolean);
  const firstText = (selectors) => {
    for (const selector of selectors) {
      const text = cleanText(document.querySelector(selector)?.innerText);
      if (text) return text;
    }
    return "";
  };
  const visible = (node) => {
    const rect = node?.getBoundingClientRect?.();
    return Boolean(rect && rect.width > 0 && rect.height > 0);
  };
  const imageUrl = (node) => cleanText(
    node?.currentSrc || node?.src || node?.getAttribute("src")
      || node?.getAttribute("data-delayed-url") || node?.getAttribute("data-ghost-url")
  );
  const h1 = document.querySelector("main h1") || document.querySelector("h1");
  const stripDegree = (text) => cleanText((text || "").replace(/\s+[^A-Za-z0-9]*\d+(st|nd|rd|th)$/i, ""));
  const main = document.querySelector("main") || document.body;
  const identityRoot = (() => {
    let cursor = h1;
    for (let depth = 0; cursor && cursor !== main && depth < 9; depth += 1) {
      const text = cleanText(cursor.innerText);
      if (text && cursor.querySelector("img") && text.length < 5000) return cursor;
      cursor = cursor.parentElement;
    }
    return h1?.closest("section")
      || h1?.closest("[data-member-id]")
      || h1?.closest("[class*='top-card']")
      || main;
  })();
  const topCard = identityRoot;
  const isDegree = (text) => /^[^A-Za-z0-9]*\d+(st|nd|rd|th)\s*$/i.test(text);
  const isCount = (text) => /\bfollowers?\b|\bconnections?\b/i.test(text);
  const isAction = (text) => /^(message|pending|more|connect|follow|following|open to|add profile section|enhance profile|skip to main content|\d+\s+notifications?)$/i.test(text);
  const badName = (text) => {
    const value = cleanText(text);
    return !value || value.length > 80 || isDegree(value) || isCount(value) || isAction(value)
      || value.includes("|") || value.includes(",")
      || /contact info|linkedin|profile|followers|connections|notifications|skip to main content/i.test(value);
  };
  const topLines = lines(topCard);
  const h1Name = stripDegree(cleanText(h1?.innerText));
  const name = h1Name || [h1Name, ...topLines.map(stripDegree)].find((candidate) => !badName(candidate)) || "";
  const nameIndex = Math.max(0, topLines.findIndex((part) => stripDegree(part) === name || part.startsWith(`${name} `)));
  const afterName = topLines.slice(nameIndex + 1);
  const headline = afterName.find((line) => (
    line && !isDegree(line) && !isCount(line) && !isAction(line)
    && !/contact info/i.test(line) && stripDegree(line) !== name
  )) || firstText([
    ".text-body-medium.break-words",
    ".top-card-layout__headline",
    ".pv-text-details__left-panel .text-body-medium"
  ]);
  const cleanLocation = (text) => cleanText((text || "").replace(/\s*[^A-Za-z0-9]*\s*contact info.*$/i, ""));
  const location = cleanLocation(afterName.find((line) => {
    const candidate = cleanLocation(line);
    return candidate && candidate !== headline && candidate !== name && !isDegree(candidate)
      && !isCount(candidate) && !isAction(candidate) && candidate.includes(",") && !candidate.includes("|");
  }) || firstText([
    ".pv-text-details__left-panel .text-body-small.inline.t-black--light.break-words",
    ".top-card-layout__first-subline"
  ]));
  const profileName = name.toLowerCase();
  const currentProfilePath = (() => {
    const match = window.location.pathname.match(/^\/in\/[^/]+/i);
    return match ? `${match[0].toLowerCase()}/` : "";
  })();
  const linkedProfilePath = (node) => {
    const anchor = node.closest("a[href*='/in/']");
    if (!anchor) return "";
    try {
      const path = new URL(anchor.href, window.location.origin).pathname.toLowerCase();
      const match = path.match(/^\/in\/[^/]+/i);
      return match ? `${match[0]}/` : "";
    } catch (_) {
      return "";
    }
  };
  const profileImageUrl = Array.from(topCard.querySelectorAll("img"))
    .filter(visible)
    .map((img) => {
      const src = imageUrl(img);
      const alt = cleanText(img.alt).toLowerCase();
      const rect = img.getBoundingClientRect();
      const lowerSrc = src.toLowerCase();
      const imageProfilePath = linkedProfilePath(img);
      let score = 0;
      if (!src) score -= 1000;
      if (imageProfilePath && currentProfilePath && imageProfilePath !== currentProfilePath) score -= 1000;
      if (imageProfilePath && currentProfilePath && imageProfilePath === currentProfilePath) score += 160;
      if (alt && profileName && (alt === profileName || alt.includes(profileName))) score += 120;
      if (lowerSrc.includes("profile-displayphoto")) score += 35;
      if (rect.width >= 72 && rect.height >= 72) score += 20;
      if (rect.width > 320 || rect.height > 320) score -= 80;
      if (/profile-backgroundimage|company-logo|ghost|article-cover|feedshare/.test(lowerSrc)) score -= 300;
      return { src, score };
    })
    .filter((item) => item.src && item.score >= 80)
    .sort((left, right) => right.score - left.score)[0]?.src || "";
  const sectionText = (label) => {
    const sectionSelectors = [
      `main [componentkey*='${label}' i]`,
      `main [data-view-name*='${label}' i]`,
      "main section",
      "main [aria-label]"
    ];
    const sections = [];
    sectionSelectors.forEach((selector) => {
      document.querySelectorAll(selector).forEach((node) => {
        if (!sections.includes(node)) sections.push(node);
      });
    });
    const contentAfterLabel = (sectionLines) => {
      const labelIndex = sectionLines.findIndex((part) => part.toLowerCase() === label);
      if (labelIndex < 0) return "";
      const stopLabels = new Set([
        "activity", "experience", "education", "skills", "interests", "featured",
        "recommendations", "licenses & certifications", "licenses and certifications"
      ]);
      const content = [];
      for (const part of sectionLines.slice(labelIndex + 1)) {
        const lower = part.toLowerCase();
        if (stopLabels.has(lower)) break;
        if (["show all", "show more", "see more", "show less", "... more"].includes(lower)) continue;
        if (/^top skills$/i.test(part)) break;
        content.push(part.replace(/\s*\.\.\.\s*more$/i, "").trim());
      }
      return content.filter(Boolean).join("\n");
    };
    for (const section of sections) {
      if (section.closest("aside, nav, footer")) continue;
      const sectionLines = lines(section);
      const content = contentAfterLabel(sectionLines);
      if (content) return content;
    }
    const labelNodes = Array.from(main.querySelectorAll("h2, h3, p, span, div"))
      .filter((node) => cleanText(node.innerText).toLowerCase() === label);
    for (const labelNode of labelNodes) {
      let cursor = labelNode.parentElement;
      for (let depth = 0; cursor && cursor !== main && depth < 7; depth += 1) {
        const content = contentAfterLabel(lines(cursor));
        if (content) return content;
        cursor = cursor.parentElement;
      }
    }
    return "";
  };
  return {
    name: stripDegree(name),
    headline: isDegree(headline) || headline === name ? "" : cleanText(headline),
    about: sectionText("about"),
    location: cleanText(location),
    profile_image_url: profileImageUrl,
    source: "extension",
    fetched_at: new Date().toISOString()
  };
}

async function scrapeProfileDetails() {
  window.scrollTo({ top: 0, behavior: "auto" });
  await delay(250);
  const details = extractProfileDetails();
  if (details.about) return details;

  let previousTop = -1;
  for (let index = 0; index < 10; index += 1) {
    const nextTop = Math.min(
      document.documentElement.scrollHeight,
      window.scrollY + Math.max(550, Math.floor(window.innerHeight * 0.8))
    );
    if (nextTop === previousTop) break;
    previousTop = nextTop;
    window.scrollTo({ top: nextTop, behavior: "auto" });
    await delay(350 + Math.random() * 250);
    const about = extractProfileDetails().about;
    if (about) return { ...details, about };
  }
  return details;
}

function extractExperience() {
  const lines = (node) => (node?.innerText || "")
    .split("\n")
    .map(cleanText)
    .filter(Boolean);
  const isNoise = (value) => {
    const lower = cleanText(value).toLowerCase();
    return !lower
      || ["show all", "show more", "see more", "show less", "..."].includes(lower)
      || /^(activate to view larger image|opens profile photo|company logo)$/i.test(lower);
  };
  const uniqueLines = (values) => {
    const result = [];
    values.forEach((value) => {
      if (!isNoise(value) && result[result.length - 1] !== value) result.push(value);
    });
    return result;
  };
  const hasDateRange = (value) => (
    /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\s*[-\u2013]\s*(?:Present|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b/i
      .test(value || "")
  );
  const scope = document.querySelector("main") || document;
  const roots = new Set();
  const items = [];
  const addItem = (itemLines) => {
    const cleaned = uniqueLines(itemLines);
    if (cleaned.length < 2 || !hasDateRange(cleaned.join(" "))) return;
    const lower = cleaned.join(" ").toLowerCase();
    if (lower.includes("more profiles for you") || lower.includes("people also viewed")) return;
    items.push(cleaned.join("\n"));
  };
  const descriptionText = (container) => cleanText(
    container?.querySelector("[data-testid='expandable-text-box']")?.innerText
  );
  const isDescriptionParagraph = (paragraph) => Boolean(
    paragraph.querySelector("[data-testid='expandable-text-box']")
  );
  const paragraphData = (container, excludedContainer = null) => {
    const paragraphs = Array.from(container?.querySelectorAll("p") || [])
      .filter((paragraph) => !isDescriptionParagraph(paragraph))
      .filter((paragraph) => !excludedContainer || !excludedContainer.contains(paragraph));
    const titleParagraph = paragraphs.find((paragraph) => paragraph.hasAttribute("style"))
      || paragraphs[0]
      || null;
    const title = cleanText(titleParagraph?.innerText);
    const metadata = uniqueLines(paragraphs
      .filter((paragraph) => paragraph !== titleParagraph)
      .map((paragraph) => cleanText(paragraph.innerText)));
    return { title, metadata };
  };
  const roleLines = ({ title, company, metadata, description }) => {
    const dateIndex = metadata.findIndex(hasDateRange);
    const beforeDate = dateIndex >= 0 ? metadata.slice(0, dateIndex) : metadata;
    const afterDate = dateIndex >= 0 ? metadata.slice(dateIndex) : [];
    const companyLine = cleanText(company)
      || beforeDate.find((value) => !/^\d+\s+(?:yr|yrs|mo|mos)\b/i.test(value))
      || "";
    return uniqueLines([
      title,
      companyLine,
      ...afterDate,
      description
    ]);
  };

  const componentRoots = Array.from(scope.querySelectorAll("[componentkey^='entity-collection-item']"))
    .filter((node) => !node.closest("aside, nav, footer"))
    .filter((node) => {
      const parent = node.parentElement?.closest("[componentkey^='entity-collection-item']");
      return !parent;
    });
  componentRoots.forEach((node) => {
    const groupedList = Array.from(node.querySelectorAll("ul")).find((list) => (
      Array.from(list.children).some((child) => (
        child.tagName === "LI" && hasDateRange(cleanText(child.innerText))
      ))
    ));
    const nestedItems = groupedList
      ? Array.from(groupedList.children).filter((child) => (
        child.tagName === "LI" && hasDateRange(cleanText(child.innerText))
      ))
      : [];
    if (!nestedItems.length) {
      const { title, metadata } = paragraphData(node);
      addItem(roleLines({
        title,
        company: "",
        metadata,
        description: descriptionText(node)
      }));
      return;
    }
    const groupHeader = paragraphData(node, groupedList);
    const companyName = groupHeader.title
      || groupHeader.metadata.find((part) => (
        !hasDateRange(part) && !/^\d+\s+(?:yr|yrs|mo|mos)\b/i.test(part)
      ))
      || "";
    nestedItems.forEach((child) => {
      const { title, metadata } = paragraphData(child);
      addItem(roleLines({
        title,
        company: companyName,
        metadata,
        description: descriptionText(child)
      }));
    });
  });

  const selectors = [
    "main [data-view-name='profile-component-entity']",
    "main li.pvs-list__paged-list-item",
    "main li",
    ".experience__list li",
    ".profile-section-card"
  ];
  selectors.forEach((selector) => {
    document.querySelectorAll(selector).forEach((node) => {
      if (node.closest("aside")) return;
      if (node.closest("[componentkey^='entity-collection-item']")) return;
      const text = cleanText(node.innerText);
      if (!text || text.length < 12) return;
      if (selector === "main li" && !hasDateRange(text)) return;
      const nestedItems = Array.from(node.querySelectorAll("li"))
        .filter((child) => child !== node && hasDateRange(cleanText(child.innerText)));
      if (!nestedItems.length) roots.add(node);
    });
  });
  roots.forEach((node) => {
    addItem(lines(node));
  });
  if (items.length) {
    return items.filter((item, index) => (
      items.findIndex((candidate) => candidate.toLowerCase() === item.toLowerCase()) === index
    ));
  }
  const sections = Array.from(document.querySelectorAll("main section, section"));
  for (const section of sections) {
    const sectionLines = lines(section);
    if (sectionLines[0]?.toLowerCase() !== "experience") continue;
    const experienceLines = sectionLines.slice(1)
      .filter((part) => !["show all", "show more", "see more"].includes(part.toLowerCase()));
    return experienceLines.length ? [experienceLines.join("\n")] : [];
  }
  return [];
}

async function scrapeExperience() {
  window.scrollTo({ top: 0, behavior: "auto" });
  await delay(250);
  const collected = new Map();
  let previousTop = -1;
  let unchangedPasses = 0;

  for (let index = 0; index < 35; index += 1) {
    const before = collected.size;
    extractExperience().forEach((item) => collected.set(item.toLowerCase(), item));
    unchangedPasses = collected.size === before ? unchangedPasses + 1 : 0;

    const maxTop = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    const nextTop = Math.min(maxTop, window.scrollY + Math.max(500, Math.floor(window.innerHeight * 0.75)));
    if ((nextTop === previousTop || nextTop >= maxTop) && unchangedPasses >= 2) break;
    previousTop = nextTop;
    window.scrollTo({ top: nextTop, behavior: "auto" });
    await delay(350 + Math.random() * 250);
  }

  extractExperience().forEach((item) => collected.set(item.toLowerCase(), item));
  return Array.from(collected.values());
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const error = pageError();
  if (error) {
    sendResponse(error);
    return false;
  }
  if (message?.type === "SCRAPE_POSTS") {
    scrollRecentPosts()
      .then(() => extractPostCandidates())
      .then((data) => sendResponse({ data }))
      .catch((caught) => sendResponse({ error: caught instanceof Error ? caught.message : String(caught) }));
    return true;
  }
  if (message?.type === "SCRAPE_PROFILE") {
    scrapeProfileDetails()
      .then((data) => sendResponse({ data }))
      .catch((caught) => sendResponse({ error: caught instanceof Error ? caught.message : String(caught) }));
    return true;
  }
  if (message?.type === "SCRAPE_EXPERIENCE") {
    scrapeExperience()
      .then((data) => sendResponse({ data }))
      .catch((caught) => sendResponse({ error: caught instanceof Error ? caught.message : String(caught) }));
    return true;
  }
  return false;
});
