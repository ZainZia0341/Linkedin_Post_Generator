export type ExperienceItem = {
  heading: string;
  details: string[];
};

const DATE_RANGE_PATTERN =
  /\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\s*[-\u2013]\s*(?:Present|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4})\b/i;
const EMPLOYMENT_PATTERN =
  /\b(?:full-time|part-time|contract|freelance|self-employed|internship|apprenticeship|temporary|seasonal)\b/i;
const DURATION_PATTERN = /^(?:\d+\s*(?:yrs?|years?|mos?|months?))(?:\s+\d+\s*(?:mos?|months?))?$/i;
const ROLE_PATTERN =
  /\b(?:architect|associate|chief|consultant|contractor|developer|director|engineer|executive|founder|head|lead|manager|officer|owner|partner|president|principal|specialist|technologist|vice president|vp)\b/i;

export function parseExperience(experience: string[]): ExperienceItem[] {
  return experience.flatMap(parseExperienceBlock).filter((item) => item.heading);
}

export function formatExperienceForClipboard(experience: string[]) {
  return parseExperience(experience)
    .map((item) => [item.heading, ...item.details].join("\n"))
    .join("\n\n");
}

function parseExperienceBlock(value: string): ExperienceItem[] {
  const lines = value
    .split(/\n+/)
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean);
  if (!lines.length) return [];

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
