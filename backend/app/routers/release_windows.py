"""ReleaseWindow CRUD endpoints. Nested under a Release for creation/listing, flat for direct access."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.window import ReleaseWindow
from app.routers.common import get_release_or_404
from app.schemas.window import ReleaseWindowCreate, ReleaseWindowRead, ReleaseWindowUpdate

router = APIRouter(prefix="/api/v1", tags=["release-windows"])


def _get_or_404(window_id: int, db: Session) -> ReleaseWindow:
    window = db.get(ReleaseWindow, window_id)
    if window is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Release window not found.")
    return window


@router.get("/release-windows", response_model=list[ReleaseWindowRead])
def list_all_release_windows(db: Session = Depends(get_db)) -> list[ReleaseWindow]:
    """Flat listing (not scoped to one release) -- used by the Dashboard filter bar."""
    stmt = select(ReleaseWindow).order_by(ReleaseWindow.start_date.desc())
    return list(db.execute(stmt).scalars().all())


@router.get("/releases/{release_id}/windows", response_model=list[ReleaseWindowRead])
def list_release_windows(release_id: int, db: Session = Depends(get_db)) -> list[ReleaseWindow]:
    get_release_or_404(release_id, db)
    stmt = (
        select(ReleaseWindow)
        .where(ReleaseWindow.release_id == release_id)
        .order_by(ReleaseWindow.start_date.desc())
    )
    return list(db.execute(stmt).scalars().all())


@router.post(
    "/releases/{release_id}/windows", response_model=ReleaseWindowRead, status_code=status.HTTP_201_CREATED
)
def create_release_window(
    release_id: int, payload: ReleaseWindowCreate, db: Session = Depends(get_db)
) -> ReleaseWindow:
    get_release_or_404(release_id, db)
    window = ReleaseWindow(release_id=release_id, **payload.model_dump())
    db.add(window)
    db.commit()
    db.refresh(window)
    return window


@router.get("/release-windows/{window_id}", response_model=ReleaseWindowRead)
def get_release_window(window_id: int, db: Session = Depends(get_db)) -> ReleaseWindow:
    return _get_or_404(window_id, db)


@router.patch("/release-windows/{window_id}", response_model=ReleaseWindowRead)
def update_release_window(
    window_id: int, payload: ReleaseWindowUpdate, db: Session = Depends(get_db)
) -> ReleaseWindow:
    window = _get_or_404(window_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(window, field, value)
    db.commit()
    db.refresh(window)
    return window


@router.delete("/release-windows/{window_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_release_window(window_id: int, db: Session = Depends(get_db)) -> None:
    window = _get_or_404(window_id, db)
    db.delete(window)
    db.commit()
