"""Release Apps AI candidate generation. Preview only — does not persist TestCase rows."""

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.config import settings
from app.services.ai_case_engine import _from_evidence
from app.services.operativa_engine.jira_context import BrfContextBundle

WEB_RN = Path(__file__).parent / "fixtures" / "DAMCO-RN-CV_-_WEB_-16.9.0-010926-005137.pdf"
ROKU_RN = Path(__file__).parent / "fixtures" / "DAMCO-RN-_CV_-_Roku_-_V6_0_0-290826-175741.pdf"
AAF_RN = (
    Path(__file__).parent
    / "fixtures"
    / "DAMCO-RN_AAF_OTT_-Nueva_experiencia_para_Activacio_n_de_HBO_Max___Transacciones-290826-175323.pdf"
)
OPE_RN = Path(__file__).parent / "fixtures" / "APMOGH-OPE-AGOSTO-2026-AUP_Release_notes.pdf"

_ROKU_FEATURES = {"ROKUPR-1444", "ROKUPR-1477", "ROKUPR-1513", "ROKUPR-1542"}
_WEB_FEATURES = {"WEBCL-3721", "WEBCL-3153", "WEBCL-3779", "WEBCL-3762", "WEBCL-3767"}
_AAF_FEATURES = {"STVCL-2234", "STVCL-2250"}


def _gherkin_artifacts(keys: list[str] | None = None) -> list[dict]:
    keys = keys or ["WEBCL-3767"]
    artifacts = []
    for key in keys:
        description = (
            f"Feature: {key}\n"
            f"Scenario: Completar el pago de {key}\n"
            "  When el usuario selecciona pagar con PayPal\n"
            "  Then se muestra el modal de confirmación y el usuario ve el resultado\n"
        )
        artifacts.append(
            {
                "key": key,
                "issuetype": "Epic",
                "summary": f"Feature {key}",
                "description": description,
                "acceptance_criteria": "El usuario ve el resultado",
                "children": [
                    {
                        "key": key,
                        "issuetype": "Story",
                        "summary": f"Feature {key}",
                        "description": description,
                        "acceptance_criteria": "El usuario ve el resultado",
                    }
                ],
            }
        )
    return artifacts


def _disable_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.ai_case_engine.settings",
        replace(settings, openai_api_key=""),
    )
    monkeypatch.setattr("app.services.ai_case_engine.fetch_artifacts_for_keys", lambda _keys: [])


def _store_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "app.services.rn_storage.settings",
        replace(settings, rn_storage_dir=str(tmp_path)),
    )


def _create_app_release_from_pdf(client, monkeypatch, tmp_path, pdf_path: Path):
    _disable_llm(monkeypatch)
    _store_dir(monkeypatch, tmp_path)
    analyzed = client.post(
        "/api/v1/releases/analyze-rn",
        files={"file": (pdf_path.name, pdf_path.read_bytes(), "application/pdf")},
    )
    assert analyzed.status_code == 200
    analysis = analyzed.json()["analysis"]
    created = client.post(
        "/api/v1/releases",
        json={
            "name": analysis.get("detected_name") or pdf_path.stem,
            "version": analysis.get("detected_version") or "0.0.0",
            "platform": analysis.get("detected_platform") or "WEB",
            "analysis_data": analysis,
        },
    )
    assert created.status_code == 201
    return created.json()["id"], analysis


def _create_app_release_with_rn(client, monkeypatch, tmp_path):
    return _create_app_release_from_pdf(client, monkeypatch, tmp_path, WEB_RN)


def test_generate_without_analysis_returns_404(client, monkeypatch) -> None:
    _disable_llm(monkeypatch)
    release_id = client.post(
        "/api/v1/releases",
        json={"name": "Claro Video", "version": "8.15", "platform": "tvOS"},
    ).json()["id"]
    response = client.post(f"/api/v1/releases/{release_id}/generate-cases")
    assert response.status_code == 404


def test_generate_rejects_be_release(client, monkeypatch) -> None:
    _disable_llm(monkeypatch)
    draft = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{draft['id']}",
        json={"name": "BE-GEN", "regresivo_scope": "COMPLETO"},
    )
    qc = client.post(f"/api/v1/releases-be/{draft['id']}/create-release").json()
    response = client.post(f"/api/v1/releases/{qc['id']}/generate-cases")
    assert response.status_code == 400
    assert "Release BE" in response.json()["detail"]


