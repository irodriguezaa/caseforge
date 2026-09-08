"""Release CRUD endpoints.

Apps, Operativas and Release BE can be hard-deleted (including dependent rows).
A Release that is origin of Revalidaciones cannot be deleted.
"""

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import AuthUser, Role
from app.db import get_db
from app.deps.auth import get_current_user, require_jefe
from app.models.be_release import BeRelease
from app.models.deliverable import Deliverable
from app.models.epc import Epc
from app.models.operativa_release import OperativaRelease
from app.models.release import Release, ReleaseStatus, ReleaseType
from app.models.release_analysis import ReleaseAnalysis
from app.models.test_case import TestCase
from app.routers.common import get_release_or_404
from app.schemas.case_generation import GenerateCasesResponse
from app.schemas.coverage_matrix import CoverageMatrixResponse
from app.schemas.matrix_preview import MatrixPreviewResponse
from app.schemas.publication import PublicationRecordRead, PublishCasesResponse
from app.schemas.release import (
    ReleaseAnalysisRead,
    ReleaseCreate,
    ReleaseNoteAnalyzeResponse,
    ReleaseRead,
    ReleaseUpdate,
    ReleaseWithCounts,
)
from app.services.ai_case_engine import _tickets_by_section, generate_release_app_candidates
from app.services.revalidation_engine import (
    candidates_from_incremental_plan,
    plan_incremental_generation,
    stamp_incremental_traceability,
)
from app.services.case_persistence import (
    delete_engine_cases,
    engine_cases_for_release,
    persist_candidates,
    summarize_cases,
)
from app.services.operativa_engine import ENGINE_VERSION as OPERATIVA_ENGINE, generate_operativa_from_matrix
from app.services.operativa_engine.coverage_matrix import build_coverage_matrix
from app.services.operativa_engine.matrix_expand import expand_matrix_preview
from app.services.test_case_export import build_test_cases_workbook, load_release_cases
from app.services.zephyr_publish import fingerprint, load_engine_cases, publish_cases
from app.services.release_note_analyzer import (
    RuleBasedPdfAnalyzer,
    calculate_business_days,
)
from app.services.rn_storage import persist_release_note_pdf, read_release_note_pdf, delete_release_note_pdf

router = APIRouter(prefix="/api/v1/releases", tags=["releases"])

# Allowed forward transitions. DRAFT can also be removed entirely via DELETE (see below).
_VALID_TRANSITIONS: dict[ReleaseStatus, set[ReleaseStatus]] = {
    ReleaseStatus.DRAFT: {ReleaseStatus.IN_PROGRESS, ReleaseStatus.CANCELLED},
    ReleaseStatus.IN_PROGRESS: {ReleaseStatus.COMPLETED, ReleaseStatus.CANCELLED},
    ReleaseStatus.COMPLETED: set(),
    ReleaseStatus.CANCELLED: set(),
}

# Entregable / Tipo de Release / Release origen can only change while still DRAFT (product
# decision) -- same posture as the existing DRAFT-only hard-delete rule below.
_LINEAGE_FIELDS = {"deliverable_name", "release_type", "parent_release_id"}


def _test_case_coverage_snapshot(row: TestCase) -> dict:
    return {
        "id": row.id,
        "release_id": row.release_id,
        "test_case_id": row.test_case_id,
        "test_case_name": row.test_case_name,
        "description": row.description or "",
        "technical_story": row.technical_story or "",
        "technical_epic": row.technical_epic or "",
        "evidence": row.evidence or "",
        "justification": row.justification or "",
    }


