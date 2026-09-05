"""Intermediate coverage matrix for Operativas — pre device expansion / TC generation."""

from typing import Literal

from pydantic import BaseModel, Field


class HnCoverageRecord(BaseModel):
    """Where each HN of a selected BRF landed. Grouping does not delete HN content."""

    brf_key: str
    hn_key: str
    status: Literal[
        "COVERED",
        "ABSORBED",
        "UPDATED_BY",
        "OUT_OF_SCOPE",
        "DEPENDENCY",
        "QC_REVIEW",
        "UNCOVERED",
    ]
    behavior_keys: list[str] = Field(default_factory=list)
    related_hn: list[str] = Field(default_factory=list)
    disposition: Literal[
        "PRIMARY_BEHAVIOR",
        "SUPPORTING",
        "SCENARIO",
        "TEST_DATA",
        "DEPENDENCY_CONFIGURATION",
        "OOS_QC",
    ] | None = None
    reason: str


class CoverageMatrixRow(BaseModel):
    brf_key: str
    epc_keys: list[str] = Field(default_factory=list)
    hn_keys: list[str] = Field(default_factory=list)
    behavior_key: str
    behavior_title: str
    interaction_points: list[str] = Field(default_factory=list)
    channel: str | None = None
    ecosystem: str | None = None
    applicable_devices: list[str] = Field(default_factory=list)
    relevant_users: list[str] = Field(default_factory=list)
    transactional: bool = False
    mdp: list[str] = Field(default_factory=list)
    test_data: str | None = None
    origin: Literal["directo", "derivado", "inferencia", "QC_REVIEW"] = "directo"
    source: str = "BRF/HN"
    hn_source: str | None = None
    scope_status: Literal["IN_SCOPE", "OUT_OF_SCOPE"] = "IN_SCOPE"
    behavior_reason: str | None = None
    reasoning: str | None = None
    evidence: str
    applicability_reason: str
    duplicate_risk: Literal["UNIQUE", "POSSIBLE_DUPLICATE", "OVERLAP"] = "UNIQUE"
    duplicate_with: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)


class CoverageMatrixResponse(BaseModel):
    status: str
    engine: str
    release_id: int
    release_name: str
    brfs_analyzed: int = 0
    row_count: int = 0
    rows: list[CoverageMatrixRow] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    hn_source_by_brf: dict[str, str] = Field(default_factory=dict)
    hn_coverage: list[HnCoverageRecord] = Field(default_factory=list)