def test_generate_operativa_uses_matrix_pipeline(client, monkeypatch) -> None:
    _disable_llm(monkeypatch)
    monkeypatch.setattr(
        "app.services.operativa_engine.coverage_matrix.fetch_brf_context_bundle",
        lambda key: BrfContextBundle(brf_key=key, jira_blob=""),
    )
    analyzed = client.post(
        "/api/v1/operativa/analyze-rn",
        files={"file": (OPE_RN.name, OPE_RN.read_bytes(), "application/pdf")},
    )
    operativa_id = analyzed.json()["operativa_release"]["id"]
    qc = client.post(f"/api/v1/operativa/{operativa_id}/create-release").json()
    response = client.post(f"/api/v1/releases/{qc['id']}/generate-cases")
    assert response.status_code == 200
    body = response.json()
    assert body["engine"] == "operativa-v4.1"
    assert body["brfs_analyzed"] > 0
    # Without HN/CA the generic pipeline does not invent TCs.
    assert body["test_case_count"] == 0
    assert body["persisted"] is False
    second = client.post(f"/api/v1/releases/{qc['id']}/generate-cases").json()
    assert second["already_generated"] is False
    assert second["engine"] == "operativa-v4.1"


def test_analyze_rn_stores_pdf_path(client, monkeypatch, tmp_path) -> None:
    _store_dir(monkeypatch, tmp_path)
    response = client.post(
        "/api/v1/releases/analyze-rn",
        files={"file": (WEB_RN.name, WEB_RN.read_bytes(), "application/pdf")},
    )
    assert response.status_code == 200
    path = response.json()["analysis"]["pdf_file_path"]
    assert path
    assert Path(path).is_file()


def test_generate_from_web_rn_proposes_functionality_candidates_without_persisting(
    client, monkeypatch, tmp_path
) -> None:
    release_id, analysis = _create_app_release_with_rn(client, monkeypatch, tmp_path)
    before = client.get(f"/api/v1/releases/{release_id}/test-cases").json()
    response = client.post(f"/api/v1/releases/{release_id}/generate-cases")
    assert response.status_code == 200
    body = response.json()
    assert body["persisted"] is True
    assert body["has_analysis"] is True
    assert body["engine"] == "evidence"
    assert body["status"] == "PROPOSED"
    assert len(body["candidates"]) == analysis["features_count"] == 5
    assert all(row["basic_validation"] is True for row in body["candidates"])
    jiras = {row["related_jira"] for row in body["candidates"]}
    assert "TBRFRE-2105" not in jiras
    for row in body["candidates"]:
        assert row["name"]
        assert row["description"]
        assert row["steps"]
        assert row["evidence"]
        assert row["justification"]
        assert row["related_rn"]
        assert row["review_required"] is True
        assert row["related_jira"]
    after = client.get(f"/api/v1/releases/{release_id}/test-cases").json()
    assert len(after) == 5
    assert all(row["generated_by_engine"] is True for row in after)
    assert all(row["source_type"] == "functionality" for row in after)
    assert all(row["source_type"] == "functionality" for row in body["candidates"])
    assert body["test_case_count"] == 5
    from app.services.qc_effort import estimate_release

    hours, days = estimate_release(5)
    assert body["estimation_hours"] == hours
    assert body["estimation_days"] == days


def test_generate_does_not_duplicate_when_called_twice(
    client, monkeypatch, tmp_path
) -> None:
    release_id, _analysis = _create_app_release_with_rn(client, monkeypatch, tmp_path)
    first = client.post(f"/api/v1/releases/{release_id}/generate-cases").json()
    assert first["persisted"] is True
    assert first["already_generated"] is False
    listed = client.get(f"/api/v1/releases/{release_id}/test-cases").json()
    assert len(listed) == 5
    second = client.post(f"/api/v1/releases/{release_id}/generate-cases").json()
    assert second["already_generated"] is True
    assert second["test_case_count"] == 5
    listed_again = client.get(f"/api/v1/releases/{release_id}/test-cases").json()
    assert len(listed_again) == 5
    assert {row["test_case_id"] for row in listed} == {row["test_case_id"] for row in listed_again}


