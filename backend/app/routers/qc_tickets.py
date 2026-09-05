"""QcTicket endpoints: independent defect-radar import pipeline and KPIs aggregation.

Same Import -> Validate -> Preview -> Approve -> Persist pattern already used for Test Cases,
kept as a fully separate pipeline since QcTicket has no relationship to Release/TestCase/Defect.
"""

import logging
from datetime import datetime, timezone
from collections import Counter

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps.auth import require_dashboard
from app.models.qc_ticket import QcTicket, QcTicketSource, QcTicketView
from app.schemas.qc_tickets import (
    QcTicketBulkCreateError,
    QcTicketBulkCreateResult,
    QcTicketCreate,
    QcTicketImportPreviewResponse,
    QcTicketImportRowError,
    QcTicketJiraRefreshFilterResult,
    QcTicketJiraRefreshResult,
    QcTicketRead,
    QcTicketStats,
)
from app.services import jira_client
from app.services.jira_client import JiraApiError, JiraFetchResult, JiraNotConfiguredError, RADAR_FILTERS
from app.services.qc_ticket_imports import QcTicketImportStructureError, parse_file, validate_rows

router = APIRouter(
    prefix="/api/v1/qc-tickets",
    tags=["qc-tickets"],
    dependencies=[Depends(require_dashboard)],
)
logger = logging.getLogger(__name__)


@router.post("/import/preview", response_model=QcTicketImportPreviewResponse)
async def preview_qc_ticket_import(
    file: UploadFile,
    view: QcTicketView = Form(...),
    source: QcTicketSource = Form(...),
    db: Session = Depends(get_db),
) -> QcTicketImportPreviewResponse:
    if file.filename is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No se recibió ningún archivo.")

    content = await file.read()
    try:
        rows = parse_file(file.filename, content)
    except QcTicketImportStructureError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="; ".join(exc.messages)) from exc

    valid, errors, warnings, excluded_cancelled, linked_keys_by_issue = validate_rows(rows, view, source)

    existing_keys = {
        (key, stored_view, stored_source)
        for key, stored_view, stored_source in db.execute(
            select(QcTicket.issue_key, QcTicket.view, QcTicket.source)
        ).all()
    }
    still_valid: list[QcTicketCreate] = []
    for ticket in valid:
        if (ticket.issue_key, ticket.view, ticket.source) in existing_keys:
            errors.append(
                QcTicketImportRowError(
                    issue_key=ticket.issue_key, message=f"'{ticket.issue_key}' ya existe en CaseForge."
                )
            )
        else:
            still_valid.append(ticket)

    # Fuga genuina (Release + LEAKED only): a leaked ticket that already has a QC/QA Bug linked
    # (any Jira link type) was already caught by QA/QC before deriving into a prod issue, so it
    # is NOT a genuine leak. Cross-referenced against QC/QA Bugs (view=RELEASE, source=
    # QC_DETECTED) already persisted in CaseForge. If none exist yet, the cross can't be
    # computed (matches the README note) -- is_attributed stays None (unknown), not False.
    if view == QcTicketView.RELEASE and source == QcTicketSource.LEAKED:
        known_qc_bug_keys = set(
            db.execute(
                select(QcTicket.issue_key).where(
                    QcTicket.view == QcTicketView.RELEASE, QcTicket.source == QcTicketSource.QC_DETECTED
                )
            ).scalars()
        )
        if known_qc_bug_keys:
            for ticket in still_valid:
                linked = linked_keys_by_issue.get(ticket.issue_key, [])
                ticket.is_attributed = bool(set(linked) & known_qc_bug_keys)

    return QcTicketImportPreviewResponse(
        valid=still_valid,
        errors=errors,
        warnings=warnings,
        total_rows=len(rows),
        excluded_cancelled_count=excluded_cancelled,
        valid_count=len(still_valid),
        error_count=len(errors),
    )


