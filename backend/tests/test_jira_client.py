def test_jira_fields_returns_400_when_not_configured(client) -> None:
    """We have no live Jira to test against in this environment, so this confirms only what we
    can: the app fails safely and clearly when JIRA_* env vars aren't set, instead of crashing
    or silently returning nothing."""
    response = client.get("/api/v1/qc-tickets/jira/fields")
    assert response.status_code == 400
    assert "JIRA_BASE_URL" in response.json()["detail"]


def test_jira_sync_preview_returns_400_when_not_configured(client) -> None:
    response = client.post(
        "/api/v1/qc-tickets/jira/sync-preview",
        params={"filter_id": "112929", "view": "OPERATIVAS", "source": "QC_DETECTED"},
    )
    assert response.status_code == 400
    assert "JIRA_BASE_URL" in response.json()["detail"]


def test_jira_refresh_returns_400_when_not_configured(client) -> None:
    response = client.post("/api/v1/qc-tickets/jira/refresh", params={"view": "OPERATIVAS"})
    assert response.status_code == 400
    assert "JIRA_BASE_URL" in response.json()["detail"]


def test_fetch_tickets_posts_enhanced_search_jql(monkeypatch) -> None:
    """Jira Cloud removed GET /rest/api/3/search (410). Refresh must use POST /rest/api/3/search/jql."""
    from app.models.qc_ticket import QcTicketSource, QcTicketView
    from app.services import jira_client

    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200

        def json(self) -> dict:
            if captured.get("path") == "/rest/api/3/search/jql":
                return {"issues": [], "nextPageToken": None}
            return {"jql": 'project = DEMO AND created >= "2026-01-01"'}

    class _FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, path: str) -> _FakeResponse:
            captured["get_path"] = path
            return _FakeResponse()

        def post(self, path: str, json: dict) -> _FakeResponse:
            captured["path"] = path
            captured["json"] = json
            return _FakeResponse()

    monkeypatch.setattr(jira_client, "_client", lambda: _FakeClient())
    jira_client.fetch_tickets_by_filter("112929", QcTicketView.OPERATIVAS, QcTicketSource.QC_DETECTED)

    assert captured["get_path"] == "/rest/api/3/filter/112929"
    assert captured["path"] == "/rest/api/3/search/jql"
    assert captured["json"]["jql"] == 'project = DEMO AND created >= "2026-01-01"'
    assert "startAt" not in captured["json"]
    assert "nextPageToken" not in captured["json"]


def test_map_issue_uses_csv_closed_status_and_keeps_cancelled_closed() -> None:
    from app.models.qc_ticket import QcTicketSource, QcTicketView
    from app.services.jira_client import _map_issue

    base_fields = {
        "priority": {"name": "Critical"},
        "project": {"key": "WEBCL"},
        "issuetype": {"name": "QC Bug"},
        "created": "2026-08-25T15:45:00.000-0600",
        "summary": "Crash",
    }
    cancelled = _map_issue(
        {"key": "OPE-1", "fields": {**base_fields, "status": {"name": "Cancelada"}}},
        None,
        None,
        QcTicketView.OPERATIVAS,
        QcTicketSource.QC_DETECTED,
    )
    assert cancelled is not None
    assert cancelled.is_open is False
    assert cancelled.status_raw == "Cancelada"

    closed = _map_issue(
        {"key": "OPE-2", "fields": {**base_fields, "status": {"name": "Finalizada"}}},
        None,
        None,
        QcTicketView.OPERATIVAS,
        QcTicketSource.QC_DETECTED,
    )
    assert closed is not None
    assert closed.is_open is False

    roll_out_ope = _map_issue(
        {"key": "OPE-3", "fields": {**base_fields, "status": {"name": "Roll Out"}}},
        None,
        None,
        QcTicketView.OPERATIVAS,
        QcTicketSource.QC_DETECTED,
    )
    assert roll_out_ope is not None
    assert roll_out_ope.is_open is True