def test_generate_without_stored_pdf_does_not_invent_cases(client, monkeypatch) -> None:
    _disable_llm(monkeypatch)
    created = client.post(
        "/api/v1/releases",
        json={
            "name": "Claro Video",
            "version": "16.9.0",
            "platform": "WEB",
            "analysis_data": {
                "pdf_filename": "missing.pdf",
                "features_count": 5,
                "qa_qc_issues_count": 0,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    )
    response = client.post(f"/api/v1/releases/{created.json()['id']}/generate-cases")
    assert response.status_code == 200
    body = response.json()
    assert body["candidates"] == []
    assert body["persisted"] is False
    assert body["status"] == "EMPTY"


def test_llm_structured_payload_is_returned(client, monkeypatch, tmp_path) -> None:
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
                        "action": "Completar el flujo PayPal descrito en el RN.",
                        "expected_result": "El pago se confirma según el RN.",
                    }
                ],
                "related_functionality": "WEBCL-3767",
                "related_jira": "WEBCL-3767",
                "related_rn": WEB_RN.name,
                "evidence": "WEBCL-3767: Integración PayPal",
                "justification": "Ticket de Funcionalidad en el RN.",
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
            "name": "WEB",
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
    assert body["engine"] == "llm"
    assert body["persisted"] is True
    assert len(body["candidates"]) == 1
    assert body["candidates"][0]["related_jira"] == "WEBCL-3767"
    assert body["candidates"][0]["covers"] == ["COV-001"]
    assert body["coverage_unit_count"] >= 1
    posted = json.loads(fake_client.post.call_args.kwargs["json"]["messages"][1]["content"])
    assert "coverage_inventory" in posted
    assert posted["coverage_inventory"]
    assert "coverage_id" in posted["coverage_inventory"][0]
    stored = client.get(f"/api/v1/releases/{release_id}/test-cases").json()
    assert len(stored) == 1
    assert stored[0]["test_case_name"] == "Validar checkout PayPal"


