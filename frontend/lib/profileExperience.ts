export type ExperienceItem = {
  heading: string;
  company: string;
  period: string;
  details: string[];
};

type RawExperienceItem = {
  heading: string;
  details: string[];
};

const DATE_RANGE_PATTERN =
  /\b(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+)?\d{4}\s*[-\u2013]\s*(?:Present|(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+)?\d{4})\b/i;
const EMPLOYMENT_PATTERN =
  /\b(?:full-time|part-time|contract|freelance|self-employed|internship|apprenticeship|temporary|seasonal)\b/i;
const DURATION_PATTERN = /^(?:\d+\s*(?:yrs?|years?|mos?|months?))(?:\s+\d+\s*(?:mos?|months?))?$/i;
const ROLE_PATTERN =
  /\b(?:architect|associate|chief|consultant|contractor|developer|director|engineer|executive|founder|head|lead|manager|officer|owner|partner|president|principal|specialist|technologist|vice president|vp)\b/i;
const DURATION_PREFIX_PATTERN =
  /^(?:\s*[\u00b7-]\s*)?((?:\d+\s*(?:yrs?|years?)(?:\s+\d+\s*(?:mos?|months?))?)|(?:\d+\s*(?:mos?|months?)))(?:\s+|$)(.*)$/i;

export function parseExperience(experience: string[]): ExperienceItem[] {
  return experience
    .flatMap(parseExperienceBlock)
    .filter((item) => item.heading)
    .map(structureExperienceItem);
}

export function formatExperienceForClipboard(experience: string[]) {
  return parseExperience(experience)
    .map((item) => [item.heading, item.company, item.period, ...item.details].filter(Boolean).join("\n"))
    .join("\n\n");
}

function parseExperienceBlock(value: string): RawExperienceItem[] {
  let lines = value
    .split(/\n+/)
    .map(normalizeExperienceText)
    .filter(Boolean);
  if (!lines.length) return [];

  if (lines.length === 1) {
    lines = splitConcatenatedExperience(lines[0]);
  }

  const dateIndexes = lines
    .map((line, index) => (DATE_RANGE_PATTERN.test(line) ? index : -1))
    .filter((index) => index >= 0);
  if (!dateIndexes.length) {
    return [{ heading: lines[0], details: lines.slice(1) }];
  }

  const boundaries = dateIndexes.map((dateIndex) => {
    const previous = lines[dateIndex - 1] || "";
    const hasEmploymentLine = EMPLOYMENT_PATTERN.test(previous);
    const previousLooksLikeRole = ROLE_PATTERN.test(previous);
    const hasCompanyLine = dateIndex >= 2 && (hasEmploymentLine || !previousLooksLikeRole);
    const headingIndex = Math.max(0, dateIndex - (hasCompanyLine ? 2 : 1));
    const groupedCompanyIndex =
      hasEmploymentLine
      && DURATION_PATTERN.test(lines[headingIndex - 1] || "")
      && headingIndex >= 2
        ? headingIndex - 2
        : headingIndex;
    return {
      dateIndex,
      headingIndex,
      startIndex: groupedCompanyIndex,
    };
  });

  return boundaries.map((boundary, index) => {
    const nextStart = boundaries[index + 1]?.startIndex ?? lines.length;
    const leadingDetails = lines
      .slice(boundary.startIndex, boundary.dateIndex)
      .filter((_, lineOffset) => boundary.startIndex + lineOffset !== boundary.headingIndex);
    const trailingDetails = lines.slice(boundary.dateIndex, nextStart);
    return {
      heading: lines[boundary.headingIndex],
      details: dedupeLines([...leadingDetails, ...trailingDetails]),
    };
  });
}

function dedupeLines(lines: string[]) {
  const seen = new Set<string>();
  return lines.filter((line) => {
    const key = line.toLowerCase();
    if (!line || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function structureExperienceItem(item: RawExperienceItem): ExperienceItem {
  const lines = dedupeLines(item.details.map(normalizeExperienceText));
  const dateIndex = lines.findIndex((line) => DATE_RANGE_PATTERN.test(line));
  const company = dateIndex > 0 ? lines.slice(0, dateIndex).join(" \u00b7 ") : "";
  let period = dateIndex >= 0 ? lines[dateIndex] : "";
  let details = dateIndex >= 0 ? lines.slice(dateIndex + 1) : lines.slice(company ? 1 : 0);

  if (period && details.length && isLikelyLocation(details[0])) {
    period = `${period} \u00b7 ${details[0]}`;
    details = details.slice(1);
  }

  return {
    heading: normalizeExperienceText(item.heading),
    company,
    period,
    details,
  };
}

function splitConcatenatedExperience(value: string) {
  const line = normalizeExperienceText(value);
  const dateMatch = line.match(DATE_RANGE_PATTERN);
  if (!dateMatch || dateMatch.index === undefined || dateMatch.index === 0) return [line];

  const beforeDate = line.slice(0, dateMatch.index).replace(/[\u00b7-]+\s*$/, "").trim();
  const employmentMatch = beforeDate.match(EMPLOYMENT_PATTERN);
  const heading = employmentMatch?.index
    ? beforeDate.slice(0, employmentMatch.index).replace(/[\u00b7-]+\s*$/, "").trim()
    : beforeDate;
  const company = employmentMatch?.index !== undefined
    ? beforeDate.slice(employmentMatch.index).trim()
    : "";
  const tail = line.slice(dateMatch.index + dateMatch[0].length).trim();
  const { periodSuffix, details } = splitConcatenatedTail(tail);
  const period = [dateMatch[0], periodSuffix].filter(Boolean).join(" \u00b7 ");

  return [heading, company, period, ...details].filter(Boolean);
}

function splitConcatenatedTail(value: string) {
  const cleanValue = value.replace(/^[\s\u00b7-]+/, "").trim();
  const durationMatch = cleanValue.match(DURATION_PREFIX_PATTERN);
  const duration = durationMatch?.[1] || "";
  const remainder = (durationMatch?.[2] ?? cleanValue).trim();
  if (!remainder) return { periodSuffix: duration, details: [] as string[] };

  const parts = remainder
    .split(/\s+(?:-|\u2013|\u2014)\s+(?=[A-Z\u201c\"])/)
    .map((part) => part.trim())
    .filter(Boolean);
  const firstPart = parts[0] || "";
  const location = isLikelyLocation(firstPart) ? firstPart : "";
  const details = location ? parts.slice(1) : parts;

  return {
    periodSuffix: [duration, location].filter(Boolean).join(" \u00b7 "),
    details,
  };
}

function isLikelyLocation(value: string) {
  const line = value.trim();
  if (!line || line.length > 90 || /https?:\/\//i.test(line)) return false;
  if (/[.!?]/.test(line) || /^(?:i|we|led|built|managed|developed|designed|created|owned|provided|worked|responsible|cross-functional|owner|uber)\b/i.test(line)) {
    return false;
  }
  return true;
}

function normalizeExperienceText(value: string) {
  return value
    .replace(/\u00c2\u00b7/g, "\u00b7")
    .replace(/\u00e2\u0080\u0093/g, "\u2013")
    .replace(/\u00e2\u0080\u0094/g, "\u2014")
    .replace(/\u00e2\u0080\u00a6/g, "...")
    .replace(/\s+/g, " ")
    .trim();
}
