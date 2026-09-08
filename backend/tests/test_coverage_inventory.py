"""Coverage inventory and LLM covers / coverage-check."""

import json
from unittest.mock import MagicMock, patch

from app.schemas.case_generation import CandidateStep, GeneratedCaseCandidate
from app.services.gherkin_coverage import build_coverage_inventory
from app.services.qc_candidate_rules import apply_qc_rules
from tests.test_case_generation import _gherkin_artifacts


def test_coverage_unit_created_from_gherkin_a() -> None:
    artifacts = _gherkin_artifacts(["WEBCL-3767"])
    units = build_coverage_inventory(artifacts, "rn.pdf")
    assert units
    assert units[0].coverage_id == "COV-001"
    assert units[0].role in {"A", "G"}
    assert units[0].jira_key == "WEBCL-3767"
    assert units[0].scenario
    payload = units[0].for_llm()
    assert "coverage_id" in payload
    assert "body" not in payload


def test_apply_qc_rules_does_not_merge_distinct_covers() -> None:
    left = GeneratedCaseCandidate(
        name="Validar pago exitoso",
        description="A",
        steps=[
            CandidateStep(
                step_number=1,
                action="El usuario confirma el pago",
                expected_result="Ve la confirmación de compra en pantalla",
            )
        ],
        evidence="A",
        justification="A",
        related_jira="WEBCL-1",
        covers=["COV-001"],
    )
    right = GeneratedCaseCandidate(
        name="Validar pago rechazado",
        description="B",
        steps=[
            CandidateStep(
                step_number=1,
                action="El usuario confirma el pago",
                expected_result="Ve el modal de error de saldo insuficiente",
            )
        ],
        evidence="B",
        justification="B",
        related_jira="WEBCL-1",
        covers=["COV-002"],
    )
    merged = apply_qc_rules([left, right])
    assert len(merged) == 2
    assert {tuple(item.covers) for item in merged} == {("COV-001",), ("COV-002",)}