def test_llm_logs_attempt_and_success_without_leaking_api_key(
    client, monkeypatch, tmp_path, caplog
) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="app.services.ai_case_engine")
    secret = "sk-secret-must-not-appear-xyz"
    _store_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.ai_case_engine.settings",
        replace(settings, openai_api_key=secret, openai_model="gpt-4o-mini"),
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
                        "action": "Completar el flujo PayPal descrito en el RN.",
                        "expected_result": "El pago se confirma según el RN.",
                    }
                ],
                "related_functionality": "WEBCL-3767",
                "related_jira": "WEBCL-3767",
                "related_rn": WEB_RN.name,
                "evidence": "WEBCL-3767: Integración PayPal",
                "justification": "Ticket de Funcionalidad en el RN.",
                "possible_duplicate_of": None,
                "confidence": "high",
                "review_required": True,
                "covers": ["COV-001"],
            }
        ]
    }
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.text = f"ok {secret}"
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
            "name": "WEB LLM LOG",
            "version": "16.9.0",
            "platform": "WEB",
            "analysis_data": analyzed,
        },
    ).json()["id"]
    with patch("app.services.ai_case_engine.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = fake_client
        response = client.post(f"/api/v1/releases/{release_id}/generate-cases")
    assert response.status_code == 200
    assert response.json()["engine"] == "llm"
    messages = [record.getMessage() for record in caplog.records]
    blob = "\n".join(messages)
    assert any("LLM attempt" in msg and "gpt-4o-mini" in msg for msg in messages)
    assert any("LLM responded correctly" in msg and "candidates=1" in msg for msg in messages)
    assert secret not in blob
    assert "Bearer sk-" not in blob


def test_llm_error_logs_fallback_without_leaking_api_key(
    client, monkeypatch, tmp_path, caplog
) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="app.services.ai_case_engine")
    secret = "sk-secret-must-not-appear-xyz"
    _store_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.ai_case_engine.settings",
        replace(settings, openai_api_key=secret, openai_model="gpt-4o-mini"),
    )
    monkeypatch.setattr(
        "app.services.ai_case_engine.fetch_artifacts_for_keys",
        lambda _keys: _gherkin_artifacts(["WEBCL-3767"]),
    )
    fake_response = MagicMock()
    fake_response.status_code = 401
    fake_response.text = f"Unauthorized token {secret}"
    fake_client = MagicMock()
    fake_client.post.return_value = fake_response
    analyzed = client.post(
        "/api/v1/releases/analyze-rn",
        files={"file": (WEB_RN.name, WEB_RN.read_bytes(), "application/pdf")},
    ).json()["analysis"]
    release_id = client.post(
        "/api/v1/releases",
        json={
            "name": "WEB LLM FAIL",
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
    assert body["engine"] in {"evidence", "evidence-fallback", "evidence-jira"}
    assert body["engine"] != "llm"
    messages = [record.getMessage() for record in caplog.records]
    blob = "\n".join(messages)
    assert any("LLM attempt" in msg for msg in messages)
    assert any("LLM HTTP error" in msg and "401" in msg for msg in messages)
    assert any("LLM call failed" in msg and "RuntimeError" in msg for msg in messages)
    assert any("LLM fallback activated" in msg for msg in messages)
    assert secret not in blob
    assert "Bearer sk-" not in blob


def test_evidence_fallback_skips_untracked_alcance_tickets() -> None:
    candidates = _from_evidence(WEB_RN.read_bytes(), WEB_RN.name, [])
    assert len(candidates) == 5
    assert all(row.related_jira != "TBRFRE-2105" for row in candidates)
    assert all(row.basic_validation is True for row in candidates)


def test_shared_walk_roku_web_aaf_functionality_matches_analyzer() -> None:
    from app.services.ai_case_engine import _tickets_by_section
    from app.services.release_note_analyzer import RuleBasedPdfAnalyzer

    samples = (
        (ROKU_RN, _ROKU_FEATURES),
        (WEB_RN, _WEB_FEATURES),
        (AAF_RN, _AAF_FEATURES),
    )
    for path, expected in samples:
        pdf = path.read_bytes()
        analysis = RuleBasedPdfAnalyzer().analyze(path.name, pdf)
        buckets = _tickets_by_section(pdf)
        keys = {ticket_id for ticket_id, _text in buckets["functionality"]}
        assert keys == expected, path.name
        assert analysis.features_count == len(expected), path.name
        qa_qc = {ticket_id for ticket_id, _text in buckets["qa_qc"]}
        assert expected.isdisjoint(qa_qc), path.name


def test_generate_roku_web_aaf_proposes_functionality_candidates(
    client, monkeypatch, tmp_path
) -> None:
    samples = (
        (ROKU_RN, _ROKU_FEATURES),
        (WEB_RN, _WEB_FEATURES),
        (AAF_RN, _AAF_FEATURES),
    )
    for path, expected in samples:
        release_id, analysis = _create_app_release_from_pdf(client, monkeypatch, tmp_path, path)
        assert analysis["features_count"] == len(expected)
        response = client.post(f"/api/v1/releases/{release_id}/generate-cases")
        assert response.status_code == 200, path.name
        body = response.json()
        assert body["persisted"] is True
        assert body["status"] == "PROPOSED"
        assert len(body["candidates"]) >= len(expected)
        jiras = {row["related_jira"] for row in body["candidates"]}
        assert expected <= jiras, path.name
        listed = client.get(f"/api/v1/releases/{release_id}/test-cases").json()
        assert len(listed) == len(body["candidates"])


_TWO_SCENARIOS = """
Scenario: Activar add-on desde Home
  When el usuario abre la Home
  Then ve el banner de activación en Superdestacados
Scenario: Activar add-on desde Configuraciones
  When el usuario abre Configuraciones
  Then ve la opción de activar el add-on
"""

_HTTP_OUTLINE = """
Scenario Outline: No mostrar el componente ante error de comunicación
  When el usuario abre la Home
  Then no se muestra el componente
  Examples:
    | code |
    | 400 |
    | 401 |
    | 404 |
    | 429 |
    | 500 |
    | 503 |
"""

_PLAN_OUTLINE = """
Scenario Outline: Activar add-on contratado
  When el usuario inicia la activación
  Then ve el flujo del add-on contratado
  Examples:
    | plan |
    | HBO Max |
    | Paramount |
"""


def test_gherkin_http_outline_groups_same_user_behavior() -> None:
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    artifacts = [
        {
            "key": "STVCL-2234",
            "issuetype": "Technical Epic",
            "children": [
                {
                    "key": "STVCL-9001",
                    "summary": "Feature banner",
                    "description": _HTTP_OUTLINE,
                    "acceptance_criteria": "Banner Superdestacado",
                }
            ],
        }
    ]
    candidates = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda _n, _j, _e: None)
    assert len(candidates) == 1
    assert "400" in (candidates[0].test_data or "")
    assert "503" in (candidates[0].test_data or "")
    assert all("GET" not in step.action and "POST" not in step.action for step in candidates[0].steps)


def test_gherkin_independent_examples_are_materialized() -> None:
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    artifacts = [
        {
            "key": "WEBCL-3779",
            "issuetype": "Technical Epic",
            "children": [
                {
                    "key": "WEBCL-9002",
                    "summary": "Feature add-on",
                    "description": _PLAN_OUTLINE,
                    "acceptance_criteria": "Activación de add-on",
                }
            ],
        }
    ]
    candidates = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda _n, _j, _e: None)
    assert len(candidates) == 2
    names = " ".join(row.name for row in candidates)
    assert "HBO Max" in names
    assert "Paramount" in names


def test_gherkin_quality_appendix_is_not_materialized() -> None:
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    description = """
Scenario: Usuario ve el banner
  When el usuario abre la Home
  Then ve el banner de activación
10. 📐 Criterios de calidad y prueba Esta sección define los criterios mínimos
Scenario: CF-01 no es un caso QC
  When alguien lee el apéndice
  Then no debe generar este caso
"""
    artifacts = [
        {
            "key": "WEBCL-3721",
            "children": [{"key": "WEBCL-3721", "description": description, "acceptance_criteria": ""}],
        }
    ]
    candidates = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda _n, _j, _e: None)
    assert len(candidates) == 1
    assert "banner" in candidates[0].name.lower()


