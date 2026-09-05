"""Filter Outlook events to QC-related meetings and normalize for the UI."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings
from app.schemas.calendar import QcCalendarEvent

QC_KEYWORDS = (
    "qc",
    "quality control",
    "control de calidad",
    "release",
    "liberación",
    "liberacion",
    "regresión",
    "regresion",
    "smoke",
    "test",
    "pruebas",
)
QC_CATEGORIES = ("QC", "Release", "Testing")

QC_EXCLUDE_ORGANIZERS = (
    "mcastagno@amco.mx",
    "osorniodm@hitss.com"
)


def is_qc_meeting(event: dict) -> bool:
    subject = (event.get("subject") or "").lower()
    categories = event.get("categories") or []
    if any(keyword in subject for keyword in QC_KEYWORDS):
        return True
    return any(category in QC_CATEGORIES for category in categories)


def _parse_graph_datetime(value: str) -> datetime:
    cleaned = value.strip().replace("Z", "+00:00")
    if "." in cleaned:
        head, rest = cleaned.split(".", 1)
        frac = ""
        tz = ""
        for index, char in enumerate(rest):
            if char.isdigit():
                frac += char
            else:
                tz = rest[index:]
                break
        cleaned = f"{head}.{frac[:6]}{tz}"
    parsed = datetime.fromisoformat(cleaned)
    zone = ZoneInfo(settings.ms_graph_timezone)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)


def normalize_event(event: dict, *, now: datetime | None = None) -> QcCalendarEvent:
    start = _parse_graph_datetime(event["start"]["dateTime"])
    end = _parse_graph_datetime(event["end"]["dateTime"])
    current = now or datetime.now(ZoneInfo(settings.ms_graph_timezone))
    location = (event.get("location") or {}).get("displayName")
    return QcCalendarEvent(
        id=event.get("id") or "",
        title=event.get("subject") or "(sin título)",
        start=start.isoformat(),
        end=end.isoformat(),
        location=location or None,
        is_live=start <= current <= end,
        web_link=event.get("webLink"),
        categories=list(event.get("categories") or []),
    )
