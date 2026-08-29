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
