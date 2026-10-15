const JIRA_BROWSE_BASE = "https://dlatvarg.atlassian.net/browse";
const JIRA_ISSUES_BASE = "https://dlatvarg.atlassian.net/issues";
const JIRA_KEY_RE = /\b([A-Z][A-Z0-9_]+-\d+)\b/gi;
const JIRA_FILTER_RE = /(?:[?&]filter=|\/filters\/)(\d+)/i;

export function jiraFilterUrl(filterId: string | null | undefined): string | null {
  const id = String(filterId ?? "")
    .replace(/^#/, "")
    .trim();
  if (!/^\d+$/.test(id)) {
    return null;
  }
  return `${JIRA_ISSUES_BASE}?filter=${encodeURIComponent(id)}`;
}

export function parseJiraFilterId(raw: string | null | undefined): string | null {
  if (!raw) {
    return null;
  }
  const text = raw.trim();
  if (/^\d+$/.test(text)) {
    return text;
  }
  const match = JIRA_FILTER_RE.exec(text);
  return match?.[1] ?? null;
}

export function jiraIssueUrl(key: string): string | null {
  const trimmed = key.trim();
  if (!/^[A-Z][A-Z0-9_]+-\d+$/i.test(trimmed)) {
    return null;
  }
  return `${JIRA_BROWSE_BASE}/${encodeURIComponent(trimmed.toUpperCase())}`;
}

export function parseJiraTicketKeys(raw: string | null | undefined): string[] {
  if (!raw) {
    return [];
  }
  const found: string[] = [];
  const seen = new Set<string>();
  for (const match of raw.matchAll(JIRA_KEY_RE)) {
    const key = match[1].toUpperCase();
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    found.push(key);
  }
  return found;
}
