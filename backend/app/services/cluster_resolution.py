"""Cluster normalization shared by the CSV importer and the Jira sync client.

Rules per the QC team's existing documented methodology (README_metodologia.md, section 3):
- Direct values map 1:1 to CaseForge's 5-value Cluster vocabulary (AUP/Andina/CENAM/
  Dominicana/Global); "Mexico"/"Colombia" fold into Global.
- Jira's combined value "Andina/Dominicana" is split by reading the country mentioned in the
  ticket's Summary (word-boundary, case-insensitive): Ecuador/Peru/Chile -> Andina;
  Dominicana/RD -> Dominicana; Colombia -> Global. If no country is found, the combined value
  is kept as-is (not silently dropped) so it's visible as its own "needs manual review" bucket,
  matching how the reference tool counted it separately.
"""

import re

_ANDINA_COUNTRY_RE = re.compile(r"\b(ECUADOR|PER[UÚ]|CHILE)\b", re.IGNORECASE)
_DOMINICANA_RE = re.compile(r"\b(DOMINICANA|RD)\b", re.IGNORECASE)
_COLOMBIA_RE = re.compile(r"\bCOLOMBIA\b", re.IGNORECASE)

_DIRECT_ALIASES = {
    "AUP": "AUP",
    "ANDINA": "Andina",
    "CENAM": "CENAM",
    "DOMINICANA": "Dominicana",
    "GLOBAL": "Global",
    "MEXICO": "Global",
    "MÉXICO": "Global",
    "COLOMBIA": "Global",
}
_REGION_FOLDED_INTO_GLOBAL = {"MEXICO", "MÉXICO", "COLOMBIA"}
_COMBINED_UNRESOLVED_KEY = "ANDINA/DOMINICANA"


def resolve_cluster(raw_cluster: str | None, summary: str | None) -> tuple[str | None, str | None]:
    """Returns (normalized_cluster_or_None, warning_message_or_None)."""
    if not raw_cluster:
        return None, None

    key = raw_cluster.strip().upper()

    if key == _COMBINED_UNRESOLVED_KEY:
        text = summary or ""
        if _DOMINICANA_RE.search(text):
            return "Dominicana", f"Cluster '{raw_cluster}' resuelto a Dominicana según el Resumen."
        if _ANDINA_COUNTRY_RE.search(text):
            return "Andina", f"Cluster '{raw_cluster}' resuelto a Andina según el Resumen."
        if _COLOMBIA_RE.search(text):
            return "Global", f"Cluster '{raw_cluster}' resuelto a Global (Colombia) según el Resumen."
        return (
            raw_cluster.strip(),
            f"Cluster '{raw_cluster}' no se pudo resolver desde el Resumen -- revisar manualmente.",
        )

    normalized = _DIRECT_ALIASES.get(key)
    if normalized is None:
        return None, f"Cluster '{raw_cluster}' no reconocido, se importó sin cluster."

    if key in _REGION_FOLDED_INTO_GLOBAL:
        return normalized, f"Cluster '{raw_cluster}' se agrupó bajo Global."

    return normalized, None
