"""Release KPI schemas. Volume first; later cluster/SWF/retrabajo can attach here."""

from pydantic import BaseModel, Field


class ReleaseVolumeMonth(BaseModel):
    """One calendar month of QC Release volume. App + BE + Operativa == total."""

    month: str  # YYYY-MM from releases.created_at
    total: int = 0
    app: int = 0
    be: int = 0
    operativa: int = 0


class ClusterParticipation(BaseModel):
    cluster: str
    count: int = 0


class DeliverableReleaseKpi(BaseModel):
    """One Entregable from App Releases only. versions is null only if none apply."""

    deliverable_id: int | None = None
    deliverable_name: str
    releases: int = 0
    versions: int | None = None


class SwfReleaseKpi(BaseModel):
    swf: str
    releases: int = 0
    percent: float = 0.0


class UnclassifiedSwfKpi(BaseModel):
    origin: str
    platform: str | None = None
    count: int = 0
    reason: str


class SwfDistributionKpi(BaseModel):
    """App + BE only. Operativas are out of scope."""

    considered: int = 0
    unclassified: int = 0
    by_swf: list[SwfReleaseKpi] = Field(default_factory=list)
    unclassified_rows: list[UnclassifiedSwfKpi] = Field(default_factory=list)


class RevalidationKpi(BaseModel):
    """Nuevo / Revalidación from persisted release_type. App only; BE/OPE have no type."""

    total: int = 0
    app: int = 0
    nuevo: int = 0
    revalidacion: int = 0
    untyped_app: int = 0
    revalidacion_percent: float = 0.0
    scope: str = "APP"


class ReleaseKpisRead(BaseModel):
    """KPIs → Releases V1: volume, cluster, deliverable, SWF, revalidaciones."""

    total: int = 0
    app: int = 0
    be: int = 0
    operativa: int = 0
    by_month: list[ReleaseVolumeMonth] = Field(default_factory=list)
    by_cluster: list[ClusterParticipation] = Field(default_factory=list)
    cluster_validations_total: int = 0
    clusters_per_release_avg: float = 0.0
    by_deliverable: list[DeliverableReleaseKpi] = Field(default_factory=list)
    swf: SwfDistributionKpi = Field(default_factory=SwfDistributionKpi)
    revalidation: RevalidationKpi = Field(default_factory=RevalidationKpi)
