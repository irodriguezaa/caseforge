const JIRA_BROWSE_BASE = "https://dlatvarg.atlassian.net/browse";

export function jiraIssueUrl(key: string): string | null {
  const trimmed = key.trim();
  if (!/^[A-Z][A-Z0-9_]+-\d+$/i.test(trimmed)) {
    return null;
  }
  return `${JIRA_BROWSE_BASE}/${encodeURIComponent(trimmed)}`;
}
