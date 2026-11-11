"""QCO Epic from a release. No live Jira."""

from types import SimpleNamespace

import pytest

from app.services.jira_epic import JiraEpicError, epic_description, epic_summary, program_code, publish_epic
from app.services.jira_epic import EpicDraft


def test_summary_uses_program_version_and_type() -> None:
    assert program_code("WEB", ["WEBCL-12", "WEBCL-13"]) == "WEBCL"
    assert program_code("WEB", []) == "WEBCL"
    assert epic_summary("WEBCL", "16.11.3", "HotFix") == "WEBCL | 16.11.3 | HOTFIX"
    text = epic_description(
        device="WEB",
        version="16.11.3",
        environment="FEHF",
        validation_type="Regresivo",
        rn_filename="RN.pdf",
        functionalities=[("WEBCL-12", "WEBCL-12: Guía")],
        qc_bugs=[],
    )
    assert "Liberar WEB versión 16.11.3 para Claro Video" in text
    assert "Clarovideo WEB." in text
    assert "entorno FEHF." in text
    assert "- WEBCL-12 Guía" in text
    assert "Sin bugs QC en el RN." in text
    assert "Tipo de prueba: Regresivo" in text
    assert "Entorno: FEHF" in text
    assert "RN: RN.pdf" in text


def test_unknown_program_is_rejected() -> None:
    with pytest.raises(JiraEpicError):
        program_code("Kepler", [])


def test_publish_creates_one_epic_and_reuses_it(monkeypatch) -> None:
    draft = EpicDraft(
        release_id=4,
        summary="WEBCL | 16.11.3 | HOTFIX",
        description="Objetivo",
        activity_type="HotFix",
        environment="FEHF",
    )
    store: dict[str, str] = {}

    def search(jql: str):
        if draft.summary in jql and store:
            return [{"key": next(iter(store))}]
        return []

    def create(fields: dict):
        store["QCO-1"] = fields["summary"]
        return "QCO-1"

    monkeypatch.setattr("app.services.jira_epic._search", search)
    monkeypatch.setattr("app.services.jira_epic._create_issue", create)
    monkeypatch.setattr("app.services.jira_epic._account_id", lambda: None)

    first = publish_epic(draft)
    second = publish_epic(draft)

    assert first.already_existed is False
    assert first.key == "QCO-1"
    assert second.already_existed is True
    assert len(store) == 1


def test_route_requires_cases(client) -> None:
    created = client.post(
        "/api/v1/releases",
        json={
            "name": "CV WEB",
            "version": "16.11.3",
            "platform": "WEB",
            "activity_type": "HotFix",
            "environment": "FEHF",
        },
    )
    assert created.status_code == 201
    assert created.json()["activity_type"] == "HotFix"
    assert created.json()["environment"] == "FEHF"

    response = client.post(
        f"/api/v1/releases/{created.json()['id']}/jira-epic",
        json={"activity_type": "HotFix", "environment": "FEHF"},
    )
    assert response.status_code == 400
    assert "casos" in response.json()["detail"]
