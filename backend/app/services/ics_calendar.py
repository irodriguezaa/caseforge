"""Read a published Outlook ICS feed. No Graph Calendar permission required."""

from __future__ import annotations

import calendar as cal
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pathlib import Path

import httpx

from app.config import settings
from app.schemas.calendar import QcCalendarEvent
from app.services.qc_calendar import QC_KEYWORDS, QC_EXCLUDE_ORGANIZERS

_WEEKDAY = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
_MAX_OCCURRENCES = 400


_events_cache: tuple[tuple[str, int, int], list[dict[str, str]]] | None = None


def ics_file_path() -> Path:
    custom = (settings.ms_calendar_ics_path or "").strip()
    if custom:
        return Path(custom)
    return Path(settings.rn_storage_dir) / "outlook.ics"


def ics_configured() -> bool:
    if (getattr(settings, "ms_calendar_ics_url", "") or "").strip():
        return True
    path = ics_file_path()
    return path.is_file() and path.stat().st_size > 0


def save_uploaded_ics(content: bytes) -> Path:
    text = content.decode("utf-8", errors="replace")
    if "BEGIN:VCALENDAR" not in text.upper():
        raise ValueError("El archivo no parece un calendario .ics (Calendario/Outlook).")
    path = ics_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _load_ics_text() -> str:
    url = (settings.ms_calendar_ics_url or "").strip()
    if url:
        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "CaseForge-QC-Calendar"})
            response.raise_for_status()
            return response.text
    path = ics_file_path()
    return path.read_text(encoding="utf-8", errors="replace")

def _organizer_email(block: dict[str, Any]) -> str:
    raw = str(block.get("ORGANIZER") or "")
    return raw.replace("mailto:", "").strip().lower()

def fetch_ics_events(range_start: datetime, range_end: datetime, zone: ZoneInfo) -> list[QcCalendarEvent]:
    if not ics_configured():
        return []
    qc_only = settings.ms_calendar_ics_qc_only
    now = datetime.now(zone)
    excluded_organizers = {o.lower() for o in QC_EXCLUDE_ORGANIZERS} 
    rows: list[QcCalendarEvent] = []
    for block, start, end in _expanded_occurrences(_cached_vevents(), range_start, range_end, zone):
        if _organizer_email(block) in excluded_organizers:
            continue
        title = str(block.get("SUMMARY") or "").replace("\\,", ",").replace("\\n", " ").strip()
        if qc_only and not any(keyword in title.lower() for keyword in QC_KEYWORDS):
            continue
        location = str(block.get("LOCATION") or "").replace("\\,", ",").strip() or None
        uid = str(block.get("UID") or f"{title}-{start.isoformat()}")
        rows.append(
            QcCalendarEvent(
                id=f"ics-{uid}-{start.isoformat()}"[:180],
                title=title or "(sin título)",
                start=start.astimezone(zone).isoformat(),
                end=end.astimezone(zone).isoformat(),
                location=location,
                is_live=start <= now <= end,
                web_link=str(block.get("URL") or "") or None,
                categories=["Outlook"],
                source="outlook-ics",
            )
        )
    rows.sort(key=lambda row: row.start)
    return rows


def _cached_vevents() -> list[dict[str, str]]:
    global _events_cache
    url = (getattr(settings, "ms_calendar_ics_url", "") or "").strip()
    if url:
        return _vevents(_load_ics_text())
    path = ics_file_path()
    stat = path.stat()
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    if _events_cache and _events_cache[0] == key:
        return _events_cache[1]
    events = _vevents(_load_ics_text())
    _events_cache = (key, events)
    return events


def _vevents(raw: str) -> list[dict[str, Any]]:
    unfolded = _unfold(raw)
    events: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in unfolded.splitlines():
        if line.strip() == "BEGIN:VEVENT":
            current = {}
            continue
        if line.strip() == "END:VEVENT":
            if current:
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        name = key.split(";", 1)[0].upper()
        if name == "EXDATE":
            stamps = current.setdefault("_EXDATES", [])
            stamps.append((key, value))
            continue
        if name in current:
            continue
        current[name] = value
        if name == "DTSTART":
            current["_DTSTART_RAW"] = key
        if name == "DTEND":
            current["_DTEND_RAW"] = key
        if name == "RECURRENCE-ID":
            current["_RECURRENCE_RAW"] = key
    return events


