"""Authentication and role enforcement."""

from tests.conftest import login_as


def _create_release(client, **overrides):
    payload = {
        "name": "Claro Video",
        "version": "8.15",
        "platform": "tvOS",
        "cluster": "LATAM",
        "description": "Release 8.15 regression cycle",
    }
    payload.update(overrides)
    return client.post("/api/v1/releases", json=payload)


def test_login_sets_httponly_cookie_and_me_returns_role(client) -> None:
    login_as(client, "tester@test.com", "tester-pass")
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json() == {"email": "tester@test.com", "role": "tester"}
    assert "qc_session" in client.cookies


def test_successful_login_is_recorded(client, db_session) -> None:
    from app.models.login_event import LoginEvent

    login_as(client, "tester@test.com", "tester-pass")
    login_as(client, "tester@test.com", "tester-pass")
    rows = db_session.query(LoginEvent).filter(LoginEvent.email == "tester@test.com").all()
    assert len(rows) == 2
    assert rows[0].role == "tester"


def test_failed_login_is_not_recorded(client, db_session) -> None:
    from app.models.login_event import LoginEvent

    before = db_session.query(LoginEvent).count()
    client.cookies.clear()
    client.post("/api/v1/auth/login", json={"email": "jefe@test.com", "password": "wrong"})
    assert db_session.query(LoginEvent).count() == before


def test_login_rejects_bad_password(client) -> None:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "jefe@test.com", "password": "wrong"},
    )
    assert response.status_code == 401


def test_unauthenticated_api_returns_401(client) -> None:
    client.cookies.clear()
    response = client.get("/api/v1/releases")
    assert response.status_code == 401


def test_tester_forbidden_on_delete_status_ics_dashboard_kpis(client) -> None:
    created = _create_release(client)
    assert created.status_code == 201
    release_id = created.json()["id"]

    login_as(client, "tester@test.com", "tester-pass")
    assert client.delete(f"/api/v1/releases/{release_id}").status_code == 403
    assert client.patch(f"/api/v1/releases/{release_id}", json={"status": "IN_PROGRESS"}).status_code == 403
    ics = client.post(
        "/api/v1/calendar/ics",
        files={"file": ("calendar.ics", b"BEGIN:VCALENDAR\nEND:VCALENDAR\n", "text/calendar")},
    )
    assert ics.status_code == 403
    assert client.get("/api/v1/dashboard/qc-summary").status_code == 403
    assert client.get("/api/v1/kpis/releases").status_code == 403
    assert client.get("/api/v1/dashboard/summary").status_code == 403
    assert client.get("/api/v1/calendar/week").status_code == 403
    assert client.get("/api/v1/qc-tickets/stats", params={"view": "OPERATIVAS"}).status_code == 403
    assert client.get("/api/v1/releases").status_code == 200


def test_lider_can_change_status_but_not_delete_or_upload_ics(client) -> None:
    created = _create_release(client)
    release_id = created.json()["id"]

    login_as(client, "lider@test.com", "lider-pass")
    moved = client.patch(f"/api/v1/releases/{release_id}", json={"status": "IN_PROGRESS"})
    assert moved.status_code == 200
    assert moved.json()["status"] == "IN_PROGRESS"
    assert client.delete(f"/api/v1/releases/{release_id}").status_code == 403
    ics = client.post(
        "/api/v1/calendar/ics",
        files={"file": ("calendar.ics", b"BEGIN:VCALENDAR\nEND:VCALENDAR\n", "text/calendar")},
    )
    assert ics.status_code == 403
    assert client.get("/api/v1/dashboard/qc-summary").status_code == 200
    assert client.get("/api/v1/kpis/releases").status_code == 200
    assert client.get("/api/v1/qc-tickets/stats", params={"view": "OPERATIVAS"}).status_code == 200


def test_jefe_can_change_status_delete_and_upload_ics(client, tmp_path, monkeypatch) -> None:
    created = _create_release(client, name="To Delete")
    release_id = created.json()["id"]
    moved = client.patch(f"/api/v1/releases/{release_id}", json={"status": "IN_PROGRESS"})
    assert moved.status_code == 200

    ics_path = tmp_path / "outlook.ics"
    monkeypatch.setattr("app.services.ics_calendar.ics_file_path", lambda: ics_path)
    ics = client.post(
        "/api/v1/calendar/ics",
        files={
            "file": (
                "calendar.ics",
                b"BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:u1\nSUMMARY:QC\n"
                b"DTSTART:20260902T150000Z\nDTEND:20260902T160000Z\nEND:VEVENT\nEND:VCALENDAR\n",
                "text/calendar",
            )
        },
    )
    assert ics.status_code == 200
    assert client.get("/api/v1/dashboard/qc-summary").status_code == 200
    cancelled = client.patch(f"/api/v1/releases/{release_id}", json={"status": "CANCELLED"})
    assert cancelled.status_code == 200

    draft = _create_release(client, name="Draft Delete", version="9.0")
    assert client.delete(f"/api/v1/releases/{draft.json()['id']}").status_code == 204


def test_consulta_reads_dashboard_and_kpis_but_cannot_mutate(client) -> None:
    created = _create_release(client)
    release_id = created.json()["id"]

    login_as(client, "consulta@test.com", "consulta-pass")
    assert client.get("/api/v1/auth/me").json()["role"] == "consulta"
    assert client.get("/api/v1/dashboard/qc-summary").status_code == 200
    assert client.get("/api/v1/kpis/releases").status_code == 200
    assert client.get("/api/v1/calendar/week").status_code == 200
    assert client.get("/api/v1/qc-tickets/stats", params={"view": "OPERATIVAS"}).status_code == 200
    assert client.get("/api/v1/releases").status_code == 403
    assert client.get(f"/api/v1/releases/{release_id}").status_code == 403
    assert client.patch(f"/api/v1/releases/{release_id}", json={"status": "IN_PROGRESS"}).status_code == 403
    assert client.delete(f"/api/v1/releases/{release_id}").status_code == 403
    ics = client.post(
        "/api/v1/calendar/ics",
        files={"file": ("calendar.ics", b"BEGIN:VCALENDAR\nEND:VCALENDAR\n", "text/calendar")},
    )
    assert ics.status_code == 403
    generate = client.post(f"/api/v1/releases/{release_id}/generate-cases")
    assert generate.status_code == 403
