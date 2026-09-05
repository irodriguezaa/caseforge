"""QC calendar events from CaseForge schedules (no Outlook / Graph)."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.release import Release, ReleaseStatus
from app.models.window import ReleaseWindow, WindowStatus
from app.schemas.calendar import QcCalendarEvent


def caseforge_qc_events(
    db: Session,
    *,
    range_start: datetime,
    range_end: datetime,
    zone: ZoneInfo,
) -> list[QcCalendarEvent]:
    start_day = range_start.date()
    end_day = range_end.date()
    now = datetime.now(zone)
    events: list[QcCalendarEvent] = []

    windows = list(
        db.execute(
            select(ReleaseWindow)
            .options(selectinload(ReleaseWindow.release))
            .where(
                ReleaseWindow.status != WindowStatus.CLOSED,
                ReleaseWindow.start_date <= end_day,
                ReleaseWindow.end_date >= start_day,
            )
        )
        .scalars()
        .all()
    )
    seen_releases: set[int] = set()
    for window in windows:
        release = window.release
        if release is None or release.status == ReleaseStatus.CANCELLED:
            continue
        seen_releases.add(release.id)
        events.append(
            _event_from_span(
                event_id=f"rw-{window.id}",
                title=_release_title(release, window.name),
                span_start=window.start_date,
                span_end=window.end_date,
                location=_location(release),
                range_start=start_day,
                range_end=end_day,
                zone=zone,
                now=now,
                href=f"/releases/{release.id}",
            )
        )

    dated_releases = list(
        db.execute(
            select(Release).where(
                Release.status.in_((ReleaseStatus.DRAFT, ReleaseStatus.IN_PROGRESS)),
                Release.start_date.is_not(None),
                Release.end_date.is_not(None),
                Release.start_date <= end_day,
                Release.end_date >= start_day,
            )
        )
        .scalars()
        .all()
    )
    for release in dated_releases:
        if release.id in seen_releases:
            continue
        assert release.start_date is not None and release.end_date is not None
        events.append(
            _event_from_span(
                event_id=f"rel-{release.id}",
                title=_release_title(release, None),
                span_start=release.start_date,
                span_end=release.end_date,
                location=_location(release),
                range_start=start_day,
                range_end=end_day,
                zone=zone,
                now=now,
                href=f"/releases/{release.id}",
            )
        )

    events.sort(key=lambda row: (row.start, row.title))
    return events


def _origin(release: Release) -> str:
    if release.operativa_release_id is not None:
        return "Operativa"
    if release.be_release_id is not None:
        return "Release BE"
    return "Release Apps"


def _release_title(release: Release, window_name: str | None) -> str:
    base = f"{_origin(release)} · {release.name}"
    if release.version:
        base = f"{base} v{release.version}"
    if window_name:
        return f"{base} · {window_name}"
    return base


def _location(release: Release) -> str:
    parts = [part for part in (release.cluster, release.platform) if part]
    return " · ".join(parts) if parts else "QC"


def _event_from_span(
    *,
    event_id: str,
    title: str,
    span_start: date,
    span_end: date,
    location: str,
    range_start: date,
    range_end: date,
    zone: ZoneInfo,
    now: datetime,
    href: str,
) -> QcCalendarEvent:
    visible_start = max(span_start, range_start)
    visible_end = min(span_end, range_end)
    start_dt = datetime.combine(visible_start, time(9, 0), tzinfo=zone)
    end_dt = datetime.combine(visible_end, time(18, 0), tzinfo=zone)
    live = span_start <= now.date() <= span_end
    return QcCalendarEvent(
        id=event_id,
        title=title,
        start=start_dt.isoformat(),
        end=end_dt.isoformat(),
        location=location,
        is_live=live,
        web_link=href,
        categories=["CaseForge"],
        source="caseforge",
    )