@router.post("/bulk", response_model=QcTicketBulkCreateResult, status_code=status.HTTP_201_CREATED)
def bulk_create_qc_tickets(
    payload: list[QcTicketCreate], db: Session = Depends(get_db)
) -> QcTicketBulkCreateResult:
    """Transactional: any row failing rolls back the whole batch.

    Two-phase for performance at scale (thousands of rows from a real Jira export): tries one
    fast add_all()+flush() first, since the common case is "everything in `payload` already
    passed preview validation and will insert cleanly". Only falls back to the slower per-row
    savepoint loop -- needed to pinpoint exactly which row(s) failed -- if that fast path
    raises. SQLAlchemyError is caught broadly, not just IntegrityError/DataError, and always
    turned into a clean per-row error response instead of an opaque 500.
    """
    try:
        rows = [QcTicket(**ticket.model_dump()) for ticket in payload]
        db.add_all(rows)
        db.flush()
    except SQLAlchemyError:
        db.rollback()
        tentative: list[QcTicket] = []
        errors: list[QcTicketBulkCreateError] = []
        for ticket in payload:
            savepoint = db.begin_nested()
            row = QcTicket(**ticket.model_dump())
            db.add(row)
            try:
                db.flush()
            except SQLAlchemyError as exc:
                savepoint.rollback()
                logger.warning("qc_ticket bulk import row failed: %s (%s)", ticket.issue_key, exc)
                errors.append(
                    QcTicketBulkCreateError(
                        issue_key=ticket.issue_key,
                        message=f"'{ticket.issue_key}': no se pudo guardar ({exc.__class__.__name__}).",
                    )
                )
                continue
            tentative.append(row)

        if errors:
            db.rollback()
            return QcTicketBulkCreateResult(created=[], errors=errors)

        db.commit()
        for row in tentative:
            db.refresh(row)
        return QcTicketBulkCreateResult(created=tentative, errors=[])

    db.commit()
    for row in rows:
        db.refresh(row)
    return QcTicketBulkCreateResult(created=rows, errors=[])


@router.get("", response_model=list[QcTicketRead])
def list_qc_tickets(
    view: QcTicketView | None = Query(default=None),
    cluster: str | None = Query(default=None),
    source: QcTicketSource | None = Query(default=None),
    is_open: bool | None = Query(default=None),
    bug_type: str | None = Query(default=None, description="RELEASE only: 'QC' or 'QA'."),
    db: Session = Depends(get_db),
) -> list[QcTicket]:
    stmt = select(QcTicket).order_by(QcTicket.created_date.desc())
    if view is not None:
        stmt = stmt.where(QcTicket.view == view)
    if cluster is not None:
        stmt = stmt.where(QcTicket.cluster == cluster)
    if source is not None:
        stmt = stmt.where(QcTicket.source == source)
    if is_open is not None:
        stmt = stmt.where(QcTicket.is_open == is_open)
    tickets = list(db.execute(stmt).scalars().all())
    if view == QcTicketView.RELEASE and bug_type in ("QC", "QA"):
        tickets = [
            t for t in tickets
            if t.source == QcTicketSource.QC_DETECTED and _matches_bug_type(t, bug_type)
        ]
    return tickets


def _matches_bug_type(ticket: QcTicket, bug_type: str) -> bool:
    """Uses the RAW issue_type field already stored verbatim from Jira's 'Tipo de Incidencia'
    column (filter #113261 exports both 'QC Bug' and 'QA Bug' issue types) -- not a new
    classification, just a case-insensitive match against data already there."""
    if not ticket.issue_type:
        return False
    normalized = ticket.issue_type.strip().upper()
    if bug_type == "QC":
        return normalized == "QC BUG"
    if bug_type == "QA":
        return normalized == "QA BUG"
    return True


