const JIRA_BROWSE_BASE = "https://dlatvarg.atlassian.net/browse";
const JIRA_KEY_RE = /\b([A-Z][A-Z0-9_]+-\d+)\b/gi;

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