def test_llm_second_batch_only_missing_units(client, monkeypatch, tmp_path) -> None:
    from dataclasses import replace

    from app.config import settings
    from tests.test_case_generation import WEB_RN, _gherkin_artifacts, _store_dir

    _store_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.ai_case_engine.settings",
        replace(settings, openai_api_key="sk-test", openai_model="gpt-4o-mini"),
    )
    monkeypatch.setattr(
        "app.services.ai_case_engine.fetch_artifacts_for_keys",
        lambda _keys: _gherkin_artifacts(["WEBCL-3767", "WEBCL-3762"]),
    )

    def _candidate(name: str, covers: list[str]) -> dict:
        return {
            "name": name,
            "description": name,
            "precondition": None,
            "requires_condition": False,
            "steps": [
                {
                    "step_number": 1,
                    "action": "El usuario recorre el flujo",
                    "expected_result": "Observa el resultado en pantalla",
                }
            ],
            "related_functionality": "WEBCL-3767",
            "related_jira": "WEBCL-3767",
            "related_rn": WEB_RN.name,
            "evidence": name,
            "justification": "LLM",
            "possible_duplicate_of": None,
            "confidence": "high",
            "review_required": True,
            "covers": covers,
        }

    first = MagicMock()
    first.status_code = 200
    first.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"candidates": [_candidate("Uno", ["COV-001"])]})}}]
    }
    second = MagicMock()
    second.status_code = 200
    second.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"candidates": [_candidate("Dos", ["COV-002"])]})}}]
    }
    fake_client = MagicMock()
    fake_client.post.side_effect = [first, second]
    analyzed = client.post(
        "/api/v1/releases/analyze-rn",
        files={"file": (WEB_RN.name, WEB_RN.read_bytes(), "application/pdf")},
    ).json()["analysis"]
    release_id = client.post(
        "/api/v1/releases",
        json={
            "name": "WEB COVERAGE CHECK",
            "version": "16.9.0",
            "platform": "WEB",
            "analysis_data": analyzed,
        },
    ).json()["id"]
    with patch("app.services.ai_case_engine.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = fake_client
        response = client.post(f"/api/v1/releases/{release_id}/generate-cases")
    assert response.status_code == 200
    assert fake_client.post.call_count == 2
    second_payload = json.loads(fake_client.post.call_args_list[1].kwargs["json"]["messages"][1]["content"])
    second_ids = {row["coverage_id"] for row in second_payload["coverage_inventory"]}
    assert "COV-001" not in second_ids
    assert second_ids
    body = response.json()
    covered = set(body["covered_coverage_ids"])
    assert "COV-001" in covered
    assert "COV-002" in covered


def _assert_llm_payload_is_functionality_only(posted: dict) -> None:
    assert "release_note_text" not in posted
    tickets = posted.get("tickets_from_rn") or {}
    assert set(tickets) == {"functionality"}
    assert "nco" not in tickets
    assert "tri" not in tickets
    assert "qa_qc" not in tickets
    assert "coverage_inventory" in posted
    assert "functionality_jira_artifacts" in posted


def test_llm_http_payload_excludes_nco_tri_qa_qc(client, monkeypatch, tmp_path) -> None:
    from dataclasses import replace

    from app.config import settings
    from app.services.ai_case_engine import _ENGINE_RULES
    from tests.test_case_generation import WEB_RN, _gherkin_artifacts, _store_dir

    _store_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.ai_case_engine.settings",
        replace(settings, openai_api_key="sk-test", openai_model="gpt-4o-mini"),
    )
    monkeypatch.setattr(
        "app.services.ai_case_engine.fetch_artifacts_for_keys",
        lambda _keys: _gherkin_artifacts(["WEBCL-3767"]),
    )
    payload = {
        "candidates": [
            {
                "name": "Validar checkout PayPal",
                "description": "Comportamiento de checkout descrito en el RN.",
                "precondition": None,
                "requires_condition": False,
                "steps": [
                    {
                        "step_number": 1,
                        "action": "El usuario recorre el flujo",
                        "expected_result": "Observa el resultado en pantalla",
                    }
                ],
                "related_functionality": "WEBCL-3767",
                "related_jira": "WEBCL-3767",
                "related_rn": WEB_RN.name,
                "evidence": "WEBCL-3767",
                "justification": "LLM",
                "possible_duplicate_of": None,
                "confidence": "high",
                "review_required": True,
                "covers": ["COV-001"],
            }
        ]
    }
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(payload)}}]
    }
    fake_client = MagicMock()
    fake_client.post.return_value = fake_response
    analyzed = client.post(
        "/api/v1/releases/analyze-rn",
        files={"file": (WEB_RN.name, WEB_RN.read_bytes(), "application/pdf")},
    ).json()["analysis"]
    release_id = client.post(
        "/api/v1/releases",
        json={
            "name": "WEB LLM FUNC ONLY",
            "version": "16.9.0",
            "platform": "WEB",
            "analysis_data": analyzed,
        },
    ).json()["id"]
    with patch("app.services.ai_case_engine.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = fake_client
        response = client.post(f"/api/v1/releases/{release_id}/generate-cases")
    assert response.status_code == 200
    posted = json.loads(fake_client.post.call_args.kwargs["json"]["messages"][1]["content"])
    _assert_llm_payload_is_functionality_only(posted)
    system = fake_client.post.call_args.kwargs["json"]["messages"][0]["content"]
    assert "salvo comportamiento funcional nuevo" not in system
    assert "Las únicas fuentes permitidas para generar casos mediante LLM" in _ENGINE_RULES
    assert "Ignora NCO, TRI, QA Bugs y QC Bugs" in _ENGINE_RULES


def test_llm_candidates_keep_only_functionality_jira_and_covers(
    client, monkeypatch, tmp_path
) -> None:
    from dataclasses import replace

    from app.config import settings
    from tests.test_case_generation import WEB_RN, _gherkin_artifacts, _store_dir

    _store_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.ai_case_engine.settings",
        replace(settings, openai_api_key="sk-test", openai_model="gpt-4o-mini"),
    )
    monkeypatch.setattr(
        "app.services.ai_case_engine.fetch_artifacts_for_keys",
        lambda _keys: _gherkin_artifacts(["WEBCL-3767"]),
    )

    def _candidate(name: str, jira: str, covers: list[str]) -> dict:
        return {
            "name": name,
            "description": name,
            "precondition": None,
            "requires_condition": False,
            "steps": [
                {
                    "step_number": 1,
                    "action": "El usuario recorre el flujo",
                    "expected_result": "Observa el resultado en pantalla",
                }
            ],
            "related_functionality": jira,
            "related_jira": jira,
            "related_rn": WEB_RN.name,
            "evidence": name,
            "justification": "LLM",
            "possible_duplicate_of": None,
            "confidence": "high",
            "review_required": True,
            "covers": covers,
        }

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "candidates": [
                                _candidate("Funcional", "WEBCL-3767", ["COV-001"]),
                                _candidate("Bug QA", "QCBG-10", ["COV-001"]),
                                _candidate("NCO leak", "NCO-9", ["COV-001"]),
                            ]
                        }
                    )
                }
            }
        ]
    }
    fake_client = MagicMock()
    fake_client.post.return_value = fake_response
    analyzed = client.post(
        "/api/v1/releases/analyze-rn",
        files={"file": (WEB_RN.name, WEB_RN.read_bytes(), "application/pdf")},
    ).json()["analysis"]
    release_id = client.post(
        "/api/v1/releases",
        json={
            "name": "WEB LLM DROP QA NCO",
            "version": "16.9.0",
            "platform": "WEB",
            "analysis_data": analyzed,
        },
    ).json()["id"]
    with patch("app.services.ai_case_engine.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = fake_client
        response = client.post(f"/api/v1/releases/{release_id}/generate-cases")
    assert response.status_code == 200
    body = response.json()
    llm_rows = [
        row
        for row in body["candidates"]
        if row.get("related_jira") in {"WEBCL-3767", "QCBG-10", "NCO-9"}
    ]
    jiras = {row["related_jira"] for row in llm_rows}
    assert "WEBCL-3767" in jiras
    assert "QCBG-10" not in jiras
    assert "NCO-9" not in jiras
    for row in llm_rows:
        if row["related_jira"] == "WEBCL-3767":
            assert set(row.get("covers") or []).issubset({"COV-001"})
