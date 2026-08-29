"""QcTicket endpoints: independent defect-radar import pipeline and KPIs aggregation.

Same Import -> Validate -> Preview -> Approve -> Persist pattern already used for Test Cases,
kept as a fully separate pipeline since QcTicket has no relationship to Release/TestCase/Defect.
"""

import logging
from collections import Counter

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.qc_ticket import QcTicket, QcTicketSource, QcTicketView
from app.schemas.qc_tickets import (
    QcRadarConfigResponse,
    QcRadarFilterItem,
    QcRadarViewConfig,
    QcTicketBulkCreateError,
    QcTicketBulkCreateResult,
    QcTicketCreate,
    QcTicketImportPreviewResponse,
    QcTicketImportRowError,
    QcTicketRead,
    QcTicketStats,
)
from app.services import jira_client
from app.services.jira_client import JiraApiError, JiraNotConfiguredError
from app.services.qc_ticket_imports import QcTicketImportStructureError, parse_file, validate_rows

router = APIRouter(prefix="/api/v1/qc-tickets", tags=["qc-tickets"])
logger = logging.getLogger(__name__)

QC_RADAR_CONFIG = QcRadarConfigResponse(
    OPERATIVAS=QcRadarViewConfig(
        detected=QcRadarFilterItem(
            filter_id="112929",
            label="Detección QC",
            description="Bugs detectados por QC en ventanas operativas",
            tag="#112929",
        ),
        leaked=QcRadarFilterItem(
            filter_id="113062",
            label="Fuga",
            description="Fuga de defectos en operativas",
            tag="#113062",
        ),
    ),
    RELEASE=QcRadarViewConfig(
        detected=QcRadarFilterItem(
            filter_id="113261",
            label="QC/QA Bugs",
            description="Bugs detectados por QC/QA en releases",
            tag="#113261",
        ),
        leaked=QcRadarFilterItem(
            filter_id="113784",
            label="Fuga",
            description="Fuga de defectos en releases hacia producción",
            tag="#113784",
        ),
    ),
)


@router.get("/filters", response_model=QcRadarConfigResponse)
@router.get("/radar-config", response_model=QcRadarConfigResponse)
def get_qc_radar_config() -> QcRadarConfigResponse:
    """Returns the canonical Jira filter configuration for QC Radar views (Single Source of Truth)."""
    return QC_RADAR_CONFIG


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

    existing_keys = set(db.execute(select(QcTicket.issue_key)).scalars())
    still_valid: list[QcTicketCreate] = []
    for ticket in valid:
        if ticket.issue_key in existing_keys:
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
    return list(db.execute(stmt).scalars().all())


@router.get("/stats", response_model=QcTicketStats)
def get_qc_ticket_stats(
    view: QcTicketView = Query(...),
    cluster: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> QcTicketStats:
    """Split by view -- Operativas and Release use different backlog rules and SWF derivations,
    so a merged view/Release total would mix incompatible things (same reasoning as the
    Dashboard's per-Release execution split earlier)."""
    stmt = select(QcTicket).where(QcTicket.view == view)
    if cluster is not None:
        stmt = stmt.where(QcTicket.cluster == cluster)
    tickets = list(db.execute(stmt).scalars().all())

    total = len(tickets)
    blocker = sum(1 for t in tickets if t.priority_bucket.value == "BLOCKER")
    critical = sum(1 for t in tickets if t.priority_bucket.value == "CRITICAL")
    other = sum(1 for t in tickets if t.priority_bucket.value == "OTHER")
    open_count = sum(1 for t in tickets if t.is_open)
    qc_detected = sum(1 for t in tickets if t.source == QcTicketSource.QC_DETECTED)
    leaked = sum(1 for t in tickets if t.source == QcTicketSource.LEAKED)
    leak_rate = round((leaked / (leaked + qc_detected)) * 100, 1) if (leaked + qc_detected) else 0.0

    genuine_leak_count = None
    if view == QcTicketView.RELEASE:
        genuine_leak_count = sum(
            1 for t in tickets if t.source == QcTicketSource.LEAKED and t.is_attributed is not True
        )

    by_cluster = Counter(t.cluster or "Sin cluster" for t in tickets if t.cluster is not None)
    by_swf = Counter(t.swf or "Sin SWF" for t in tickets)
    by_month = Counter(f"{t.created_date.year:04d}-{t.created_date.month:02d}" for t in tickets)

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
        tickets, skipped = jira_client.fetch_tickets_by_filter(filter_id, view, source, cluster_field_id)
    except JiraNotConfiguredError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except JiraApiError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    errors = [
        QcTicketImportRowError(issue_key=key, message=f"'{key}': no se pudo interpretar su fecha de creación.")
        for key in skipped
    ]

    existing_keys = set(db.execute(select(QcTicket.issue_key)).scalars())
    seen_in_batch: set[str] = set()
    valid: list[QcTicketCreate] = []
    for ticket in tickets:
        if ticket.issue_key in existing_keys:
            errors.append(
                QcTicketImportRowError(issue_key=ticket.issue_key, message=f"'{ticket.issue_key}' ya existe en CaseForge.")
            )
        elif ticket.issue_key in seen_in_batch:
            errors.append(
                QcTicketImportRowError(issue_key=ticket.issue_key, message=f"'{ticket.issue_key}' duplicado en el resultado de Jira.")
            )
        else:
            seen_in_batch.add(ticket.issue_key)
            valid.append(ticket)

    return QcTicketImportPreviewResponse(
        valid=valid,
        errors=errors,
        warnings=[],
        total_rows=len(tickets) + len(skipped),
        valid_count=len(valid),
        error_count=len(errors),
    )
