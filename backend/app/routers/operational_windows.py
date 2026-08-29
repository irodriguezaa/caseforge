"""OperationalWindow CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.window import OperationalWindow, WindowStatus
from app.schemas.window import OperationalWindowCreate, OperationalWindowRead, OperationalWindowUpdate

router = APIRouter(prefix="/api/v1/operational-windows", tags=["operational-windows"])


def _get_or_404(window_id: int, db: Session) -> OperationalWindow:
    window = db.get(OperationalWindow, window_id)
    if window is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Operational window not found.")
    return window


@router.get("", response_model=list[OperationalWindowRead])
def list_operational_windows(
    status_filter: WindowStatus | None = Query(default=None, alias="status"),
    cluster: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[OperationalWindow]:
    stmt = select(OperationalWindow).order_by(OperationalWindow.start_date.desc())
    if status_filter is not None:
        stmt = stmt.where(OperationalWindow.status == status_filter)
    if cluster is not None:
        stmt = stmt.where(OperationalWindow.cluster == cluster)
    return list(db.execute(stmt).scalars().all())


@router.post("", response_model=OperationalWindowRead, status_code=status.HTTP_201_CREATED)
def create_operational_window(
    payload: OperationalWindowCreate, db: Session = Depends(get_db)
) -> OperationalWindow:
    window = OperationalWindow(**payload.model_dump())
    db.add(window)
    db.commit()
    db.refresh(window)
    return window


@router.get("/{window_id}", response_model=OperationalWindowRead)
def get_operational_window(window_id: int, db: Session = Depends(get_db)) -> OperationalWindow:
    return _get_or_404(window_id, db)


@router.patch("/{window_id}", response_model=OperationalWindowRead)
def update_operational_window(
    window_id: int, payload: OperationalWindowUpdate, db: Session = Depends(get_db)
) -> OperationalWindow:
    window = _get_or_404(window_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(window, field, value)
    db.commit()
    db.refresh(window)
    return window


@router.delete("/{window_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_operational_window(window_id: int, db: Session = Depends(get_db)) -> None:
    window = _get_or_404(window_id, db)
    db.delete(window)
    db.commit()
