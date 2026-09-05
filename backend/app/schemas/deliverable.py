from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.release import ReleaseStatus, ReleaseType


class DeliverableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    updated_at: datetime


class DeliverableReleaseSummary(BaseModel):
    """One row of the Deliverable's version tree / 'Release origen' dropdown."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    version: str
    status: ReleaseStatus
    release_type: ReleaseType | None
    parent_release_id: int | None
    deliverable_id: int | None
    created_at: datetime


class DeliverableWithMetrics(DeliverableRead):
    """Backs the 'X versiones QC · N Evolutiva(s) · M Revalidación(es)' summary.

    Deliberately does NOT include any quality score or traffic-light -- per product decision,
    only raw counts are computed at this phase.
    """

    total_versions: int = 0
    total_evolutivas: int = 0
    total_revalidaciones: int = 0
    total_defects: int = 0
    latest_release_id: int | None = None
    latest_release_status: ReleaseStatus | None = None
    releases: list[DeliverableReleaseSummary] = Field(default_factory=list)
