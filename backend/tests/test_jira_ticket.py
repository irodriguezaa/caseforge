from app.services.jira_ticket import normalize_jira_tickets


def test_normalize_extracts_keys_from_url_and_plain_text() -> None:
    assert normalize_jira_tickets("  ") is None
    assert (
        normalize_jira_tickets("https://dlatvarg.atlassian.net/browse/WEBCL-123")
        == "WEBCL-123"
    )
    assert normalize_jira_tickets("webcl-1, WEBCL-1 y AAFCL-9") == "WEBCL-1 | AAFCL-9"
    assert normalize_jira_tickets("sin clave") == "sin clave"
