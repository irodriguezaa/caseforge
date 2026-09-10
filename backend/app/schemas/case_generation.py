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


class CoverageUnit(BaseModel):
    """What must be covered. Not a Test Case."""

    coverage_id: str
    role: Literal["A", "G"]
    behavior: str
    scenario: str
    evidence: str
    jira_key: str | None = None
    rn_key: str | None = None
    feature_story: str | None = None
    condition_b: str | None = None
    outline_strategy: str = "single"
    technical_group: str | None = None
    traceability: str = ""
    body: str = ""
    extra_test_data: str | None = None
    requires_condition: bool = False
    description: str = ""
    rn_filename: str = ""
    artifact_key: str = ""
    story_key: str = ""
    observable_then: list[str] = Field(default_factory=list)
    technical_notes: list[str] = Field(default_factory=list)
    special_condition: str | None = None
    normal_precondition: str | None = None

    def for_llm(self) -> dict:
        return {
            "coverage_id": self.coverage_id,
            "role": self.role,
            "behavior": self.behavior,
            "scenario": self.scenario,
            "evidence": (self.evidence or "")[:1200],
            "jira_key": self.jira_key,
            "rn_key": self.rn_key,
            "feature_story": self.feature_story,
            "condition_b": self.condition_b,
            "outline_strategy": self.outline_strategy,
            "technical_group": self.technical_group,
            "traceability": self.traceability,
        }


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
    source_type: str | None = None
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
    covers: list[str] = Field(default_factory=list)


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
    coverage_unit_count: int = 0
    covered_coverage_ids: list[str] = Field(default_factory=list)
    uncovered_coverage_ids: list[str] = Field(default_factory=list)
    brfs_analyzed: int = 0
    device_review_count: int = 0
    possible_duplicate_count: int = 0
