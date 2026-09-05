"""QC calendar filter and endpoints. Graph is mocked; MSAL is not required."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.services.graph_auth import calendar_view_path, is_app_only_token, normalize_access_token
from app.services.qc_calendar import is_qc_meeting, normalize_event


def test_is_qc_meeting_by_title() -> None:
    assert is_qc_meeting({"subject": "QC AUP standup", "categories": []}) is True
    assert is_qc_meeting({"subject": "Almuerzo equipo", "categories": []}) is False


def test_is_qc_meeting_by_outlook_category() -> None:
    assert is_qc_meeting({"subject": "Sync", "categories": ["QC"]}) is True


def test_normalize_event_marks_live(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.qc_calendar.settings",
        type("S", (), {"ms_graph_timezone": "America/Mexico_City"})(),
    )
    zone = ZoneInfo("America/Mexico_City")
    now = datetime(2026, 9, 2, 12, 0, tzinfo=zone)
    event = {
        "id": "1",
        "subject": "QC daily",
        "start": {"dateTime": "2026-09-02T11:00:00"},
        "end": {"dateTime": "2026-09-02T13:00:00"},
        "location": {"displayName": "Teams"},
        "categories": ["QC"],
        "webLink": "https://outlook.office.com/e/1",
    }
    row = normalize_event(event, now=now)
    assert row.is_live is True
    assert row.title == "QC daily"
    assert row.location == "Teams"


def test_calendar_week_without_outlook_returns_caseforge_feed(client) -> None:
    response = client.get("/api/v1/calendar/week")
    assert response.status_code == 200
    body = response.json()
    assert body["feed"] == "caseforge"
    assert body["events"] == []
    assert "Guardar calendario" in (body.get("outlook_note") or "")


def test_calendar_week_includes_release_window(client) -> None:
    created = client.post(
        "/api/v1/releases",
        json={"name": "Claro Video", "version": "9.0", "platform": "WEB", "cluster": "AUP"},
    )
    assert created.status_code == 201
    release_id = created.json()["id"]
    window = client.post(
        f"/api/v1/releases/{release_id}/windows",
        json={
            "name": "Regresión",
            "start_date": "2026-09-01",
            "end_date": "2026-09-05",
            "status": "ACTIVE",
        },
    )
    assert window.status_code == 201

    response = client.get("/api/v1/calendar/week", params={"date": "2026-09-02"})
    assert response.status_code == 200
    events = response.json()["events"]
    assert len(events) == 1
    assert events[0]["source"] == "caseforge"
    assert "Regresión" in events[0]["title"]
    assert events[0]["web_link"] == f"/releases/{release_id}"


def test_normalize_access_token_strips_bearer_and_quotes() -> None:
    assert normalize_access_token('Bearer abc') == "abc"
    assert normalize_access_token('"xyz"') == "xyz"


def test_app_token_without_mailbox_explains_me_failure() -> None:
    claims = {"idtyp": "app", "roles": ["Calendars.Read"]}
    assert is_app_only_token(claims) is True
    try:
        calendar_view_path(claims, None)
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "MS_GRAPH_MAILBOX" in exc.detail


def test_upload_ics_then_week_lists_event(client, tmp_path, monkeypatch) -> None:
    ics_path = tmp_path / "outlook.ics"
    monkeypatch.setattr("app.services.ics_calendar.ics_file_path", lambda: ics_path)
    payload = (
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:u1\nSUMMARY:QC gate\n"
        "DTSTART:20260902T150000Z\nDTEND:20260902T160000Z\nEND:VEVENT\nEND:VCALENDAR\n"
    )
    response = client.post(
        "/api/v1/calendar/ics",
        files={"file": ("calendar.ics", payload.encode("utf-8"), "text/calendar")},
    )
    assert response.status_code == 200
    week = client.get("/api/v1/calendar/week", params={"date": "2026-09-02"})
    assert week.status_code == 200
    titles = [row["title"] for row in week.json()["events"]]
    assert "QC gate" in titles


def test_ics_parser_reads_utc_vevent() -> None:
    from zoneinfo import ZoneInfo

    from app.services.ics_calendar import _parse_ics_dt, _vevents

    sample = (
        "BEGIN:VCALENDAR\n"
        "BEGIN:VEVENT\n"
        "UID:one\n"
        "SUMMARY:QC daily\n"
        "DTSTART:20260902T150000Z\n"
        "DTEND:20260902T160000Z\n"
        "LOCATION:Teams\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n"
    )
    events = _vevents(sample)
    assert len(events) == 1
    assert events[0]["SUMMARY"] == "QC daily"
    zone = ZoneInfo("America/Mexico_City")
    start = _parse_ics_dt(events[0]["DTSTART"], events[0].get("_DTSTART_RAW"), zone)
    assert start is not None
    assert start.year == 2026


def test_ics_rrule_expands_daily_and_weekdays(tmp_path, monkeypatch) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    import app.services.ics_calendar as ics_mod

    ics_path = tmp_path / "outlook.ics"
    ics_path.write_text(
        "BEGIN:VCALENDAR\n"
        "BEGIN:VEVENT\n"
        "UID:paypal-daily\n"
        "SUMMARY:Paypal Check (daily)\n"
        "DTSTART;TZID=America/Mexico_City:20260831T093000\n"
        "DTEND;TZID=America/Mexico_City:20260831T100000\n"
        "RRULE:FREQ=DAILY;COUNT=7\n"
        "END:VEVENT\n"
        "BEGIN:VEVENT\n"
        "UID:tc-cenam\n"
        "SUMMARY:TC CENAM\n"
        "DTSTART;TZID=America/Mexico_City:20260831T100000\n"
        "DTEND;TZID=America/Mexico_City:20260831T103000\n"
        "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n",
        encoding="utf-8",
    )
    ics_mod._events_cache = None
    monkeypatch.setattr(ics_mod, "ics_file_path", lambda: ics_path)

    zone = ZoneInfo("America/Mexico_City")
    rows = ics_mod.fetch_ics_events(
        datetime(2026, 8, 31, tzinfo=zone),
        datetime(2026, 9, 6, 23, 59, tzinfo=zone),
        zone,
    )
    paypal_days = {row.start[:10] for row in rows if row.title.startswith("Paypal")}
    tc_days = {row.start[:10] for row in rows if row.title.startswith("TC CEN")}
    assert "2026-09-04" in paypal_days
    assert "2026-09-04" in tc_days
    assert tc_days == {"2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04"}


def test_ics_rrule_fast_forwards_old_daily_series(tmp_path, monkeypatch) -> None:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    import app.services.ics_calendar as ics_mod

    ics_path = tmp_path / "outlook.ics"
    ics_path.write_text(
        "BEGIN:VCALENDAR\n"
        "BEGIN:VEVENT\n"
        "UID:old-daily\n"
        "SUMMARY:Paypal Check (daily)\n"
        "DTSTART;TZID=America/Mexico_City:20260105T093000\n"
        "DTEND;TZID=America/Mexico_City:20260105T100000\n"
        "RRULE:FREQ=DAILY\n"
        "END:VEVENT\n"
        "END:VCALENDAR\n",
        encoding="utf-8",
    )
    ics_mod._events_cache = None
    monkeypatch.setattr(ics_mod, "ics_file_path", lambda: ics_path)

    zone = ZoneInfo("America/Mexico_City")
    rows = ics_mod.fetch_ics_events(
        datetime(2026, 8, 31, tzinfo=zone),
        datetime(2026, 9, 4, 23, 59, tzinfo=zone),
        zone,
    )
    days = {row.start[:10] for row in rows}
    assert "2026-09-04" in days
    assert "2026-08-31" in days

    assert calendar_view_path({"scp": "Calendars.ReadBasic User.Read"}, None) == "/me/calendarView"
    assert (
        calendar_view_path({"idtyp": "app", "roles": ["Calendars.Read"]}, "qc@contoso.com")
        == "/users/qc@contoso.com/calendarView"
    )