def test_gherkin_origin_examples_group_same_user_behavior() -> None:
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    description = """
Scenario Outline: El sistema dispara la consulta de estado desde puntos de entrada elegibles
  When el usuario navega al punto de entrada
  Then no se bloquea la experiencia y el flujo de activación puede continuar
  Examples:
    | origen |
    | Banner Superdestacado |
    | Tarjeta de carrusel |
    | Buscador |
"""
    artifacts = [
        {
            "key": "WEBCL-3723",
            "children": [{"key": "WEBCL-3723", "description": description, "acceptance_criteria": ""}],
        }
    ]
    candidates = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda _n, _j, _e: None)
    assert len(candidates) == 1
    assert "Banner Superdestacado" in (candidates[0].test_data or "")
    assert "Buscador" in (candidates[0].test_data or "")
    assert candidates[0].priority in {"BLOCKER", "CRITICAL"}


def test_gherkin_visibility_outline_groups_by_observable_outcome() -> None:
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    description = """
Scenario Outline: Visibilidad del ítem Activar HBO Max
  When el usuario abre Configuraciones
  Then el ítem <visibilidad>
  Examples:
    | perfil | suscripto_hbo | visibilidad |
    | Administrador | true | se muestra |
    | Administrador | false | no se muestra |
    | Miembro | true | no se muestra |
"""
    artifacts = [
        {
            "key": "WEBCL-3779",
            "children": [{"key": "WEBCL-3785", "description": description, "acceptance_criteria": ""}],
        }
    ]
    candidates = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda _n, _j, _e: None)
    assert len(candidates) == 2
    blob = " ".join(row.name.lower() + (row.test_data or "") for row in candidates)
    assert "se muestra" in blob
    assert "no se muestra" in blob


def test_gherkin_metrics_and_qa_process_scenarios_are_excluded() -> None:
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    description = """
Scenario: El usuario completa la transacción con PayPal
  When el usuario selecciona PayPal
  Then completa el pago y permanece en Claro video
Scenario: Se registra evento de analítica cuando la activación redirige correctamente
  When el frontend dispara payment_method_selected
  Then el evento se transmite al pipeline DAT
Scenario: Desviación de nomenclatura detectada en QA se reporta antes del despliegue
  When QA detecta la desviación
  Then se reporta y se habilita el despliegue
Scenario: Fallo de transmisión del evento hacia el servicio de analítica no bloquea el flujo de pago
  When falla la analítica
  Then el usuario puede completar el pago y no se bloquea
"""
    artifacts = [
        {
            "key": "WEBCL-3767",
            "children": [{"key": "WEBCL-3768", "description": description, "acceptance_criteria": ""}],
        }
    ]
    candidates = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda _n, _j, _e: None)
    names = " | ".join(row.name for row in candidates)
    assert "PayPal" in names
    assert "nomenclatura" not in names.lower()
    assert "pipeline DAT" not in names
    assert any("no bloquea" in row.name.lower() or "pago" in row.name.lower() for row in candidates)
    assert all(row.priority for row in candidates)


def test_gherkin_steps_move_http_verbs_to_test_data() -> None:
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    description = """
Scenario: Home muestra banner
  When el FE solicita GET /services/cms/v2/level
  Then el servicio responde y el usuario ve el banner
"""
    artifacts = [
        {
            "key": "WEBCL-3785",
            "children": [{"key": "WEBCL-3785", "description": description, "acceptance_criteria": ""}],
        }
    ]
    candidates = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda _n, _j, _e: None)
    assert len(candidates) == 1
    assert "GET" not in candidates[0].steps[0].action
    assert "/services/" not in candidates[0].steps[0].action
    assert "GET" in (candidates[0].test_data or candidates[0].steps[0].test_data or "")


def test_generate_expands_jira_gherkin_coverage(client, monkeypatch, tmp_path) -> None:
    _store_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "app.services.ai_case_engine.settings",
        replace(settings, openai_api_key=""),
    )

    def fake_fetch(keys: list[str]) -> list[dict]:
        return [
            {
                "key": key,
                "issuetype": "Technical Epic",
                "summary": key,
                "description": "",
                "acceptance_criteria": "Banner Superdestacado",
                "children": [
                    {
                        "key": f"{key}-F1",
                        "summary": "Feature flow",
                        "description": _TWO_SCENARIOS,
                        "acceptance_criteria": "Banner Superdestacado",
                    }
                ],
            }
            for key in keys
        ]

    monkeypatch.setattr("app.services.ai_case_engine.fetch_artifacts_for_keys", fake_fetch)
    release_id, analysis = _create_app_release_with_rn(client, monkeypatch, tmp_path)
    # _create_app_release_with_rn also stubs fetch to []; re-apply expansion stub.
    monkeypatch.setattr("app.services.ai_case_engine.fetch_artifacts_for_keys", fake_fetch)
    response = client.post(f"/api/v1/releases/{release_id}/generate-cases")
    body = response.json()
    assert response.status_code == 200
    assert body["engine"] == "evidence-jira"
    assert body["persisted"] is True
    functional = [row for row in body["candidates"] if not row["basic_validation"]]
    assert len(functional) == 2
    joined = " ".join(row["name"].lower() for row in functional)
    assert "banner" in joined or "home" in joined
    assert "configur" in joined or "add-on" in joined or "activar" in joined
    assert all(row["basic_validation"] is False for row in functional)
    stored = client.get(f"/api/v1/releases/{release_id}/test-cases").json()
    assert len(stored) == len(body["candidates"])
    assert all(row["generated_by_engine"] is True for row in stored)