def _deliverable_baseline_coverage(
    db: Session, release: Release
) -> tuple[list[dict], dict[str, str], dict[str, str], dict[str, str]]:
    """All Test Cases and prior RN cells from Releases of the same Entregable.

    Coverage is decided from Test Case identity fields, not from RN appearance.
    QA/QC and NCO cells are kept only to detect an explicit delta on an already-covered key.
    """
    if release.deliverable_id is None:
        return [], {}, {}, {}
    siblings = list(
        db.execute(
            select(Release)
            .where(Release.deliverable_id == release.deliverable_id, Release.id != release.id)
            .order_by(Release.id.asc())
        )
        .scalars()
        .all()
    )
    if not siblings:
        return [], {}, {}, {}
    sibling_ids = [row.id for row in siblings]
    cases = list(db.execute(select(TestCase).where(TestCase.release_id.in_(sibling_ids))).scalars().all())
    snapshot = [_test_case_coverage_snapshot(row) for row in cases]
    prior_functionality: dict[str, str] = {}
    prior_qa_qc: dict[str, str] = {}
    prior_nco: dict[str, str] = {}
    for sibling in siblings:
        analysis = (
            db.execute(
                select(ReleaseAnalysis)
                .where(ReleaseAnalysis.release_id == sibling.id)
                .order_by(ReleaseAnalysis.created_at.desc())
            )
            .scalars()
            .first()
        )
        if analysis is None:
            continue
        prior_pdf = read_release_note_pdf(analysis.pdf_file_path)
        if not prior_pdf:
            continue
        buckets = _tickets_by_section(prior_pdf)
        for ticket_id, cell_text in buckets.get("functionality", []):
            prior_functionality[ticket_id.upper()] = cell_text
        for ticket_id, cell_text in buckets.get("qa_qc", []):
            prior_qa_qc[ticket_id.upper()] = cell_text
        for ticket_id, cell_text in buckets.get("nco", []):
            prior_nco[ticket_id.upper()] = cell_text
    return snapshot, prior_functionality, prior_qa_qc, prior_nco


def to_release_read(release: Release) -> ReleaseRead:
    """Populate deliverable_name and BE fields that are not columns on Release."""
    be = release.be_release
    parent = release.parent
    read = ReleaseRead.model_validate(release)
    return read.model_copy(
        update={
            "deliverable_name": release.deliverable.name if release.deliverable else None,
            "parent_release_name": f"{parent.name} v{parent.version}" if parent else None,
            "swf": be.swf if be else None,
            "regresivo_scope": be.regresivo_scope if be else None,
            "affected_component": be.affected_component if be else None,
        }
    )


def _resolve_deliverable(name: str | None, db: Session) -> Deliverable | None:
    """Get-or-create by case-insensitive name match. No picker in this phase -- a typo creates
    a new Deliverable rather than silently merging, which is an accepted tradeoff for now."""
    if not name or not name.strip():
        return None
    normalized = name.strip()
    existing = db.execute(
        select(Deliverable).where(func.lower(Deliverable.name) == normalized.lower())
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    deliverable = Deliverable(name=normalized)
    db.add(deliverable)
    try:
        db.flush()
    except IntegrityError:
        # Rare race: another request created the exact same name between our lookup and this
        # flush. The UNIQUE constraint caught it -- fall back to reusing that row instead of
        # surfacing a 500 for something that isn't really an error from the caller's view.
        db.rollback()
        return db.execute(
            select(Deliverable).where(func.lower(Deliverable.name) == normalized.lower())
        ).scalar_one()
    return deliverable


def _would_create_cycle(release_id: int, proposed_parent_id: int | None, db: Session) -> bool:
    """Walks up the proposed parent's own chain -- if it ever reaches release_id, setting
    proposed_parent_id as release_id's parent would create a cycle."""
    if proposed_parent_id is None:
        return False
    current_id: int | None = proposed_parent_id
    visited: set[int] = set()
    while current_id is not None:
        if current_id == release_id:
            return True
        if current_id in visited:
            break  # guards against an already-corrupt chain elsewhere; never infinite-loops
        visited.add(current_id)
        parent = db.get(Release, current_id)
        current_id = parent.parent_release_id if parent else None
    return False


def _validate_origin_parent(
    parent_release_id: int | None,
    deliverable_id: int | None,
    db: Session,
    self_release_id: int | None,
    required_detail: str,
) -> None:
    if parent_release_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=required_detail)
    if self_release_id is not None and parent_release_id == self_release_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Una Release no puede ser su propia Release origen.",
        )
    parent = db.get(Release, parent_release_id)
    if parent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Release origen no encontrada.")
    if deliverable_id is None or parent.deliverable_id != deliverable_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="La Release origen debe pertenecer al mismo Entregable.",
        )
    if self_release_id is not None and _would_create_cycle(self_release_id, parent_release_id, db):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Esa Release origen generaría un ciclo en la cadena de versiones del Entregable.",
        )


