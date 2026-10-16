"""QC base matrices: import, view, publish, and export. Case editing is out of this phase."""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import AuthUser
from app.db import get_db
from app.deps.auth import get_current_user, require_status_change
from app.models.qc_matrix import QcMatrixCase, QcMatrixDevice, QcMatrixModule, QcMatrixVersion
from app.routers.common import get_release_or_404
from app.schemas.qc_matrix import (
    QcMatrixCaseRead,
    QcMatrixDetail,
    QcMatrixDeviceRead,
    QcMatrixModuleRead,
    QcMatrixPreview,
    QcMatrixPreviewRequest,
    QcMatrixSelectionUpdate,
    QcMatrixSummary,
)
from app.services.qc_matrix_io import import_matrix, parse_upload, publish_version, version_to_workbook
from app.services.qc_matrix_selection import pin_published_matrix, select_be_matrix_cases, select_matrix_cases

router = APIRouter(prefix="/api/v1/qc-matrices", tags=["qc-matrices"])


def _get_version(matrix_id: int, db: Session) -> QcMatrixVersion:
    row = db.get(QcMatrixVersion, matrix_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No existe esa versión de matriz.")
    return row


def _loaded(matrix_id: int, db: Session) -> QcMatrixVersion:
    row = db.execute(
        select(QcMatrixVersion)
        .where(QcMatrixVersion.id == matrix_id)
        .options(
            selectinload(QcMatrixVersion.modules).selectinload(QcMatrixModule.relations),
            selectinload(QcMatrixVersion.devices),
            selectinload(QcMatrixVersion.cases).selectinload(QcMatrixCase.device_links),
            selectinload(QcMatrixVersion.cases).selectinload(QcMatrixCase.module),
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No existe esa versión de matriz.")
    return row


@router.get("", response_model=list[QcMatrixSummary])
def list_matrices(
    db: Session = Depends(get_db),
    _: AuthUser = Depends(get_current_user),
) -> list[QcMatrixSummary]:
    rows = db.execute(select(QcMatrixVersion).order_by(QcMatrixVersion.code, QcMatrixVersion.version)).scalars().all()
    summaries: list[QcMatrixSummary] = []
    for row in rows:
        summaries.append(
            QcMatrixSummary(
                id=row.id,
                code=row.code,
                version=row.version,
                name=row.name,
                status=row.status,
                generated_on=row.generated_on,
                published_at=row.published_at,
                published_by=row.published_by,
                module_count=db.scalar(
                    select(func.count()).select_from(QcMatrixModule).where(QcMatrixModule.matrix_version_id == row.id)
                )
                or 0,
                device_count=db.scalar(
                    select(func.count()).select_from(QcMatrixDevice).where(QcMatrixDevice.matrix_version_id == row.id)
                )
                or 0,
                case_count=db.scalar(
                    select(func.count()).select_from(QcMatrixCase).where(QcMatrixCase.matrix_version_id == row.id)
                )
                or 0,
            )
        )
    return summaries


@router.post("/preview", response_model=QcMatrixPreview)
def preview_matrix_selection(
    payload: QcMatrixPreviewRequest,
    db: Session = Depends(get_db),
    _: AuthUser = Depends(get_current_user),
) -> dict:
    if not payload.platform and payload.release_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Indica el dispositivo o la Release.")
    platform = payload.platform
    validation_type = payload.validation_type
    touched = payload.touched_modules
    templates = payload.template_values
    raw_analysis = payload.raw_analysis
    pinned = None
    if payload.release_id is not None:
        release = get_release_or_404(payload.release_id, db)
        platform = release.platform
        if validation_type is None:
            validation_type = release.validation_type
        if touched is None:
            touched = release.qc_matrix_touched_modules
        if templates is None:
            templates = release.qc_matrix_template_values
        pinned = release.qc_matrix_version_id
        if raw_analysis is None and release.analyses:
            raw_analysis = release.analyses[0].raw_analysis
    raw = raw_analysis if isinstance(raw_analysis, dict) else None
    if (platform or "").strip() == "BE":
        return select_be_matrix_cases(
            db,
            validation_type=validation_type,
            touched_modules=touched,
            template_values=templates,
            raw_analysis=raw,
            pinned_version_id=None,
        )
    return select_matrix_cases(
        db,
        platform=platform,
        validation_type=validation_type,
        touched_modules=touched,
        template_values=templates,
        raw_analysis=raw,
        pinned_version_id=pinned,
    )


@router.post("/releases/{release_id}/selection", response_model=QcMatrixPreview)
def save_matrix_selection(
    release_id: int,
    payload: QcMatrixSelectionUpdate,
    db: Session = Depends(get_db),
    _: AuthUser = Depends(require_status_change),
) -> dict:
    release = get_release_or_404(release_id, db)
    if release.operativa_release_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="La matriz QC aplica a Releases App y BE.")
    release.qc_matrix_touched_modules = payload.touched_modules
    release.qc_matrix_template_values = payload.template_values or None
    is_be = release.be_release_id is not None or (release.platform or "").strip() == "BE"
    if not is_be:
        pin_published_matrix(db, release)
    db.commit()
    db.refresh(release)
    raw = release.analyses[0].raw_analysis if release.analyses else None
    parsed = raw if isinstance(raw, dict) else None
    if is_be:
        return select_be_matrix_cases(
            db,
            validation_type=release.validation_type,
            touched_modules=release.qc_matrix_touched_modules,
            template_values=release.qc_matrix_template_values,
            raw_analysis=parsed,
            pinned_version_id=None,
        )
    return select_matrix_cases(
        db,
        platform=release.platform,
        validation_type=release.validation_type,
        touched_modules=release.qc_matrix_touched_modules,
        template_values=release.qc_matrix_template_values,
        raw_analysis=parsed,
        pinned_version_id=release.qc_matrix_version_id,
    )


@router.get("/{matrix_id}", response_model=QcMatrixDetail)
def get_matrix(
    matrix_id: int,
    db: Session = Depends(get_db),
    _: AuthUser = Depends(get_current_user),
) -> QcMatrixDetail:
    row = _loaded(matrix_id, db)
    devices = sorted(row.devices, key=lambda item: (item.sort_order, item.code))
    return QcMatrixDetail(
        id=row.id,
        code=row.code,
        version=row.version,
        name=row.name,
        status=row.status,
        generated_on=row.generated_on,
        published_at=row.published_at,
        published_by=row.published_by,
        module_count=len(row.modules),
        device_count=len(row.devices),
        case_count=len(row.cases),
        modules=[
            QcMatrixModuleRead(
                module_key=module.module_key,
                group_name=module.group_name,
                name=module.name,
                description=module.description,
                related=[link.related_key for link in module.relations],
            )
            for module in sorted(row.modules, key=lambda item: item.module_key)
        ],
        devices=[
            QcMatrixDeviceRead(
                code=device.code,
                label=device.label,
                screen=device.screen,
                mdp_mx=list(device.mdp_mx or []),
                mdp_other_regions=list(device.mdp_other_regions or []),
            )
            for device in devices
        ],
        cases=[
            QcMatrixCaseRead(
                id=case.id,
                base_id=case.base_id,
                module_key=case.module.module_key if case.module else "",
                title=case.title,
                steps=case.steps,
                expected=case.expected,
                severity=case.severity,
                smoke=case.smoke,
                region=case.region,
                platforms=[link.device.code for link in case.device_links],
                platform_notes={
                    link.device.code: link.note for link in case.device_links if link.note
                },
            )
            for case in sorted(row.cases, key=lambda item: item.base_id or item.title)
        ],
    )


@router.post("/import", response_model=QcMatrixSummary, status_code=status.HTTP_201_CREATED)
async def import_qc_matrix(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: AuthUser = Depends(require_status_change),
) -> QcMatrixSummary:
    raw = await file.read()
    try:
        payload = parse_upload(file.filename or "", raw)
        row = import_matrix(db, payload)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return QcMatrixSummary(
        id=row.id,
        code=row.code,
        version=row.version,
        name=row.name,
        status=row.status,
        generated_on=row.generated_on,
        published_at=row.published_at,
        published_by=row.published_by,
        module_count=len(row.modules),
        device_count=len(row.devices),
        case_count=len(row.cases),
    )


@router.post("/{matrix_id}/publish", response_model=QcMatrixSummary)
def publish_matrix(
    matrix_id: int,
    db: Session = Depends(get_db),
    user: AuthUser = Depends(require_status_change),
) -> QcMatrixSummary:
    row = _get_version(matrix_id, db)
    publish_version(db, row, user.email)
    db.commit()
    db.refresh(row)
    return QcMatrixSummary(
        id=row.id,
        code=row.code,
        version=row.version,
        name=row.name,
        status=row.status,
        generated_on=row.generated_on,
        published_at=row.published_at,
        published_by=row.published_by,
        module_count=db.scalar(
            select(func.count()).select_from(QcMatrixModule).where(QcMatrixModule.matrix_version_id == row.id)
        )
        or 0,
        device_count=db.scalar(
            select(func.count()).select_from(QcMatrixDevice).where(QcMatrixDevice.matrix_version_id == row.id)
        )
        or 0,
        case_count=db.scalar(
            select(func.count()).select_from(QcMatrixCase).where(QcMatrixCase.matrix_version_id == row.id)
        )
        or 0,
    )


@router.get("/{matrix_id}/export")
def export_matrix(
    matrix_id: int,
    db: Session = Depends(get_db),
    _: AuthUser = Depends(get_current_user),
) -> Response:
    row = _loaded(matrix_id, db)
    content = version_to_workbook(row)
    filename = f"Matriz_{row.code}_v{row.version}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