def test_internal_then_is_translated_to_observable_result() -> None:
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    description = """
Scenario: El flag deshabilitado impide toda consulta de activación
  When el usuario entra a la experiencia
  Then el sistema no realiza la consulta de estado de activación
Scenario: El usuario activa su cuenta desde el Modal inicial
  When el usuario selecciona Activar ahora
  Then el sistema ejecuta el servicio /oauth/external con una clave de idempotencia única
"""
    artifacts = [
        {
            "key": "WEBCL-3721",
            "children": [{"key": "WEBCL-3722", "description": description, "acceptance_criteria": ""}],
        }
    ]
    candidates = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda _n, _j, _e: None)
    assert len(candidates) == 2
    joined_expected = " ".join(step.expected_result for row in candidates for step in row.steps)
    joined_names = " ".join(row.name for row in candidates)
    assert "consulta de estado" not in joined_expected.lower() or "usuario" in joined_expected.lower()
    assert "/oauth/external" not in joined_expected
    assert any("oauth" in (row.test_data or "").lower() for row in candidates)
    assert "no visualiza opciones de activación" in joined_names.lower() + joined_expected.lower()
    assert "experiencia de activación" in joined_expected.lower()
    for row in candidates:
        assert all("el sistema consulta" not in step.expected_result.lower() for step in row.steps)


def test_wcag_audit_only_is_not_a_qc_case() -> None:
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    description = """
Scenario: El usuario visualiza el Modal inicial de activación
  When el usuario abre la Home
  Then ve el Modal inicial
Scenario: El Modal inicial cumple los criterios de accesibilidad WCAG 2.1 AA
  When el sistema renderiza el Modal
  Then el sistema expone roles y etiquetas ARIA equivalentes al contenido visible
"""
    artifacts = [
        {
            "key": "WEBCL-3726",
            "children": [{"key": "WEBCL-3726", "description": description, "acceptance_criteria": ""}],
        }
    ]
    candidates = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda _n, _j, _e: None)
    names = " ".join(row.name for row in candidates).lower()
    assert "wcag" not in names
    assert "aria" not in names
    assert any("modal" in row.name.lower() for row in candidates)


def test_analytics_failure_keeps_functional_consequence() -> None:
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    description = """
Scenario: Fallo de transmisión del evento hacia el servicio de analítica no bloquea el flujo de pago
  When el envío del evento hacia el servicio de analítica de DAT falla por timeout de red
  Then el sistema registra el fallo de envío en el log de observabilidad del cliente
"""
    artifacts = [
        {
            "key": "WEBCL-3767",
            "children": [{"key": "WEBCL-3768", "description": description, "acceptance_criteria": ""}],
        }
    ]
    candidates = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda _n, _j, _e: None)
    assert len(candidates) == 1
    expected = candidates[0].steps[0].expected_result.lower()
    assert "log" not in expected
    assert "no se bloquea" in expected or "completar el pago" in expected
    assert candidates[0].steps[0].action.lower().startswith("el usuario")


def test_implementation_asset_scenarios_are_not_materialized() -> None:
    from app.schemas.case_generation import GenerationStats
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    description = """
Scenario: El banner se muestra en la Home de inicio
  When el usuario abre la Home
  Then el banner se muestra
Scenario: Extraer URL del asset webm VP9
  When el servicio responde con un asset válido
  Then se extrae la URL del asset webm VP9
Scenario: El archivo persistido coincide con el del servicio
  When termina la descarga en hilo de background
  Then el archivo del servicio coincide con el archivo persistido localmente
Scenario: Envio de metrica de visualizacion DAT V3
  When se visualiza el banner
  Then se envía la métrica DAT V3 al pipeline
Scenario: El PNG debe estar en espacio de color sRGB
  When se publica el asset
  Then el PNG está en sRGB sin interlazado ni antialias
"""
    stats = GenerationStats()
    artifacts = [
        {
            "key": "ANDCL-100",
            "children": [{"key": "ANDCL-101", "description": description, "acceptance_criteria": "Banner Home"}],
        }
    ]
    candidates = candidates_from_jira_artifacts(
        artifacts, "rn.pdf", [], lambda _n, _j, _e: None, stats=stats
    )
    names = " | ".join(row.name.lower() for row in candidates)
    expected = " ".join(step.expected_result.lower() for row in candidates for step in row.steps)
    assert len(candidates) == 1
    assert "banner" in names
    assert "vp9" not in names and "vp9" not in expected
    assert "srgb" not in names
    assert "pipeline" not in names
    assert stats.discarded_c >= 2
    assert stats.discarded_d >= 1
    assert any("vp9" in (row.test_data or "").lower() for row in candidates)


