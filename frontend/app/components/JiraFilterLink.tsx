import type { ReactElement } from "react";
import { jiraFilterUrl } from "@/lib/jira";

export function JiraFilterLink({
  filterId,
  hash = true,
}: {
  filterId: string | null | undefined;
  hash?: boolean;
}): ReactElement | null {
  const id = String(filterId ?? "")
    .replace(/^#/, "")
    .trim();
  if (!id) {
    return null;
  }
  const href = jiraFilterUrl(id);
  const label = hash ? `#${id}` : id;
  if (!href) {
    return <>{label}</>;
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" title={`Abrir filtro ${id} en Jira`}>
      {label}
    </a>
  );
}