def _validate_lineage(
    release_type: ReleaseType | None,
    parent_release_id: int | None,
    deliverable_id: int | None,
    db: Session,
    self_release_id: int | None = None,
) -> None:
    if release_type == ReleaseType.REVALIDACION:
        _validate_origin_parent(
            parent_release_id,
            deliverable_id,
            db,
            self_release_id,
            "Una Release de tipo Revalidación requiere una Release origen.",
        )
    elif release_type == ReleaseType.NUEVO and parent_release_id is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Una Release de tipo Nuevo no debe tener Release origen.",
        )


@router.post("/analyze-rn", response_model=ReleaseNoteAnalyzeResponse)
async def analyze_release_note(
    file: UploadFile = File(...),
) -> ReleaseNoteAnalyzeResponse:
    """Parses a Release Note PDF deterministically, extracting metadata and section counts.

    Does not hallucinate or predict test cases (strictly adheres to Phase 1 separation of
    concerns prior to .md QC engine integration).
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Solo se aceptan archivos PDF para el análisis de Release Note.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="El archivo PDF está vacío.")

    analyzer = RuleBasedPdfAnalyzer()
    extracted = analyzer.analyze(file.filename, content)
    stored = persist_release_note_pdf(file.filename, content)
    if stored:
        extracted = extracted.model_copy(update={"pdf_file_path": stored})

    return ReleaseNoteAnalyzeResponse(
        analysis=extracted,
        calculated_business_days=0,
    )


@router.get("", response_model=list[ReleaseWithCounts])
def list_releases(
    status_filter: ReleaseStatus | None = Query(default=None, alias="status"),
    platform: str | None = Query(default=None),
    include_be: bool = Query(default=False),
    include_operativa: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[ReleaseWithCounts]:
    stmt = (
        select(Release, func.count(TestCase.id))
        .outerjoin(TestCase, TestCase.release_id == Release.id)
        .group_by(Release.id)
        .order_by(Release.created_at.desc())
    )
    if not include_be:
        stmt = stmt.where(Release.be_release_id.is_(None))
    if not include_operativa:
        stmt = stmt.where(Release.operativa_release_id.is_(None))
    if status_filter is not None:
        stmt = stmt.where(Release.status == status_filter)
    if platform is not None:
        stmt = stmt.where(Release.platform == platform)

    rows = db.execute(stmt).all()
    results: list[ReleaseWithCounts] = []
    for release, count in rows:
        latest_analysis = (
            db.execute(
                select(ReleaseAnalysis)
                .where(ReleaseAnalysis.release_id == release.id)
                .order_by(ReleaseAnalysis.created_at.desc())
            )
            .scalars()
            .first()
        )
        release_read = to_release_read(release).model_dump()
        results.append(
            ReleaseWithCounts(
                **release_read,
                test_case_count=count,
                latest_analysis=(
                    ReleaseAnalysisRead.model_validate(latest_analysis)
                    if latest_analysis
                    else None
                ),
            )
        )
    return results


@router.post("", response_model=ReleaseRead, status_code=status.HTTP_201_CREATED)
def create_release(payload: ReleaseCreate, db: Session = Depends(get_db)) -> ReleaseRead:
    release_dict = payload.model_dump(exclude={"analysis_data", "deliverable_name"})
    if release_dict.get("execution_days") is None and release_dict.get("start_date") and release_dict.get("end_date"):
        release_dict["execution_days"] = calculate_business_days(
            release_dict["start_date"], release_dict["end_date"]
        )

    deliverable = _resolve_deliverable(payload.deliverable_name, db)
    release_dict["deliverable_id"] = deliverable.id if deliverable else None
    _validate_lineage(payload.release_type, payload.parent_release_id, release_dict["deliverable_id"], db)

    release = Release(**release_dict)
    db.add(release)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A release with this name, version and platform already exists.",
        ) from exc

    if payload.analysis_data is not None:
        analysis_dict = payload.analysis_data.model_dump()
        analysis_row = ReleaseAnalysis(release_id=release.id, **analysis_dict)
        db.add(analysis_row)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A release with this name, version and platform already exists.",
        ) from exc

    db.refresh(release)
    return to_release_read(release)


@router.get("/{release_id}", response_model=ReleaseRead)
def get_release(release_id: int, db: Session = Depends(get_db)) -> ReleaseRead:
    release = get_release_or_404(release_id, db)
    return to_release_read(release)


@router.patch("/{release_id}", response_model=ReleaseRead)
def update_release(
    release_id: int,
    payload: ReleaseUpdate,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(get_current_user),
) -> ReleaseRead:
    release = get_release_or_404(release_id, db)
    updates = payload.model_dump(exclude_unset=True)

    new_status = updates.get("status")
    if new_status is not None and new_status != release.status and user.role not in {Role.JEFE, Role.LIDER}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No tienes permiso para cambiar el estado del release.")

    if _LINEAGE_FIELDS & updates.keys() and release.status != ReleaseStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Entregable, Tipo de Release y Release origen solo pueden editarse mientras la Release está en DRAFT.",
        )

    if new_status is not None and new_status != release.status:
        allowed = _VALID_TRANSITIONS.get(release.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot transition release from {release.status.value} "
                    f"to {new_status.value}."
                ),
            )

    original_keys = set(updates.keys())
    if "deliverable_name" in updates:
        deliverable = _resolve_deliverable(updates.pop("deliverable_name"), db)
        updates["deliverable_id"] = deliverable.id if deliverable else None

    if _LINEAGE_FIELDS & original_keys:
        effective_type = updates.get("release_type", release.release_type)
        effective_parent = updates.get("parent_release_id", release.parent_release_id)
        effective_deliverable_id = updates.get("deliverable_id", release.deliverable_id)
        _validate_lineage(effective_type, effective_parent, effective_deliverable_id, db, self_release_id=release_id)

    for field, value in updates.items():
        setattr(release, field, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A release with this name, version and platform already exists.",
        ) from exc
    db.refresh(release)
    return to_release_read(release)


def hard_delete_release_and_notes(db: Session, release: Release) -> None:
    has_children = db.execute(
        select(Release.id).where(Release.parent_release_id == release.id)
    ).first()
    if has_children:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="No se puede eliminar una Release que es origen de otras Releases (Revalidaciones).",
        )
    pdf_paths = [row.pdf_file_path for row in release.analyses if row.pdf_file_path]
    operativa = release.operativa_release
    operativa_id = operativa.id if operativa is not None else None
    if operativa and operativa.pdf_file_path:
        pdf_paths.append(operativa.pdf_file_path)
    be = release.be_release
    be_id = be.id if be is not None else None
    release.operativa_release_id = None
    release.be_release_id = None
    db.flush()
    db.delete(release)
    db.flush()
    if operativa_id is not None:
        leftover = db.get(OperativaRelease, operativa_id)
        if leftover is not None:
            db.delete(leftover)
    if be_id is not None:
        leftover_be = db.get(BeRelease, be_id)
        if leftover_be is not None:
            db.delete(leftover_be)
    db.commit()
    for path in pdf_paths:
        delete_release_note_pdf(path)


@router.delete("/{release_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_release(
    release_id: int,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_jefe),
) -> None:
    hard_delete_release_and_notes(db, get_release_or_404(release_id, db))


@router.get("/{release_id}/analysis", response_model=ReleaseAnalysisRead)
def get_release_analysis(release_id: int, db: Session = Depends(get_db)) -> ReleaseAnalysis:
    get_release_or_404(release_id, db)
    analysis = (
        db.execute(
            select(ReleaseAnalysis)
            .where(ReleaseAnalysis.release_id == release_id)
            .order_by(ReleaseAnalysis.created_at.desc())
        )
        .scalars()
        .first()
    )
    if not analysis:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="No se encontró ningún análisis de Release Note para esta release.",
        )
    return analysis


def _already_generated_response(release: Release, summary: dict) -> GenerateCasesResponse:
    return GenerateCasesResponse(
        status="ALREADY_GENERATED",
        message=(
            f"Esta Release ya tiene {summary['test_case_count']} Test Case(s) generados. "
            "No se duplicaron. Usa regenerar para reemplazar únicamente los casos del motor."
        ),
        release_id=release.id,
        release_name=release.name,
        validation_type=release.validation_type,
        has_analysis=True,
        engine="already-persisted",
        candidates=[],
        persisted=True,
        already_generated=True,
        test_case_count=summary["test_case_count"],
        estimation_hours=summary["estimation_hours"],
        estimation_days=summary["estimation_days"],
    )


def _generate_operativa_cases(release: Release, regenerate: bool, db: Session) -> GenerateCasesResponse:
    existing_engine = engine_cases_for_release(db, release.id)
    if existing_engine and not regenerate:
        return _already_generated_response(release, summarize_cases(existing_engine))

    epcs = list(
        db.scalars(
            select(Epc).where(Epc.release_id == release.id).order_by(Epc.id)
        ).all()
    )
    if not epcs:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="No hay BRF/EPC congelados en este Release. QC debe incluir EPCs al crear el Release.",
        )
    operativa = db.get(OperativaRelease, release.operativa_release_id)
    pdf_bytes = read_release_note_pdf(operativa.pdf_file_path if operativa else None)
    result = generate_operativa_from_matrix(
        release_id=release.id,
        release_name=release.name,
        epcs=epcs,
        pdf_bytes=pdf_bytes,
    )
    if regenerate:
        delete_engine_cases(db, release.id)
    persisted_rows = []
    if result.candidates:
        persisted_rows = persist_candidates(
            db, release.id, release.platform or "Operativa", result.candidates
        )
    db.commit()
    for row in persisted_rows:
        db.refresh(row)
    summary = summarize_cases(persisted_rows)
    device_review = result.device_review_brfs or []
    dup_count = result.duplicate_groups
    n_brfs = result.brfs_analyzed
    n_cases = summary["test_case_count"]
    lines = [f"{n_brfs} BRFs analizados · {n_cases} Test Cases generados"]
    if device_review:
        lines.append(f"⚠️ {len(device_review)} BRFs requieren revisión de dispositivos")
    if dup_count:
        noun = "posible duplicado detectado" if dup_count == 1 else "posibles duplicados/solapamientos detectados"
        lines.append(f"⚠️ {dup_count} {noun}")
    lines.append("Ver detalles del análisis")
    return GenerateCasesResponse(
        status="PROPOSED",
        message="\n".join(lines),
        release_id=release.id,
        release_name=release.name,
        validation_type=release.validation_type,
        has_analysis=True,
        engine=OPERATIVA_ENGINE,
        candidates=result.candidates,
        persisted=bool(persisted_rows),
        already_generated=False,
        test_case_count=n_cases,
        estimation_hours=summary["estimation_hours"],
        estimation_days=summary["estimation_days"],
        analysis_details=result.skipped,
        brfs_analyzed=n_brfs,
        device_review_count=len(device_review),
        possible_duplicate_count=dup_count,
    )


@router.get("/{release_id}/coverage-matrix", response_model=CoverageMatrixResponse)
def get_operativa_coverage_matrix(
    release_id: int,
    brf_key: str | None = Query(default=None, description="Filtrar filas a un BRF (p. ej. BRF-17442)"),
    db: Session = Depends(get_db),
) -> CoverageMatrixResponse:
    """Matriz intermedia de cobertura funcional — antes de expansión por dispositivo / TCs."""
    release = get_release_or_404(release_id, db)
    if release.operativa_release_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="La matriz de cobertura aplica solo a Releases Operativas.",
        )
    epcs = list(
        db.scalars(
            select(Epc).where(Epc.release_id == release.id).order_by(Epc.id)
        ).all()
    )
    if not epcs:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="No hay BRF/EPC congelados en este Release.",
        )
    if brf_key:
        normalized = brf_key.strip().upper()
        epcs = [epc for epc in epcs if (epc.brf_key or "").upper() == normalized]
        if not epcs:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=f"No hay EPC congelados para {normalized} en este Release.",
            )
    result = build_coverage_matrix(
        release_id=release.id,
        release_name=release.name,
        epcs=epcs,
    )
    if brf_key:
        normalized = brf_key.strip().upper()
        result.rows = [row for row in result.rows if row.brf_key.upper() == normalized]
        result.hn_coverage = [item for item in result.hn_coverage if item.brf_key.upper() == normalized]
        result.row_count = len(result.rows)
        result.brfs_analyzed = 1
    return result


@router.get("/{release_id}/coverage-matrix/preview", response_model=MatrixPreviewResponse)
def get_operativa_matrix_preview(
    release_id: int,
    brf_key: str | None = Query(default=None, description="Filtrar a un BRF (p. ej. BRF-17442)"),
    db: Session = Depends(get_db),
) -> MatrixPreviewResponse:
    """Preview Matriz → dispositivo. No persiste TCs ni escribe Jira/Zephyr."""
    matrix = get_operativa_coverage_matrix(release_id, brf_key=brf_key, db=db)
    return expand_matrix_preview(matrix)


@router.post("/{release_id}/generate-cases", response_model=GenerateCasesResponse)
def generate_cases_from_rn(
    release_id: int,
    regenerate: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> GenerateCasesResponse:
    """Generate functional Test Cases: Apps from RN/Jira, Operativas from QC-selected BRFs."""
    release = get_release_or_404(release_id, db)
    if release.be_release_id is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="La generación de casos desde Matriz QC de Release BE se conectará en una fase posterior.",
        )
    if release.operativa_release_id is not None:
        return _generate_operativa_cases(release, regenerate, db)
    analysis = (
        db.execute(
            select(ReleaseAnalysis)
            .where(ReleaseAnalysis.release_id == release_id)
            .order_by(ReleaseAnalysis.created_at.desc())
        )
        .scalars()
        .first()
    )
    if analysis is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="No hay un RN asociado a esta Release. Analiza y crea la Release desde el PDF primero.",
        )

    existing_engine = engine_cases_for_release(db, release.id)
    if existing_engine and not regenerate:
        summary = summarize_cases(existing_engine)
        return GenerateCasesResponse(
            status="ALREADY_GENERATED",
            message=(
                f"Esta Release ya tiene {summary['test_case_count']} Test Case(s) generados. "
                "No se duplicaron. Usa regenerar para reemplazar únicamente los casos del motor."
            ),
            release_id=release.id,
            release_name=release.name,
            validation_type=release.validation_type,
            has_analysis=True,
            engine="already-persisted",
            candidates=[],
            persisted=True,
            already_generated=True,
            test_case_count=summary["test_case_count"],
            estimation_hours=summary["estimation_hours"],
            estimation_days=summary["estimation_days"],
        )

    pdf_bytes = read_release_note_pdf(analysis.pdf_file_path)
    parent = release.parent
    declared_origin_id = release.parent_release_id
    declared_origin_name = f"{parent.name} v{parent.version}" if parent else None
    context = {
        "name": release.name,
        "version": release.version,
        "platform": release.platform,
        "cluster": release.cluster,
        "description": release.description,
        "validation_type": release.validation_type,
        "jira_issue_filter": release.jira_issue_filter,
        "release_type": release.release_type.value if release.release_type else None,
        "parent_release_id": declared_origin_id,
        "parent_release_name": declared_origin_name,
        "analysis": {
            "pdf_filename": analysis.pdf_filename,
            "detected_name": analysis.detected_name,
            "detected_version": analysis.detected_version,
            "detected_platform": analysis.detected_platform,
            "detected_description": analysis.detected_description,
            "features_count": analysis.features_count,
            "observations": analysis.observations,
        },
    }
    baseline_cases, prior_functionality_cells, prior_qa_qc_cells, prior_nco_cells = (
        _deliverable_baseline_coverage(db, release)
    )
    existing_reference = [
        {
            "test_case_id": row["test_case_id"],
            "test_case_name": row["test_case_name"],
            "description": row["description"],
        }
        for row in baseline_cases
    ]
    if not baseline_cases:
        proposal = generate_release_app_candidates(
            release_id=release.id,
            release_name=release.name,
            validation_type=release.validation_type,
            analysis_present=True,
            rn_filename=analysis.pdf_filename,
            pdf_bytes=pdf_bytes,
            release_context=context,
            existing_cases=existing_reference,
        )
    else:
        tickets = _tickets_by_section(pdf_bytes) if pdf_bytes else {}
        plan = plan_incremental_generation(
            tickets,
            baseline_cases,
            prior_functionality_cells,
            prior_qa_qc_cells=prior_qa_qc_cells,
            prior_nco_cells=prior_nco_cells,
        )
        new_candidates = []
        engine_name = "incremental-delta"
        if plan.new_functionality:
            scoped_tickets = {
                "functionality": plan.new_functionality,
                "nco": [],
                "tri": [],
                "qa_qc": [],
            }
            allowed = {tid.upper() for tid, _ in plan.new_functionality}
            scoped = generate_release_app_candidates(
                release_id=release.id,
                release_name=release.name,
                validation_type=release.validation_type,
                analysis_present=True,
                rn_filename=analysis.pdf_filename,
                pdf_bytes=pdf_bytes,
                release_context=context,
                existing_cases=existing_reference,
                tickets=scoped_tickets,
                restrict_to_functionality_keys=allowed,
            )
            new_candidates = [
                stamp_incremental_traceability(
                    candidate,
                    origin_release_id=declared_origin_id,
                    origin_release_name=declared_origin_name,
                    baseline_cases=baseline_cases,
                )
                for candidate in scoped.candidates
            ]
            engine_name = scoped.engine
        delta_candidates = candidates_from_incremental_plan(
            plan,
            rn_filename=analysis.pdf_filename or "",
            origin_release_id=declared_origin_id,
            origin_release_name=declared_origin_name,
            baseline_cases=baseline_cases,
        )
        merged = new_candidates + delta_candidates
        if new_candidates and delta_candidates:
            engine_name = f"{engine_name}+incremental-delta"
        elif not new_candidates:
            engine_name = "incremental-delta"
        proposal = GenerateCasesResponse(
            status="PROPOSED" if merged else "EMPTY",
            message=(
                f"Generación incremental respecto del histórico del Entregable: "
                f"{len(merged)} caso(s) nuevos o afectados. "
                f"No se copiaron los {len(baseline_cases)} Test Case(s) previos."
            ),
            release_id=release.id,
            release_name=release.name,
            validation_type=release.validation_type,
            has_analysis=True,
            engine=engine_name,
            candidates=merged,
            persisted=False,
            analysis_details=plan.analysis_details,
        )
    if regenerate:
        delete_engine_cases(db, release.id)

    persisted_rows = []
    if proposal.candidates:
        persisted_rows = persist_candidates(
            db, release.id, release.platform or "General", proposal.candidates
        )
    db.commit()
    for row in persisted_rows:
        db.refresh(row)
    summary = summarize_cases(persisted_rows)
    if not proposal.candidates:
        proposal.message = (
            proposal.message
            + " No se persistió ningún Test Case porque el motor no materializó candidatos funcionales."
        )
        proposal.persisted = False
    else:
        proposal.message = (
            f"Se persistieron {summary['test_case_count']} Test Case(s) en la Release. "
            f"Estimación IA: {summary['estimation_hours']} h (≈ {summary['estimation_days']} días QC)."
        )
        proposal.persisted = True
    proposal.already_generated = False
    proposal.test_case_count = summary["test_case_count"]
    proposal.estimation_hours = summary["estimation_hours"]
    proposal.estimation_days = summary["estimation_days"]
    return proposal


@router.get("/{release_id}/test-cases/export")
def export_release_test_cases(release_id: int, db: Session = Depends(get_db)) -> Response:
    """Excel with QC sheet + Zephyr-flat sheet from persisted Test Cases."""
    release = get_release_or_404(release_id, db)
    cases = load_release_cases(db, release.id)
    try:
        payload = build_test_cases_workbook(cases)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"No se pudo generar el Excel: {exc}",
        ) from exc
    raw_name = f"CaseForge_{release.name}_TestCases.xlsx".replace(" ", "_")
    ascii_name = "CaseForge_TestCases.xlsx"
    disposition = (
        f"attachment; filename=\"{ascii_name}\"; "
        f"filename*=UTF-8''{quote(raw_name)}"
    )
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(len(payload)),
        },
    )


@router.post("/{release_id}/publish-qco", response_model=PublishCasesResponse)
def publish_operativa_cases_to_qco(
    release_id: int,
    db: Session = Depends(get_db),
) -> PublishCasesResponse:
    """QCO_ZEPHYR_PUBLISH: parked. UI hidden. Keep endpoint for Zephyr-format phase.

    Publish persisted engine TCs of an Operativa Release to Jira QCO Test.
    Idempotent: already-created remote keys are skipped. Does not mutate coverage rows.
    """
    release = get_release_or_404(release_id, db)
    if release.operativa_release_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="La publicación a QCO está disponible para Releases de Operativas.",
        )
    cases = load_engine_cases(db, release.id)
    if not cases:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="No hay Test Cases del motor para publicar. Genera casos primero.",
        )
    before = {case.id: fingerprint(case) for case in cases}
    records = publish_cases(db, cases)
    db.expire_all()
    after_cases = load_engine_cases(db, release.id)
    after = {case.id: fingerprint(case) for case in after_cases}
    created = sum(1 for row in records if row.resultado == "created")
    errors = sum(1 for row in records if row.resultado == "error")
    duplicates = sum(1 for row in records if row.resultado == "duplicate")
    unmodified = all(after.get(key) == value for key, value in before.items())
    return PublishCasesResponse(
        status="PUBLISHED" if not errors else "PARTIAL",
        message=(
            f"{len(records)} enviados · {created} creados · {duplicates} duplicados · {errors} errores. "
            "Los Test Cases de QC Pulse no se modifican."
        ),
        release_id=release.id,
        sent=len(records),
        created=created,
        errors=errors,
        duplicates=duplicates,
        rejected=errors,
        caseforge_unmodified=unmodified,
        records=[
            PublicationRecordRead(
                caseforge_id=row.caseforge_id,
                zephyr_id=row.zephyr_id,
                brf=row.brf,
                hn=row.hn,
                device_channel=row.device_channel,
                name=row.name,
                steps=row.steps,
                status=row.status,
                resultado=row.resultado,
                detail=row.detail,
            )
            for row in records
        ],
    )
