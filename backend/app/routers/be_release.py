"""Release BE router -- optional RN, header/config, create QC Release.

NOT implemented: Matriz QC, generación de casos, estimación, recursos QC.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.be_release import BeRelease
from app.models.release import Release
from app.routers.releases import _resolve_deliverable, to_release_read
from app.schemas.be_release import (
    BeAnalysisResult,
    BeReleaseRead,
    BeReleaseUpdate,
    BeRegresivoScope,
)
from app.schemas.release import ReleaseRead
from app.services.be_rn_analyzer import extract_be_rn_header

router = APIRouter(prefix="/api/v1/releases-be", tags=["releases-be"])

BE_PLATFORM = "BE"
BE_VERSION = "BE"


def _get_be_or_404(be_release_id: int, db: Session) -> BeRelease:
    be_release = db.get(BeRelease, be_release_id)
    if be_release is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Release BE no encontrado.")
    return be_release


@router.post("", response_model=BeReleaseRead, status_code=status.HTTP_201_CREATED)
def create_be_release_without_rn(db: Session = Depends(get_db)) -> BeRelease:
    """Paso 1: continuar sin PDF. The RN is optional; QC fills Paso 2 manually."""
    be_release = BeRelease(pdf_filename=None)
    db.add(be_release)
    db.commit()
    db.refresh(be_release)
    return be_release


@router.post("/analyze-rn", response_model=BeAnalysisResult, status_code=status.HTTP_201_CREATED)
async def analyze_be_release_note(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> BeAnalysisResult:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Solo se aceptan archivos PDF para el análisis de RN de BE.",
        )
    content = await file.read()
    header = extract_be_rn_header(content)
    be_release = BeRelease(
        name=header.name,
        entregable=header.entregable,
        swf=header.swf,
        pdf_filename=file.filename,
    )
    db.add(be_release)
    db.commit()
    db.refresh(be_release)
    return BeAnalysisResult(be_release=BeReleaseRead.model_validate(be_release))


@router.get("", response_model=list[BeReleaseRead])
def list_be_releases(db: Session = Depends(get_db)) -> list[BeRelease]:
    stmt = select(BeRelease).order_by(BeRelease.created_at.desc())
    return list(db.scalars(stmt).all())


@router.post("/{be_release_id}/create-release", response_model=ReleaseRead, status_code=status.HTTP_201_CREATED)
def create_qc_release_from_be(be_release_id: int, db: Session = Depends(get_db)) -> ReleaseRead:
    be_release = _get_be_or_404(be_release_id, db)

    existing = db.scalars(select(Release).where(Release.be_release_id == be_release.id)).first()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Ya existe un Release asociado a este Release BE.",
        )

    if not be_release.name or not be_release.name.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="El Nombre es obligatorio para crear el Release BE.",
        )
    if not be_release.regresivo_scope:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="El Alcance de regresivo es obligatorio para crear el Release BE.",
        )
    if be_release.regresivo_scope == BeRegresivoScope.ACOTADO.value:
        if not be_release.affected_component or not be_release.affected_component.strip():
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Componente / Funcionalidad Afectada es obligatorio cuando el alcance es Acotado.",
            )

    deliverable = _resolve_deliverable(be_release.entregable, db)
    release = Release(
        name=be_release.name.strip(),
        version=BE_VERSION,
        platform=BE_PLATFORM,
        cluster=None,
        description=be_release.description,
        qc_resources=None,
        validation_type=None,
        deliverable_id=deliverable.id if deliverable else None,
        be_release_id=be_release.id,
    )
    db.add(release)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        already = db.scalars(select(Release).where(Release.be_release_id == be_release_id)).first()
        if already is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="Ya existe un Release asociado a este Release BE.",
            ) from exc
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="A release with this name, version and platform already exists.",
        ) from exc

    db.commit()
    db.refresh(release)
    return to_release_read(release)


@router.get("/{be_release_id}", response_model=BeReleaseRead)
def get_be_release(be_release_id: int, db: Session = Depends(get_db)) -> BeRelease:
    return _get_be_or_404(be_release_id, db)


@router.patch("/{be_release_id}", response_model=BeReleaseRead)
def update_be_release(
    be_release_id: int, payload: BeReleaseUpdate, db: Session = Depends(get_db)
) -> BeRelease:
    be_release = _get_be_or_404(be_release_id, db)
    updates = payload.model_dump(exclude_unset=True)
    if "regresivo_scope" in updates and updates["regresivo_scope"] is not None:
        scope = updates["regresivo_scope"]
        updates["regresivo_scope"] = scope.value if isinstance(scope, BeRegresivoScope) else scope
        if updates["regresivo_scope"] != BeRegresivoScope.ACOTADO.value and "affected_component" not in updates:
            updates["affected_component"] = None
    for field, value in updates.items():
        setattr(be_release, field, value)
    db.commit()
    db.refresh(be_release)
    return be_release
