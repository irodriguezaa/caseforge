const toneByStatus: Record<string, string> = {
  DRAFT: "badge-neutral",
  IN_PROGRESS: "badge-info",
  COMPLETED: "badge-ok",
  CANCELLED: "badge-error",
  UNEXECUTED: "badge-neutral",
  PASS: "badge-ok",
  FAIL: "badge-error",
  BLOCKED: "badge-warning",
  N_A: "badge-neutral",
};

export function StatusBadge({ status }: { status: string }): React.ReactElement {
  const tone = toneByStatus[status] ?? "badge-neutral";
  return <span className={`badge ${tone}`}>{status.replace("_", " ")}</span>;
}