@router.get("/stats", response_model=QcTicketStats)
def get_qc_ticket_stats(
    view: QcTicketView = Query(...),
    cluster: str | None = Query(default=None),
    bug_type: str | None = Query(default=None, description="RELEASE only: 'QC', 'QA', or None/'ALL' for both (default)."),
    db: Session = Depends(get_db),
) -> QcTicketStats:
    """Split by view -- Operativas and Release use different backlog rules and SWF derivations,
    so a merged view/Release total would mix incompatible things (same reasoning as the
    Dashboard's per-Release execution split earlier).

    bug_type (Release only): when 'QC' or 'QA', restricts to QC_DETECTED tickets matching that
    issue_type AND excludes LEAKED tickets entirely -- fuga is a cross-cutting concept that only
    makes sense for the combined QA+QC view (default/'ALL'), matching the product decision that
    the leak KPI/sections only appear there.
    """
    stmt = select(QcTicket).where(QcTicket.view == view)
    if cluster is not None:
        stmt = stmt.where(QcTicket.cluster == cluster)
    tickets = list(db.execute(stmt).scalars().all())

    if view == QcTicketView.RELEASE and bug_type in ("QC", "QA"):
        tickets = [
            t for t in tickets
            if t.source == QcTicketSource.QC_DETECTED and _matches_bug_type(t, bug_type)
        ]

    qc_detected = sum(1 for t in tickets if t.source == QcTicketSource.QC_DETECTED)
    leaked = sum(1 for t in tickets if t.source == QcTicketSource.LEAKED)
    leak_rate = round((leaked / (leaked + qc_detected)) * 100, 1) if (leaked + qc_detected) else 0.0

    # HTML reference: Total is always the detection filter (112929 / 113261). Fuga is a
    # separate series and must not be added into Total.
    volume = [t for t in tickets if t.source == QcTicketSource.QC_DETECTED]

    total = len(volume)
    blocker = sum(1 for t in volume if t.priority_bucket.value == "BLOCKER")
    critical = sum(1 for t in volume if t.priority_bucket.value == "CRITICAL")
    other = sum(1 for t in volume if t.priority_bucket.value == "OTHER")
    open_count = sum(1 for t in volume if t.is_open)

    genuine_leak_count = None
    if view == QcTicketView.RELEASE:
        genuine_leak_count = sum(
            1 for t in tickets if t.source == QcTicketSource.LEAKED and t.is_attributed is not True
        )

    by_cluster = Counter(t.cluster or "Sin cluster" for t in volume if t.cluster is not None)
    by_swf = Counter(t.swf or "Sin SWF" for t in volume)
    by_month = Counter(f"{t.created_date.year:04d}-{t.created_date.month:02d}" for t in volume)

    def _month_key(t: QcTicket) -> str:
        return f"{t.created_date.year:04d}-{t.created_date.month:02d}"

    def _quarter_key(t: QcTicket) -> str:
        return f"{t.created_date.year:04d}-Q{(t.created_date.month - 1) // 3 + 1}"

    # Operativas-only display grouping (already documented, not a new rule): TVOS/IOS/ADR/
    # C9085/ROKU show as one bar combining their CL+PR variants; every other device already has
    # no CL/PR split at the source, so it passes through unchanged.
    _GROUPED_BASES = ("TVOS", "IOS", "ADR", "C9085", "ROKU")

    def _display_device(raw: str) -> str:
        for base in _GROUPED_BASES:
            if raw in (f"{base}CL", f"{base}PR"):
                return base
        return raw

    by_month_priority: dict[str, dict[str, int]] = {}
    for t in volume:
        month = _month_key(t)
        bucket = by_month_priority.setdefault(month, {"BLOCKER": 0, "CRITICAL": 0, "OTHER": 0})
        bucket[t.priority_bucket.value] += 1

    open_by_priority = Counter(t.priority_bucket.value for t in volume if t.is_open)
    by_status = Counter(t.status_raw for t in volume if t.is_open)
    by_device = Counter(_display_device(t.device) for t in volume if t.device is not None)
    by_program = Counter(t.affected_program for t in volume if t.affected_program is not None)

    by_quarter = Counter(_quarter_key(t) for t in volume)

    severity_by_swf: dict[str, dict[str, int]] = {}
    for t in volume:
        if t.swf is None:
            continue
        bucket = severity_by_swf.setdefault(t.swf, {"BLOCKER": 0, "CRITICAL": 0, "OTHER": 0})
        bucket[t.priority_bucket.value] += 1

    swf_by_month: dict[str, dict[str, int]] = {}
    for t in volume:
        month = _month_key(t)
        bucket = swf_by_month.setdefault(month, {})
        key = t.swf or "Sin SWF"
        bucket[key] = bucket.get(key, 0) + 1

    leak_by_month: dict[str, dict[str, float]] = {}
    months_seen = sorted({_month_key(t) for t in tickets})
    for month in months_seen:
        month_tickets = [t for t in tickets if _month_key(t) == month]
        m_leaked = sum(1 for t in month_tickets if t.source == QcTicketSource.LEAKED)
        m_detected = sum(1 for t in month_tickets if t.source == QcTicketSource.QC_DETECTED)
        m_rate = round((m_leaked / (m_leaked + m_detected)) * 100, 1) if (m_leaked + m_detected) else 0.0
        leak_by_month[month] = {"leaked": float(m_leaked), "rate": m_rate}

    leak_by_swf: dict[str, int] = {}
    leak_by_project: dict[str, int] = {}
    if view == QcTicketView.RELEASE:
        leak_by_swf = dict(
            Counter(t.swf or "Sin SWF" for t in tickets if t.source == QcTicketSource.LEAKED)
        )
        leak_by_project = dict(
            Counter(t.project_key or "Sin proyecto" for t in tickets if t.source == QcTicketSource.LEAKED)
        )

    return QcTicketStats(
        total=total,
        blocker_count=blocker,
        critical_count=critical,
        other_count=other,
        open_count=open_count,
        qc_detected_count=qc_detected,
        leaked_count=leaked,
        leak_rate_percent=leak_rate,
        genuine_leak_count=genuine_leak_count,
        by_cluster=dict(by_cluster),
        by_swf=dict(by_swf),
        by_month=dict(sorted(by_month.items())),
        by_month_priority=dict(sorted(by_month_priority.items())),
        open_by_priority=dict(open_by_priority),
        by_status=dict(by_status),
        by_device=dict(by_device),
        by_program=dict(by_program),
        by_quarter=dict(sorted(by_quarter.items())),
        severity_by_swf=severity_by_swf,
        swf_by_month=dict(sorted(swf_by_month.items())),
        leak_by_month=leak_by_month,
        leak_by_swf=leak_by_swf,
        leak_by_project=leak_by_project,
    )


