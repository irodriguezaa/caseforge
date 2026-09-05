"""Structured candidate Test Cases proposed by the Release Apps AI engine.

These are preview-only: they are not TestCase/TestStep rows. QC reviews them before any persist.
"""

from typing import Literal

from pydantic import BaseModel, Field


class CandidateStep(BaseModel):
    step_number: int
    action: str
    expected_result: str
    test_data: str | None = None


class GeneratedCaseCandidate(BaseModel):
    name: str
    description: str
    precondition: str | None = None
    requires_condition: bool = False
    steps: list[CandidateStep] = Field(default_factory=list)
    test_data: str | None = None
    related_functionality: str | None = None
    related_jira: str | None = None
    related_rn: str | None = None
    evidence: str
    justification: str
    possible_duplicate_of: str | None = None
    confidence: Literal["high", "medium", "low"] = "medium"
    review_required: bool = True
    basic_validation: bool = False
    priority: Literal["BLOCKER", "CRITICAL"] | None = None
    user_type: str | None = None
    use_case_key: str | None = None
    use_case_title: str | None = None
    access_path: str | None = None
    component: str | None = None
    applied_rules: list[str] = Field(default_factory=list)
    generation_origin: str | None = None
    origin_release_id: int | None = None
    origin_release_name: str | None = None
    related_origin_case_ids: list[str] = Field(default_factory=list)
    device: str | None = None
    country: str | None = None
    device_source: str | None = None
    mdp: str | None = None
    behavior: str | None = None
    hn_keys: list[str] = Field(default_factory=list)
    candidate_id: str | None = None
    duplicate_status: Literal["UNIQUE", "POSSIBLE_DUPLICATE", "OVERLAP"] | None = None
    duplicate_with: list[str] = Field(default_factory=list)
    priority_reason: str | None = None
    ecosystem: str | None = None
    applicability_reason: str | None = None
    group_id: str | None = None
    interaction_points: list[str] = Field(default_factory=list)
    hn_source: str | None = None


class GenerationStats(BaseModel):
    """How the A–G classifier treated source Scenarios in this run. Not a target count."""

    discarded_c: int = 0
    discarded_d: int = 0
    discarded_e: int = 0
    discarded_f: int = 0
    converted_b: int = 0
    materialized_a: int = 0
    materialized_g: int = 0
    consolidated_functional: int = 0
    attached_support: int = 0
    examples_a: list[str] = Field(default_factory=list)
    examples_b: list[str] = Field(default_factory=list)
    examples_c: list[str] = Field(default_factory=list)
    examples_d: list[str] = Field(default_factory=list)
    examples_e: list[str] = Field(default_factory=list)
    examples_f: list[str] = Field(default_factory=list)
    examples_g: list[str] = Field(default_factory=list)
    examples_consolidated: list[str] = Field(default_factory=list)


class GenerateCasesResponse(BaseModel):
    status: str
    message: str
    release_id: int
    release_name: str
    validation_type: str | None = None
    has_analysis: bool
    engine: str
    candidates: list[GeneratedCaseCandidate] = Field(default_factory=list)
    persisted: bool = False
    already_generated: bool = False
    test_case_count: int = 0
    estimation_hours: float = 0
    estimation_days: float = 0
    generation_stats: GenerationStats | None = None
    analysis_details: list[str] = Field(default_factory=list)
    brfs_analyzed: int = 0
    device_review_count: int = 0
    possible_duplicate_count: int = 0
