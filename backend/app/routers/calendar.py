"""QC calendar: Outlook ICS (method B) + CaseForge windows. Graph Calendar is not required."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps.auth import require_dashboard, require_jefe
from app.schemas.calendar import QcCalendarDayResponse, QcCalendarEvent, QcCalendarWeekResponse
from app.services.ics_calendar import fetch_ics_events, ics_configured, save_uploaded_ics
from app.services.qc_local_calendar import caseforge_qc_events

router = APIRouter(
    prefix="/api/v1/calendar",
    tags=["calendar"],
    dependencies=[Depends(require_dashboard)],
)

ICS_HOW_TO = (
    "Exporta el calendario desde Calendario de Mac (Archivo → Exportar → .ics) "
    "o, en Outlook de escritorio clásico, Archivo → Guardar calendario en iCalendar. "
    "Luego pulsa «Cargar .ics» en este panel."
)


def _zone() -> ZoneInfo:
    return ZoneInfo(settings.ms_graph_timezone)


def _parse_day(date: str | None, zone: ZoneInfo) -> datetime:
    if not date:
        return datetime.now(zone)
    try:
        return datetime.fromisoformat(date).replace(tzinfo=zone)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="date must be YYYY-MM-DD."
        ) from exc


def _merge_events(
    db: Session, start: datetime, end: datetime, zone: ZoneInfo
) -> tuple[list[QcCalendarEvent], str, str | None]:
    local = caseforge_qc_events(db, range_start=start, range_end=end, zone=zone)
    if not ics_configured():
        return local, "caseforge", ICS_HOW_TO
    try:
        outlook = fetch_ics_events(start, end, zone)
    except httpx.HTTPError:
        return local, "caseforge", "No se pudo leer el ICS de Outlook."
    except OSError:
        return local, "caseforge", "No se pudo leer el archivo .ics cargado."
    merged = outlook + local
    merged.sort(key=lambda row: row.start)
    note = None if outlook else "El ICS de Outlook no trajo eventos en este periodo."
    return merged, "outlook-ics", note


@router.get("/day", response_model=QcCalendarDayResponse)
def get_day_view(
    date: str | None = Query(default=None, description="YYYY-MM-DD, default hoy"),
    db: Session = Depends(get_db),
) -> QcCalendarDayResponse:
    zone = _zone()
    day = _parse_day(date, zone)
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = day.replace(hour=23, minute=59, second=59, microsecond=0)
    events, feed, note = _merge_events(db, start, end, zone)
    return QcCalendarDayResponse(date=day.date().isoformat(), events=events, feed=feed, outlook_note=note)


@router.get("/week", response_model=QcCalendarWeekResponse)
def get_week_view(
    date: str | None = Query(default=None, description="YYYY-MM-DD dentro de la semana deseada"),
    db: Session = Depends(get_db),
) -> QcCalendarWeekResponse:
    zone = _zone()
    ref_day = _parse_day(date, zone)
    monday = (ref_day - timedelta(days=ref_day.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = (monday + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=0)
    events, feed, note = _merge_events(db, monday, end, zone)
    return QcCalendarWeekResponse(
        week_start=monday.date().isoformat(), events=events, feed=feed, outlook_note=note
    )


@router.post("/ics")
async def upload_outlook_ics(
    file: UploadFile = File(...),
    _user=Depends(require_jefe),
) -> dict[str, str | int]:
    name = (file.filename or "").lower()
    if not name.endswith(".ics"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Sube un archivo .ics exportado de Calendario o Outlook.")
    content = await file.read()
    if len(content) > 25_000_000:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="El .ics es demasiado grande (máx. 25 MB).")
    try:
        path = save_uploaded_ics(content)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo guardar el .ics.") from exc
    return {"status": "ok", "path": path.name, "bytes": len(content)}