def test_module_version_is_not_the_expected_result() -> None:
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    description = """
Scenario: El usuario ve el ítem Activar HBO Max
  When el usuario abre Configuraciones
  Then ve el ítem Activar HBO Max
Scenario: La aplicación utiliza v8 en la llamada
  When la aplicación consulta el estado
  Then la aplicación utiliza module_version=v8 en la llamada al endpoint
"""
    artifacts = [
        {
            "key": "STVCL-2234",
            "children": [{"key": "STVCL-2235", "description": description, "acceptance_criteria": ""}],
        }
    ]
    candidates = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda _n, _j, _e: None)
    assert len(candidates) == 1
    expected = candidates[0].steps[0].expected_result.lower()
    assert "v8" not in expected
    assert "endpoint" not in expected
    assert "ítem" in expected or "item" in expected or "hbo" in expected
    assert "v8" in (candidates[0].test_data or "").lower() or "module_version" in (
        candidates[0].test_data or ""
    )


def test_does_not_invent_generic_observable_result() -> None:
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    description = """
Scenario: Cache interna del estado de cuenta
  When el backend responde
  Then la cache interna no sobrevive un reinicio
"""
    artifacts = [
        {
            "key": "STVCL-1",
            "children": [{"key": "STVCL-2", "description": description, "acceptance_criteria": ""}],
        }
    ]
    candidates = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda _n, _j, _e: None)
    assert candidates == []
    assert all(
        "observa el resultado en la interfaz" not in (step.expected_result or "").lower()
        for row in candidates
        for step in row.steps
    )


def test_cross_story_same_observable_is_consolidated() -> None:
    from app.schemas.case_generation import GenerationStats
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    story = """
Scenario: El partido finaliza y se muestra el marcador
  When el usuario está en la tarjeta del partido
  Then el usuario ve el marcador final del partido
"""
    stats = GenerationStats()
    artifacts = [
        {
            "key": "AAF-1",
            "children": [
                {"key": "AAF-10", "description": story, "acceptance_criteria": ""},
                {"key": "AAF-11", "description": story, "acceptance_criteria": ""},
            ],
        }
    ]
    candidates = candidates_from_jira_artifacts(
        artifacts, "rn.pdf", [], lambda _n, _j, _e: None, stats=stats
    )
    assert len(candidates) == 1
    assert "AAF-10" in (candidates[0].related_jira or "")
    assert "AAF-11" in (candidates[0].related_jira or "")
    assert stats.consolidated_functional >= 1


def test_title_is_aligned_when_polarity_contradicts_expected() -> None:
    from app.services.qc_candidate_rules import align_title_with_flow
    from app.schemas.case_generation import CandidateStep

    steps = [
        CandidateStep(
            step_number=1,
            action="El usuario permanece en la pantalla.",
            expected_result="El usuario deja de visualizar el Modal.",
        )
    ]
    aligned = align_title_with_flow("El Modal se muestra al usuario.", steps)
    assert "deja de visualizar" in aligned.lower() or "modal" in aligned.lower()
    assert "se muestra" not in aligned.lower() or "deja de" in aligned.lower()


def test_config_scenario_becomes_condition_not_testcase() -> None:
    from app.schemas.case_generation import GenerationStats
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    description = """
Scenario: Live Feed muestra el marcador en la tarjeta
  When el usuario abre la tarjeta del partido
  Then visualiza el marcador en vivo
Scenario: Obtención de configuración por región
  Given la configuración remota de la operación
  When el backend devuelve el intervalo de polling
  Then se obtiene la configuración por región
"""
    stats = GenerationStats()
    artifacts = [
        {
            "key": "AAF-20",
            "children": [{"key": "AAF-21", "description": description, "acceptance_criteria": ""}],
        }
    ]
    candidates = candidates_from_jira_artifacts(
        artifacts, "rn.pdf", [], lambda _n, _j, _e: None, stats=stats
    )
    names = " ".join(row.name.lower() for row in candidates)
    assert "marcador" in names
    assert "polling" not in names
    assert stats.converted_b >= 1
    assert any(row.requires_condition for row in candidates)