def _expanded_occurrences(
    blocks: list[dict[str, Any]],
    range_start: datetime,
    range_end: datetime,
    zone: ZoneInfo,
) -> list[tuple[dict[str, Any], datetime, datetime]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    anonymous: list[dict[str, Any]] = []
    for block in blocks:
        uid = str(block.get("UID") or "").strip()
        if uid:
            grouped[uid].append(block)
        else:
            anonymous.append(block)

    rows: list[tuple[dict[str, Any], datetime, datetime]] = []
    for group in grouped.values():
        rows.extend(_expand_uid_group(group, range_start, range_end, zone))
    for block in anonymous:
        rows.extend(_expand_uid_group([block], range_start, range_end, zone))
    return rows


def _expand_uid_group(
    group: list[dict[str, Any]],
    range_start: datetime,
    range_end: datetime,
    zone: ZoneInfo,
) -> list[tuple[dict[str, Any], datetime, datetime]]:
    masters = [row for row in group if row.get("RRULE") and not row.get("RECURRENCE-ID")]
    overrides = [row for row in group if row.get("RECURRENCE-ID")]
    singles = [row for row in group if not row.get("RRULE") and not row.get("RECURRENCE-ID")]
    replaced: set[datetime] = set()
    cancelled: set[datetime] = set()
    override_rows: list[tuple[dict[str, Any], datetime, datetime]] = []
    for block in overrides:
        original = _parse_ics_dt(str(block.get("RECURRENCE-ID") or ""), str(block.get("_RECURRENCE_RAW") or ""), zone)
        start = _parse_ics_dt(str(block.get("DTSTART") or ""), str(block.get("_DTSTART_RAW") or ""), zone)
        end = _parse_ics_dt(str(block.get("DTEND") or "") or None, str(block.get("_DTEND_RAW") or "") or None, zone)
        stamp = original or start
        if stamp is not None:
            replaced.add(stamp)
        if str(block.get("STATUS") or "").upper() == "CANCELLED":
            if stamp is not None:
                cancelled.add(stamp)
            continue
        if start is None:
            continue
        if end is None:
            end = start + timedelta(hours=1)
        if end >= range_start and start <= range_end:
            override_rows.append((block, start, end))

    expanded: list[tuple[dict[str, Any], datetime, datetime]] = []
    for master in masters:
        if str(master.get("STATUS") or "").upper() == "CANCELLED":
            continue
        for start, end in _rrule_instances(master, range_start, range_end, zone):
            if start in replaced or start in cancelled:
                continue
            expanded.append((master, start, end))

    if not masters:
        for block in singles:
            start = _parse_ics_dt(str(block.get("DTSTART") or ""), str(block.get("_DTSTART_RAW") or ""), zone)
            end = _parse_ics_dt(str(block.get("DTEND") or "") or None, str(block.get("_DTEND_RAW") or "") or None, zone)
            if start is None:
                continue
            if end is None:
                end = start + timedelta(hours=1)
            if end >= range_start and start <= range_end:
                expanded.append((block, start, end))

    return expanded + override_rows


def _rrule_instances(
    block: dict[str, Any],
    range_start: datetime,
    range_end: datetime,
    zone: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    start = _parse_ics_dt(str(block.get("DTSTART") or ""), str(block.get("_DTSTART_RAW") or ""), zone)
    end = _parse_ics_dt(str(block.get("DTEND") or "") or None, str(block.get("_DTEND_RAW") or "") or None, zone)
    if start is None:
        return []
    if end is None:
        end = start + timedelta(hours=1)
    duration = end - start
    rules = _parse_rrule(str(block.get("RRULE") or ""))
    until = _parse_ics_dt(rules.get("UNTIL"), None, zone)
    count = int(rules["COUNT"]) if rules.get("COUNT", "").isdigit() else None
    interval = int(rules["INTERVAL"]) if rules.get("INTERVAL", "").isdigit() else 1
    freq = (rules.get("FREQ") or "DAILY").upper()
    bydays = {_WEEKDAY[part] for part in rules.get("BYDAY", "").split(",") if part in _WEEKDAY}
    excluded = {
        parsed
        for raw_key, value in block.get("_EXDATES") or []
        for stamp in str(value).split(",")
        if (parsed := _parse_ics_dt(stamp.strip(), str(raw_key), zone)) is not None
    }

    def counts_as_occurrence(stamp: datetime) -> bool:
        weekday_ok = not bydays or stamp.weekday() in bydays
        week_ok = True
        if freq == "WEEKLY" and interval > 1:
            week_ok = ((stamp.date() - start.date()).days // 7) % interval == 0
        return weekday_ok and week_ok and stamp not in excluded

    cursor = start
    emitted = 0
    skipped = 0
    while cursor + duration < range_start and skipped < 20_000:
        if until is not None and cursor > until:
            return []
        if counts_as_occurrence(cursor):
            emitted += 1
            if count is not None and emitted >= count:
                return []
        nxt = _advance(cursor, freq, interval, bydays, start)
        if nxt is None or nxt <= cursor:
            return []
        cursor = nxt
        skipped += 1

    rows: list[tuple[datetime, datetime]] = []
    while emitted < _MAX_OCCURRENCES:
        if until is not None and cursor > until:
            break
        if cursor > range_end:
            break
        if counts_as_occurrence(cursor):
            instance_end = cursor + duration
            if instance_end >= range_start and cursor <= range_end:
                rows.append((cursor, instance_end))
            emitted += 1
            if count is not None and emitted >= count:
                break
        nxt = _advance(cursor, freq, interval, bydays, start)
        if nxt is None or nxt <= cursor:
            break
        cursor = nxt
    return rows


def _advance(
    cursor: datetime,
    freq: str,
    interval: int,
    bydays: set[int],
    series_start: datetime,
) -> datetime | None:
    if freq == "DAILY":
        return cursor + timedelta(days=max(1, interval))
    if freq == "WEEKLY":
        return cursor + timedelta(days=1)
    if freq == "MONTHLY":
        month = cursor.month - 1 + max(1, interval)
        year = cursor.year + month // 12
        month = month % 12 + 1
        day = min(series_start.day, cal.monthrange(year, month)[1])
        try:
            return cursor.replace(year=year, month=month, day=day)
        except ValueError:
            return None
    return cursor + timedelta(days=1)


def _parse_rrule(text: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for piece in text.split(";"):
        if "=" not in piece:
            continue
        key, value = piece.split("=", 1)
        parts[key.strip().upper()] = value.strip()
    return parts


def _unfold(raw: str) -> str:
    lines = raw.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    for line in lines:
        if out and (line.startswith(" ") or line.startswith("\t")):
            out[-1] += line[1:]
        else:
            out.append(line)
    return "\n".join(out)


def _parse_ics_dt(value: str | None, raw_key: str | None, zone: ZoneInfo) -> datetime | None:
    if not value:
        return None
    stamp = value.strip()
    is_utc = stamp.endswith("Z")
    stamp = stamp.rstrip("Z")
    local_zone = _zone_from_key(raw_key, zone)
    if "T" not in stamp:
        try:
            day = datetime.strptime(stamp[:8], "%Y%m%d")
        except ValueError:
            return None
        return day.replace(tzinfo=local_zone)
    try:
        parsed = datetime.strptime(stamp[:15], "%Y%m%dT%H%M%S")
    except ValueError:
        try:
            parsed = datetime.strptime(stamp[:13], "%Y%m%dT%H%M")
        except ValueError:
            return None
    if is_utc:
        return parsed.replace(tzinfo=timezone.utc).astimezone(zone)
    return parsed.replace(tzinfo=local_zone).astimezone(zone)


def _zone_from_key(raw_key: str | None, fallback: ZoneInfo) -> ZoneInfo:
    if not raw_key or "TZID=" not in raw_key.upper():
        return fallback
    try:
        tzid = raw_key.split("TZID=", 1)[1].split(";", 1)[0].strip()
        return ZoneInfo(tzid)
    except (IndexError, KeyError, ValueError, ZoneInfoNotFoundError, OSError):
        return fallback
