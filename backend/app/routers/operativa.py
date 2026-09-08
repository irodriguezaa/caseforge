"""Operativa router -- RN Operativo 5-step pipeline plus QC Release creation."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth import AuthUser
from app.db import get_db
from app.deps.auth import require_jefe
from app.models.epc import Epc
from app.models.operativa_release import OperativaRelease
from app.models.release import Release
from app.routers.releases import _resolve_deliverable, hard_delete_release_and_notes
from app.schemas.operativa import (
    EpcRead,
    EpcUpdate,
    OperativaAnalysisResult,
    OperativaReleaseRead,
    OperativaReleaseUpdate,
)
from app.schemas.release import ReleaseRead
from app.services.operativa_analyzer import analyze_operativa_rn, extract_rn_header
from app.services.release_note_analyzer import calculate_business_days
from app.services.rn_storage import delete_release_note_pdf, persist_release_note_pdf

router = APIRouter(prefix="/api/v1/operativa", tags=["operativa"])

OPERATIVA_PLATFORM = "Operativa"
OPERATIVA_VERSION = "OPE"


@router.post("/analyze-rn", response_model=OperativaAnalysisResult, status_code=status.HTTP_201_CREATED)
async def analyze_operativa_release_note(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> OperativaAnalysisResult:
    """Paso 1: parse the RN Operativo PDF and persist one OperativaRelease plus one Epc per
    detected BRF/EPC. Header fields (Paso 2) come from page-1 evidence only -- never from the
    filename. include_in_qc is initialized from qc_suggestion (True only for SUGERIDO_INCLUIR)
    but is a normal editable column from the moment it's created -- never a locked decision."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Solo se aceptan archivos PDF para el análisis de RN Operativo.",
        )

    content = await file.read()
    header = extract_rn_header(content)
    candidates = analyze_operativa_rn(content)
    stored = persist_release_note_pdf(file.filename, content)

    operativa_release = OperativaRelease(
        name=header.name,
        entregable=header.entregable,
        cluster=header.cluster,
        pdf_filename=file.filename,
        pdf_file_path=stored,
    )
    db.add(operativa_release)
    db.flush()

    for candidate in candidates:
        db.add(
            Epc(
                operativa_release_id=operativa_release.id,
                brf_key=candidate.brf_key,
                epc_key=candidate.epc_key,
                titulo=candidate.titulo,
                alcance=candidate.alcance,
                nota_rte=candidate.nota_rte,
                estado_jira=candidate.estado_jira,
                qc_suggestion=candidate.qc_suggestion,
                include_in_qc=(candidate.qc_suggestion == "SUGERIDO_INCLUIR"),
            )
        )
    db.commit()
    db.refresh(operativa_release)

    return OperativaAnalysisResult(operativa_release=OperativaReleaseRead.model_validate(operativa_release))


@router.get("", response_model=list[OperativaReleaseRead])
def list_operativa_releases(db: Session = Depends(get_db)) -> list[OperativaRelease]:
    stmt = (
        select(OperativaRelease)
        .options(selectinload(OperativaRelease.epcs), selectinload(OperativaRelease.qc_release))
        .order_by(OperativaRelease.created_at.desc())
    )
    return list(db.scalars(stmt).all())


