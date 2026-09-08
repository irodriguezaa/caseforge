"""Release KPI calculations. Volume counts QC Release rows; cluster KPI counts participations."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.release import Release, ReleaseStatus, ReleaseType
from app.schemas.be_release import BE_CLUSTER_INDIVIDUAL, BE_CLUSTER_TODOS, BE_SWF_VALUES
from app.schemas.kpis import (
    ClusterParticipation,
    DeliverableReleaseKpi,
    ReleaseKpisRead,
    ReleaseVolumeMonth,
    RevalidationKpi,
    SwfDistributionKpi,
    SwfReleaseKpi,
    UnclassifiedSwfKpi,
)

OFFICIAL_CLUSTERS = BE_CLUSTER_INDIVIDUAL
SIN_ENTREGABLE_LABEL = "Sin entregable"


def release_origin_kind(rel: Release) -> str:
    if rel.be_release_id is not None:
        return "BE"
    if rel.operativa_release_id is not None:
        return "OPERATIVA"
    return "APP"


def _created_at_month_key(created_at: datetime) -> str:
    if created_at.tzinfo is not None:
        created_at = created_at.astimezone(timezone.utc)
    return created_at.strftime("%Y-%m")


def _empty_month_bucket(month: str) -> dict[str, int | str]:
    return {"month": month, "total": 0, "app": 0, "be": 0, "operativa": 0}


def _fill_month_range(by_month: dict[str, dict[str, int | str]]) -> list[ReleaseVolumeMonth]:
    if not by_month:
        return []
    keys = sorted(by_month)
    start_y, start_m = (int(part) for part in keys[0].split("-"))
    end_y, end_m = (int(part) for part in keys[-1].split("-"))
    filled: list[ReleaseVolumeMonth] = []
    year, month = start_y, start_m
    while (year, month) <= (end_y, end_m):
        key = f"{year:04d}-{month:02d}"
        bucket = by_month.get(key) or _empty_month_bucket(key)
        filled.append(ReleaseVolumeMonth.model_validate(bucket))
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return filled


def _expand_cluster_values(values: list[str] | None) -> tuple[str, ...]:
    """Map stored cluster labels to official clusters. 'Todos' is not a sixth cluster."""
    if not values:
        return ()
    cleaned = [item.strip() for item in values if isinstance(item, str) and item.strip()]
    if not cleaned:
        return ()
    if BE_CLUSTER_TODOS in cleaned:
        return OFFICIAL_CLUSTERS
    return tuple(name for name in OFFICIAL_CLUSTERS if name in cleaned)


def clusters_for_qc_release(rel: Release) -> tuple[str, ...]:
    """BE uses be_releases.clusters JSON. App/Operativa use releases.cluster. Never the BE concat label."""
    if rel.be_release_id is not None:
        raw = rel.be_release.clusters if rel.be_release is not None else None
        return _expand_cluster_values(raw)
    if not rel.cluster:
        return ()
    return _expand_cluster_values([rel.cluster])


def load_kpi_releases(db: Session) -> list[Release]:
    """Same universe as volume/cluster: rows in `releases`, not CANCELLED. Draft wizards are out."""
    return list(
        db.execute(
            select(Release)
            .options(selectinload(Release.be_release), selectinload(Release.deliverable))
            .where(Release.status != ReleaseStatus.CANCELLED)
        )
        .scalars()
        .all()
    )


def _deliverable_kpis(rows: list[Release]) -> list[DeliverableReleaseKpi]:
    """App only. Dynamic Entregables from FK. BE and Operativas are excluded."""

    @dataclass
    class _Bucket:
        deliverable_id: int | None
        deliverable_name: str
        releases: int = 0
        app_versions: set[str] = field(default_factory=set)

    buckets: dict[int | None, _Bucket] = {}
    for rel in rows:
        if release_origin_kind(rel) != "APP":
            continue
        key = rel.deliverable_id
        bucket = buckets.get(key)
        if bucket is None:
            name = rel.deliverable.name if rel.deliverable is not None else SIN_ENTREGABLE_LABEL
            bucket = _Bucket(deliverable_id=key, deliverable_name=name)
            buckets[key] = bucket
        bucket.releases += 1
        version = (rel.version or "").strip()
        if version:
            bucket.app_versions.add(version)

    items = [
        DeliverableReleaseKpi(
            deliverable_id=bucket.deliverable_id,
            deliverable_name=bucket.deliverable_name,
            releases=bucket.releases,
            versions=len(bucket.app_versions) if bucket.app_versions else None,
        )
        for bucket in buckets.values()
    ]
    items.sort(
        key=lambda row: (-row.releases, -(row.versions or 0), row.deliverable_name.lower())
    )
    return items


def swf_for_app_platform(platform: str | None) -> str | None:
    """Deterministic App platform → SWF. AAF variants are HITSS. Unknown platforms stay unclassified."""
    if not platform or not platform.strip():
        return None
    key = " ".join(platform.strip().split()).casefold()
    if key == "web" or key.startswith("web "):
        return "HITSS"
    if key.startswith("aaf"):
        return "HITSS"
    if key == "adt" or key.startswith("adt "):
        return "HITSS"
    if key in {"firetv", "fire tv"} or key.startswith("firetv") or key.startswith("fire tv"):
        return "HITSS"
    if "xbox" in key or key in {"win", "windows"} or key.startswith("win/") or key.startswith("win "):
        return "HITSS"
    if key == "ios" or key.startswith("ios "):
        return "NEORIS"
    if key == "tvos" or key.startswith("tvos"):
        return "NEORIS"
    if key == "roku" or key.startswith("roku"):
        return "NEORIS"
    if "coship" in key:
        return "NEORIS"
    if key == "adr" or key.startswith("adr "):
        return "NEORIS"
    if key == "stb iptv" or key.startswith("stb iptv"):
        return "TATA"
    if key.startswith("stv tata"):
        return "TATA"
    if key in {"sctcl", "atscl"}:
        return "TATA"
    return None


def _swf_distribution(rows: list[Release]) -> SwfDistributionKpi:
    """One count per Release. Operativas excluded. BE uses persisted swf only."""
    counts: Counter[str] = Counter()
    unclassified: Counter[tuple[str, str | None, str]] = Counter()
    considered = 0
    for rel in rows:
        kind = release_origin_kind(rel)
        if kind == "OPERATIVA":
            continue
        considered += 1
        if kind == "BE":
            persisted = rel.be_release.swf if rel.be_release is not None else None
            if persisted in BE_SWF_VALUES:
                counts[persisted] += 1
            else:
                unclassified[("BE", rel.platform, "BE sin SWF persistido")] += 1
            continue
        mapped = swf_for_app_platform(rel.platform)
        if mapped is None:
            unclassified[("APP", rel.platform, "plataforma App sin mapping SWF")] += 1
        else:
            counts[mapped] += 1

    by_swf = [
        SwfReleaseKpi(
            swf=name,
            releases=count,
            percent=round(count * 100 / considered, 1) if considered else 0.0,
        )
        for name, count in counts.items()
    ]
    by_swf.sort(key=lambda row: (-row.releases, row.swf.lower()))
    unclassified_rows = [
        UnclassifiedSwfKpi(origin=origin, platform=platform, count=count, reason=reason)
        for (origin, platform, reason), count in unclassified.items()
    ]
    unclassified_rows.sort(key=lambda row: (-row.count, row.origin, row.platform or ""))
    return SwfDistributionKpi(
        considered=considered,
        unclassified=sum(row.count for row in unclassified_rows),
        by_swf=by_swf,
        unclassified_rows=unclassified_rows,
    )


def _revalidation_kpis(rows: list[Release], total: int, app: int) -> RevalidationKpi:
    """Uses persisted release_type only. BE/Operativa are not typed."""
    nuevo = 0
    revalidacion = 0
    untyped_app = 0
    for rel in rows:
        if release_origin_kind(rel) != "APP":
            continue
        if rel.release_type == ReleaseType.NUEVO:
            nuevo += 1
        elif rel.release_type == ReleaseType.REVALIDACION:
            revalidacion += 1
        else:
            untyped_app += 1
    percent = round(revalidacion * 100 / app, 1) if app else 0.0
    return RevalidationKpi(
        total=total,
        app=app,
        nuevo=nuevo,
        revalidacion=revalidacion,
        untyped_app=untyped_app,
        revalidacion_percent=percent,
        scope="APP",
    )


def compute_release_volume_kpis(db: Session) -> ReleaseKpisRead:
    """Non-CANCELLED rows in `releases`. Drafts in be_releases/operativa_releases are out.

    Month = created_at (CaseForge create), never start_date. Multi-cluster BE counts once
    in volume and once per official cluster in participations.
    """
    rows = load_kpi_releases(db)
    totals = Counter(release_origin_kind(rel) for rel in rows)
    app = totals.get("APP", 0)
    be = totals.get("BE", 0)
    operativa = totals.get("OPERATIVA", 0)
    total = app + be + operativa
    by_month: dict[str, dict[str, int | str]] = {}
    cluster_counts: Counter[str] = Counter()
    for rel in rows:
        key = _created_at_month_key(rel.created_at)
        bucket = by_month.setdefault(key, _empty_month_bucket(key))
        bucket["total"] = int(bucket["total"]) + 1
        kind = release_origin_kind(rel)
        if kind == "APP":
            bucket["app"] = int(bucket["app"]) + 1
        elif kind == "BE":
            bucket["be"] = int(bucket["be"]) + 1
        else:
            bucket["operativa"] = int(bucket["operativa"]) + 1
        cluster_counts.update(clusters_for_qc_release(rel))

    by_cluster = [
        ClusterParticipation(cluster=name, count=cluster_counts.get(name, 0))
        for name in OFFICIAL_CLUSTERS
    ]
    validations = sum(item.count for item in by_cluster)
    avg = round(validations / total, 2) if total else 0.0
    return ReleaseKpisRead(
        total=total,
        app=app,
        be=be,
        operativa=operativa,
        by_month=_fill_month_range(by_month),
        by_cluster=by_cluster,
        cluster_validations_total=validations,
        clusters_per_release_avg=avg,
        by_deliverable=_deliverable_kpis(rows),
        swf=_swf_distribution(rows),
        revalidation=_revalidation_kpis(rows, total, app),
    )
