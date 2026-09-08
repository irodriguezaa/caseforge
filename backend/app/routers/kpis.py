"""KPIs module endpoints. Release volume first; later sections get their own routes here."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps.auth import require_dashboard
from app.schemas.kpis import ReleaseKpisRead
from app.services.release_kpis import compute_release_volume_kpis

router = APIRouter(
    prefix="/api/v1/kpis",
    tags=["kpis"],
    dependencies=[Depends(require_dashboard)],
)


@router.get("/releases", response_model=ReleaseKpisRead)
def get_release_kpis(db: Session = Depends(get_db)) -> ReleaseKpisRead:
    return compute_release_volume_kpis(db)