# ---------------------------------------------------------------------------
# Jira sync (experimental, unvalidated against a real Jira instance -- see
# services/jira_client.py). Reuses the exact same preview/bulk contract as the CSV path.
# ---------------------------------------------------------------------------


@router.get("/jira/fields")
def list_jira_fields() -> list[dict[str, str]]:
    """Safe first step: lists every Jira field with its real ID, so you can tell us which
    customfield_XXXXX is 'Cluster' without us guessing."""
    try:
        return jira_client.list_fields()
    except JiraNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except JiraApiError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/jira/sync-preview", response_model=QcTicketImportPreviewResponse)
def preview_jira_sync(
    filter_id: str = Query(...),
    view: QcTicketView = Query(...),
    source: QcTicketSource = Query(...),
    cluster_field_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> QcTicketImportPreviewResponse:
    """Same preview contract as the CSV path: fetches from Jira, validates, but does NOT
    persist. Approve by POSTing the returned `valid` list to /qc-tickets/bulk, same as CSV."""
    try:
        fetched = jira_client.fetch_tickets_by_filter(filter_id, view, source, cluster_field_id)
    except JiraNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except JiraApiError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    errors = [
        QcTicketImportRowError(issue_key=key, message=f"'{key}': no se pudo interpretar su fecha de creación.")
        for key in fetched.skipped_invalid
    ]

    existing_pairs = {
        (key, stored_view, stored_source)
        for key, stored_view, stored_source in db.execute(
            select(QcTicket.issue_key, QcTicket.view, QcTicket.source)
        ).all()
    }
    seen_in_batch: set[tuple[str, QcTicketView, QcTicketSource]] = set()
    valid: list[QcTicketCreate] = []
    for ticket in fetched.tickets:
        identity = (ticket.issue_key, ticket.view, ticket.source)
        if identity in existing_pairs:
            errors.append(
                QcTicketImportRowError(issue_key=ticket.issue_key, message=f"'{ticket.issue_key}' ya existe en CaseForge.")
            )
        elif identity in seen_in_batch:
            errors.append(
                QcTicketImportRowError(issue_key=ticket.issue_key, message=f"'{ticket.issue_key}' duplicado en el resultado de Jira.")
            )
        else:
            seen_in_batch.add(identity)
            valid.append(ticket)

    return QcTicketImportPreviewResponse(
        valid=valid,
        errors=errors,
        warnings=[],
        total_rows=len(fetched.tickets) + len(fetched.skipped_invalid) + fetched.skipped_excluded,
        excluded_cancelled_count=fetched.skipped_excluded,
        valid_count=len(valid),
        error_count=len(errors),
    )


def _upsert_qc_ticket(db: Session, ticket: QcTicketCreate) -> str:
    """Inserts or updates by (issue_key, view, source) so detection and leak stay independent."""
    existing = db.execute(
        select(QcTicket).where(
            QcTicket.issue_key == ticket.issue_key,
            QcTicket.view == ticket.view,
            QcTicket.source == ticket.source,
        )
    ).scalar_one_or_none()
    payload = ticket.model_dump()
    now = datetime.now(timezone.utc)
    if existing is None:
        db.add(QcTicket(**payload, imported_at=now))
        return "created"
    for field, value in payload.items():
        setattr(existing, field, value)
    existing.imported_at = now
    return "updated"


@router.post("/jira/refresh", response_model=QcTicketJiraRefreshResult)
def refresh_jira_radar(
    view: QcTicketView = Query(...),
    db: Session = Depends(get_db),
) -> QcTicketJiraRefreshResult:
    """Pulls the two saved Jira filters for this KPI view and replaces qc_tickets for each source.

    On-demand only (the refresh icon on KPIs). Tickets that left a filter are removed only when
    that filter returned at least one issue; an empty Jira response is treated as a failed fetch.
    """
    pairs = RADAR_FILTERS[view]
    try:
        jira_client.ensure_authenticated()
        cluster_field_id, program_field_id = jira_client.discover_custom_field_ids()
        fetched_all: list[JiraFetchResult] = []
        for source, filter_id in pairs:
            fetched_all.append(
                jira_client.fetch_tickets_by_filter(
                    filter_id, view, source, cluster_field_id, program_field_id
                )
            )
        empty_detected = [
            filter_id
            for fetched, (source, filter_id) in zip(fetched_all, pairs, strict=True)
            if source == QcTicketSource.QC_DETECTED and fetched.raw_issue_count == 0
        ]
        if empty_detected:
            raise jira_client.JiraApiError(
                502,
                "Jira devolvió 0 issues para filtro(s) "
                + ", ".join(f"#{fid}" for fid in empty_detected)
                + ". El KPI no se actualizó. Revisa JIRA_EMAIL / JIRA_API_TOKEN y que esa cuenta "
                "vea los mismos tickets que el filtro en Jira.",
            )
    except JiraNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except JiraApiError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    created = updated = skipped = 0
    leaked_links: dict[str, list[str]] = {}
    synced_leaked_keys: set[str] = set()
    filter_summaries: list[QcTicketJiraRefreshFilterResult] = []
    for fetched, (source, filter_id) in zip(fetched_all, pairs, strict=True):
        mapped_skip = len(fetched.skipped_invalid) + fetched.skipped_excluded
        skipped += mapped_skip
        filter_summaries.append(
            QcTicketJiraRefreshFilterResult(
                filter_id=filter_id,
                source=source.value,
                jira_count=fetched.raw_issue_count,
                mapped=len(fetched.tickets),
                skipped=mapped_skip,
            )
        )
        if source == QcTicketSource.LEAKED:
            leaked_links.update(fetched.linked_keys_by_issue)
            synced_leaked_keys.update(ticket.issue_key for ticket in fetched.tickets)
        for ticket in fetched.tickets:
            outcome = _upsert_qc_ticket(db, ticket)
            if outcome == "created":
                created += 1
            elif outcome == "updated":
                updated += 1
            else:
                skipped += 1

        kept_keys = {ticket.issue_key for ticket in fetched.tickets}
        if kept_keys:
            db.execute(
                delete(QcTicket).where(
                    QcTicket.view == view,
                    QcTicket.source == source,
                    QcTicket.issue_key.notin_(kept_keys),
                )
            )

    db.flush()

    if view == QcTicketView.RELEASE and synced_leaked_keys:
        known_qc_bug_keys = set(
            db.execute(
                select(QcTicket.issue_key).where(
                    QcTicket.view == QcTicketView.RELEASE, QcTicket.source == QcTicketSource.QC_DETECTED
                )
            ).scalars()
        )
        leaked_rows = list(
            db.execute(
                select(QcTicket).where(
                    QcTicket.view == QcTicketView.RELEASE,
                    QcTicket.source == QcTicketSource.LEAKED,
                    QcTicket.issue_key.in_(synced_leaked_keys),
                )
            ).scalars()
        )
        for row in leaked_rows:
            linked = leaked_links.get(row.issue_key, [])
            row.is_attributed = bool(set(linked) & known_qc_bug_keys) if known_qc_bug_keys else None

    db.commit()
    return QcTicketJiraRefreshResult(
        created=created,
        updated=updated,
        skipped=skipped,
        filter_ids=[filter_id for _source, filter_id in pairs],
        filters=filter_summaries,
    )
