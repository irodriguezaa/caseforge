"""Normalized RN scope contract shared by DAMCO projection and the Tata parser."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

RnVendor = Literal["damco", "tata"]

NORMALIZED_BUCKETS = (
    "technical_epics",
    "nco",
    "qco",
    "qa_bugs",
    "qc_bugs",
    "tri",
    "incidents",
    "known_issues",
    "qa_evidence",
)

# Hits consumed by CaseForge / DAMCO counts. Tata extras are omitted here on purpose.
LEGACY_BUCKETS = ("functionality", "nco", "tri", "qa_qc")


@dataclass
class RnItem:
    id: str
    title: str
    section: str = ""
    table_header: str = ""
    column: str = ""
    tbrf_id: str | None = None
    page: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class NormalizedRnScope:
    vendor: RnVendor
    device: str | None = None
    family: str | None = None
    version: str | None = None
    technical_epics: list[RnItem] = field(default_factory=list)
    nco: list[RnItem] = field(default_factory=list)
    qco: list[RnItem] = field(default_factory=list)
    qa_bugs: list[RnItem] = field(default_factory=list)
    qc_bugs: list[RnItem] = field(default_factory=list)
    tri: list[RnItem] = field(default_factory=list)
    incidents: list[RnItem] = field(default_factory=list)
    known_issues: list[RnItem] = field(default_factory=list)
    qa_evidence: list[RnItem] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "vendor": self.vendor,
            "device": self.device,
            "family": self.family,
            "version": self.version,
        }
        for name in NORMALIZED_BUCKETS:
            payload[name] = [item.to_dict() for item in getattr(self, name)]
        return payload

    def ids_for(self, bucket: str) -> list[str]:
        return [item.id for item in getattr(self, bucket)]


def damco_scope_from_legacy_hits(
    hits: list[tuple[str, str, str]],
    *,
    device: str | None = None,
    version: str | None = None,
) -> NormalizedRnScope:
    """Project DAMCO 4-bucket hits without moving QCO's & QA's into qco[]."""
    scope = NormalizedRnScope(vendor="damco", device=device, family=device, version=version)
    seen: dict[str, set[str]] = {name: set() for name in (*NORMALIZED_BUCKETS, "functionality")}
    for ticket_id, cell_text, bucket in hits:
        key = ticket_id.strip().upper()
        if not key:
            continue
        item = RnItem(id=key, title=cell_text)
        if bucket == "functionality":
            target = "technical_epics"
        elif bucket in ("nco", "tri"):
            target = bucket
        else:
            # qa_qc and anything else stay off the Tata-only arrays.
            continue
        if key in seen[target]:
            continue
        seen[target].add(key)
        getattr(scope, target).append(item)
    return scope


def tata_legacy_hits(scope: NormalizedRnScope) -> list[tuple[str, str, str]]:
    """Only Technical Epics become functionality. QCO/Incident never become qa_qc/tri."""
    hits: list[tuple[str, str, str]] = []
    mapping = (
        ("technical_epics", "functionality"),
        ("nco", "nco"),
        ("tri", "tri"),
        ("qa_bugs", "qa_bugs"),
        ("qc_bugs", "qc_bugs"),
        ("qco", "qco"),
        ("incidents", "incidents"),
        ("known_issues", "known_issues"),
        ("qa_evidence", "qa_evidence"),
    )
    seen: set[tuple[str, str]] = set()
    for attr, legacy in mapping:
        for item in getattr(scope, attr):
            pair = (item.id.upper(), legacy)
            if pair in seen:
                continue
            seen.add(pair)
            hits.append((item.id, item.title, legacy))
    return hits