def test_live_feed_goal_is_not_classified_as_implementation() -> None:
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    description = """
Scenario: Se anota un gol y la tarjeta actualiza el marcador
  When el sistema recibe el evento de gol por polling
  Then la tarjeta actualiza el marcador
Scenario: El usuario sale de la pantalla mientras el partido está en curso
  When el usuario navega fuera de la tarjeta
  Then deja de ver actualizaciones del partido en esa pantalla
Scenario: Obtención de configuración por región
  When el backend devuelve la configuración remota
  Then se obtiene la configuración por región
"""
    artifacts = [
        {
            "key": "AAF-30",
            "children": [{"key": "AAF-31", "description": description, "acceptance_criteria": ""}],
        }
    ]
    candidates = candidates_from_jira_artifacts(artifacts, "rn.pdf", [], lambda _n, _j, _e: None)
    names = " ".join(row.name.lower() for row in candidates)
    assert "marcador" in names
    assert "pantalla" in names or "actualizaciones" in names
    assert "obtención de configuración" not in names
    assert len(candidates) >= 2


def test_qc_effort_uses_homologated_release_formula() -> None:
    from app.services.qc_effort import estimate_release, estimate_release_raw

    expected = {
        10: (0.65, 3.9),
        12: (0.78, 4.7),
        50: (3.26, 19.6),
        61: (3.98, 23.9),
        100: (6.52, 39.1),
    }
    for count, (days_2dp, hours_1dp) in expected.items():
        raw_hours, raw_days = estimate_release_raw(count)
        assert round(raw_days, 2) == days_2dp
        assert round(raw_hours, 1) == hours_1dp
        hours, days = estimate_release(count)
        assert hours == hours_1dp
        assert days == round(raw_days, 1)

    hours_61, days_61 = estimate_release(61)
    assert hours_61 == 23.9
    assert days_61 == 4.0
    assert estimate_release(0) == (0.0, 0.0)


def test_export_excel_has_qc_and_zephyr_sheets(client, monkeypatch, tmp_path) -> None:
    import io

    from openpyxl import load_workbook

    release_id, _analysis = _create_app_release_with_rn(client, monkeypatch, tmp_path)
    generated = client.post(f"/api/v1/releases/{release_id}/generate-cases")
    assert generated.status_code == 200
    exported = client.get(f"/api/v1/releases/{release_id}/test-cases/export")
    assert exported.status_code == 200
    workbook = load_workbook(io.BytesIO(exported.content))
    assert workbook.sheetnames == ["Test Cases", "Zephyr"]
    qc = workbook["Test Cases"]
    zephyr = workbook["Zephyr"]
    assert qc["A1"].value == "ID"
    assert zephyr["A1"].value == "Test Case ID"
    assert zephyr["F1"].value == "Step"
    assert zephyr["G1"].value == "Test Step"
    assert zephyr["H1"].value == "Expected Result"
    stored = client.get(f"/api/v1/releases/{release_id}/test-cases").json()
    assert qc.max_row == len(stored) + 1
    assert zephyr.max_row >= len(stored) + 1
    first_id = stored[0]["test_case_id"]
    zephyr_ids = [zephyr.cell(row, 1).value for row in range(2, zephyr.max_row + 1)]
    assert first_id in zephyr_ids
    assert all(zephyr.cell(row, 7).value for row in range(2, zephyr.max_row + 1))
    assert all(zephyr.cell(row, 8).value for row in range(2, zephyr.max_row + 1))


def test_regenerate_replaces_only_engine_cases(client, monkeypatch, tmp_path) -> None:
    release_id, _analysis = _create_app_release_with_rn(client, monkeypatch, tmp_path)
    client.post(
        f"/api/v1/releases/{release_id}/test-cases",
        json={
            "test_case_id": "MAN-001",
            "component": "WEB",
            "test_case_name": "Caso manual",
            "priority": "CRITICAL",
            "test_type": "FUNCTIONAL",
        },
    )
    client.post(f"/api/v1/releases/{release_id}/generate-cases")
    listed = client.get(f"/api/v1/releases/{release_id}/test-cases").json()
    assert any(row["test_case_id"] == "MAN-001" for row in listed)
    engine_ids = {row["test_case_id"] for row in listed if row["generated_by_engine"]}
    client.post(f"/api/v1/releases/{release_id}/generate-cases?regenerate=true")
    again = client.get(f"/api/v1/releases/{release_id}/test-cases").json()
    assert any(row["test_case_id"] == "MAN-001" for row in again)
    new_engine = {row["test_case_id"] for row in again if row["generated_by_engine"]}
    assert engine_ids
    assert new_engine
    assert "MAN-001" not in new_engine