@router.post("/{operativa_release_id}/create-release", response_model=ReleaseRead, status_code=status.HTTP_201_CREATED)
def create_qc_release_from_operativa(
    operativa_release_id: int, db: Session = Depends(get_db)
) -> ReleaseRead:
    """Paso 5: create one QC Release from this Operativa. Freezes currently included EPCs.
    A second call must not duplicate — 409 if a Release is already linked."""
    operativa_release = db.scalars(
        select(OperativaRelease)
        .options(selectinload(OperativaRelease.epcs))
        .where(OperativaRelease.id == operativa_release_id)
    ).first()
    if operativa_release is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="OperativaRelease no encontrada.")

    existing = db.scalars(
        select(Release).where(Release.operativa_release_id == operativa_release.id)
    ).first()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Ya existe un Release asociado a esta Operativa.",
        )

    if not operativa_release.name or not operativa_release.name.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="El Nombre es obligatorio para crear el Release.",
        )

    execution_days = calculate_business_days(operativa_release.start_date, operativa_release.end_date)
    jira_filter = operativa_release.jira_filter_url or operativa_release.jira_filter_manual
    deliverable = _resolve_deliverable(
        operativa_release.name or operativa_release.entregable, db
    )

    release = Release(
        name=operativa_release.name.strip(),
        version=OPERATIVA_VERSION,
        platform=OPERATIVA_PLATFORM,
        cluster=operativa_release.cluster,
        description=operativa_release.description,
        start_date=operativa_release.start_date,
        end_date=operativa_release.end_date,
        execution_days=execution_days or None,
        jira_issue_filter=jira_filter,
        qc_resources=None,
        validation_type=None,
        deliverable_id=deliverable.id if deliverable else None,
        operativa_release_id=operativa_release.id,
    )
    db.add(release)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        already = db.scalars(
            select(Release).where(Release.operativa_release_id == operativa_release_id)
        ).first()
        if already is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Ya existe un Release asociado a esta Operativa.",
            ) from exc
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A release with this name, version and platform already exists.",
        ) from exc

    included = list(
        db.scalars(
            select(Epc).where(
                Epc.operativa_release_id == operativa_release.id,
                Epc.include_in_qc.is_(True),
            )
        ).all()
    )
    for epc in included:
        epc.release_id = release.id

    db.commit()
    db.refresh(release)
    read = ReleaseRead.model_validate(release)
    return read.model_copy(
        update={"deliverable_name": release.deliverable.name if release.deliverable else None}
    )


@router.get("/qc-releases/{qc_release_id}/epcs", response_model=list[EpcRead])
def list_epcs_frozen_on_qc_release(qc_release_id: int, db: Session = Depends(get_db)) -> list[Epc]:
    """EPCs frozen onto a QC Release at create time (release_id), not the live include_in_qc flag."""
    release = db.get(Release, qc_release_id)
    if release is None or release.operativa_release_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Release operativo no encontrado.")
    return list(
        db.scalars(
            select(Epc).where(Epc.release_id == qc_release_id).order_by(Epc.id)
        ).all()
    )


@router.get("/{operativa_release_id}", response_model=OperativaReleaseRead)
def get_operativa_release(operativa_release_id: int, db: Session = Depends(get_db)) -> OperativaRelease:
    operativa_release = db.scalars(
        select(OperativaRelease)
        .options(selectinload(OperativaRelease.epcs), selectinload(OperativaRelease.qc_release))
        .where(OperativaRelease.id == operativa_release_id)
    ).first()
    if operativa_release is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="OperativaRelease no encontrada.")
    return operativa_release


@router.delete("/{operativa_release_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_operativa_release(
    operativa_release_id: int,
    db: Session = Depends(get_db),
    _user: AuthUser = Depends(require_jefe),
) -> None:
    operativa_release = db.scalars(
        select(OperativaRelease)
        .options(selectinload(OperativaRelease.qc_release))
        .where(OperativaRelease.id == operativa_release_id)
    ).first()
    if operativa_release is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="OperativaRelease no encontrada.")
    qc_release = operativa_release.qc_release
    if qc_release is not None:
        hard_delete_release_and_notes(db, qc_release)
        return
    pdf_path = operativa_release.pdf_file_path
    db.delete(operativa_release)
    db.commit()
    delete_release_note_pdf(pdf_path)


@router.patch("/{operativa_release_id}", response_model=OperativaReleaseRead)
def update_operativa_release(
    operativa_release_id: int, payload: OperativaReleaseUpdate, db: Session = Depends(get_db)
) -> OperativaRelease:
    """Pasos 2-3: QC may correct header fields and fill configuración. Never invents values."""
    operativa_release = db.get(OperativaRelease, operativa_release_id)
    if operativa_release is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="OperativaRelease no encontrada.")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(operativa_release, field, value)

    db.commit()
    db.refresh(operativa_release)
    return operativa_release


@router.patch("/epcs/{epc_id}", response_model=EpcRead)
def update_epc(epc_id: int, payload: EpcUpdate, db: Session = Depends(get_db)) -> Epc:
    """Paso 3 (alcance_funcional, dispositivos_aplicables) and Paso 4 (include_in_qc).
    include_in_qc is always overridable, never locked. dispositivos_aplicables are never
    inferred by analogy -- the frontend only sends an explicit user selection."""
    epc = db.get(Epc, epc_id)
    if epc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="EPC no encontrado.")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(epc, field, value)

    db.commit()
    db.refresh(epc)
    return epc
