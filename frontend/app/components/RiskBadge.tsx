import type { RiskLevel } from "@/lib/types";

const LABELS: Record<RiskLevel, string> = { LOW: "Bajo", MEDIUM: "Medio", HIGH: "Alto" };
const CLASSES: Record<RiskLevel, string> = {
  LOW: "risk-badge risk-low",
  MEDIUM: "risk-badge risk-medium",
  HIGH: "risk-badge risk-high",
};

export function RiskBadge({ level }: { level: RiskLevel }): React.ReactElement {
  return <span className={CLASSES[level]}>{LABELS[level]}</span>;
}
