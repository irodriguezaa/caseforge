"""Incremental generation for a later Nuevo of the same Deliverable."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.services.revalidation_engine import plan_incremental_generation
from tests.test_case_generation import (
    WEB_RN,
    _WEB_FEATURES,
    _create_app_release_from_pdf,
)


def _origin_cases(*keys: str, generated: bool = True) -> list[dict]:
    rows = []
    for index, key in enumerate(keys, start=1):
        rows.append(
            {
                "id": index,
                "test_case_id": f"QC-{index:03d}",
                "test_case_name": f"Validar {key}",
                "description": f"Cobertura de {key}",
                "technical_story": key,
                "technical_epic": key,
                "evidence": key,
                "justification": "",
                "generated_by_engine": generated,
            }
        )
    return rows


def test_plan_skips_functionality_present_in_prior_rn_without_origin_cases() -> None:
    plan = plan_incremental_generation(
        {
            "functionality": [
                ("WEBCL-3721", "WEBCL-3721: Activación HBO"),
                ("WEBCL-3779", "WEBCL-3779: Menú HBO"),
            ],
            "qa_qc": [("WEBCL-3849", "WEBCL-3849: Se muestra parametro de api_version")],
            "nco": [],
        },
        [],
        {
            "WEBCL-3721": "WEBCL-3721: Activación HBO",
            "WEBCL-3779": "WEBCL-3779: Menú HBO",
        },
    )
    assert plan.new_functionality == []
    assert plan.changed_functionality == []
    assert plan.qa_qc == [("WEBCL-3849", "WEBCL-3849: Se muestra parametro de api_version")]
    plan = plan_incremental_generation(
        {
            "functionality": [
                ("FEAT-1", "FEAT-1: Funcionalidad A"),
                ("FEAT-2", "FEAT-2: Funcionalidad B"),
            ],
            "qa_qc": [],
            "nco": [],
        },
        _origin_cases("FEAT-1", "FEAT-2"),
        {"FEAT-1": "FEAT-1: Funcionalidad A", "FEAT-2": "FEAT-2: Funcionalidad B"},
    )
    assert plan.new_functionality == []
    assert plan.changed_functionality == []
    assert any("No se regeneró FEAT-1" in line for line in plan.analysis_details)


def test_plan_generates_new_functionality_key() -> None:
    plan = plan_incremental_generation(
        {
            "functionality": [
                ("FEAT-1", "FEAT-1: Funcionalidad A"),
                ("FEAT-99", "FEAT-99: Nueva pasarela"),
            ],
            "qa_qc": [],
            "nco": [],
        },
        _origin_cases("FEAT-1"),
        {"FEAT-1": "FEAT-1: Funcionalidad A"},
    )
    assert plan.new_functionality == [("FEAT-99", "FEAT-99: Nueva pasarela")]


def test_plan_delta_on_explicit_functional_change() -> None:
    plan = plan_incremental_generation(
        {
            "functionality": [
                ("FEAT-1", "FEAT-1: Ahora el usuario ve un modal distinto al activar"),
            ],
            "qa_qc": [],
            "nco": [],
        },
        _origin_cases("FEAT-1"),
        {"FEAT-1": "FEAT-1: Activación clásica"},
    )
    assert plan.changed_functionality
    assert plan.new_functionality == []


def test_plan_uses_generated_by_engine_baseline_keys() -> None:
    plan = plan_incremental_generation(
        {"functionality": [("FEAT-1", "FEAT-1: A")], "qa_qc": [], "nco": []},
        _origin_cases("FEAT-1", generated=True),
        {"FEAT-1": "FEAT-1: A"},
    )
    assert plan.new_functionality == []


def test_first_nuevo_is_full_and_second_is_delta_only(client, monkeypatch, tmp_path) -> None:
    first_id, analysis = _create_app_release_from_pdf(client, monkeypatch, tmp_path, Path(WEB_RN))
    client.patch(
        f"/api/v1/releases/{first_id}",
        json={"release_type": "NUEVO", "deliverable_name": "WEB incremental test"},
    )
    first = client.post(f"/api/v1/releases/{first_id}/generate-cases").json()
    assert first["engine"] in {"evidence", "evidence-jira", "evidence-fallback"}
    assert len(first["candidates"]) == analysis["features_count"] == 5
    first_ids = {row["test_case_id"] for row in client.get(f"/api/v1/releases/{first_id}/test-cases").json()}

    second = client.post(
        "/api/v1/releases",
        json={
            "name": "WEB incremental v2",
            "version": "16.9.99",
            "platform": "WEB",
            "deliverable_name": "WEB incremental test",
            "release_type": "NUEVO",
            "analysis_data": analysis,
        },
    )
    assert second.status_code == 201, second.text
    generated = client.post(f"/api/v1/releases/{second.json()['id']}/generate-cases").json()
    assert generated["engine"] == "incremental-delta"
    jiras = {row["related_jira"] for row in generated["candidates"]}
    assert jiras.isdisjoint({"WEBCL-3721", "WEBCL-3153", "WEBCL-3779", "WEBCL-3762", "WEBCL-3767"})
    second_cases = client.get(f"/api/v1/releases/{second.json()['id']}/test-cases").json()
    leftover = client.get(f"/api/v1/releases/{first_id}/test-cases").json()
    assert {row["test_case_id"] for row in leftover} == first_ids
    assert all(row.get("related_jira") not in first_ids for row in second_cases)


def test_regenerate_first_release_does_not_treat_self_as_baseline(
    client, monkeypatch, tmp_path
) -> None:
    release_id, analysis = _create_app_release_from_pdf(client, monkeypatch, tmp_path, Path(WEB_RN))
    client.patch(
        f"/api/v1/releases/{release_id}",
        json={"release_type": "NUEVO", "deliverable_name": "WEB self baseline"},
    )
    first = client.post(f"/api/v1/releases/{release_id}/generate-cases").json()
    again = client.post(f"/api/v1/releases/{release_id}/generate-cases?regenerate=true").json()
    assert again["engine"] == first["engine"]
    assert len(again["candidates"]) == analysis["features_count"] == 5


def test_incremental_qa_nco_is_deterministic_and_does_not_call_llm(
    client, monkeypatch, tmp_path
) -> None:
    from dataclasses import replace

    from app.config import settings

    first_id, analysis = _create_app_release_from_pdf(
        client, monkeypatch, tmp_path, Path(WEB_RN)
    )
    client.patch(
        f"/api/v1/releases/{first_id}",
        json={"release_type": "NUEVO", "deliverable_name": "WEB incremental qa nco"},
    )
    first = client.post(f"/api/v1/releases/{first_id}/generate-cases").json()
    assert first["engine"] in {"evidence", "evidence-jira", "evidence-fallback"}

    monkeypatch.setattr(
        "app.services.ai_case_engine.settings",
        replace(settings, openai_api_key="sk-test", openai_model="gpt-4o-mini"),
    )
    tickets = {
        "functionality": [(key, f"{key}: Funcionalidad cubierta") for key in sorted(_WEB_FEATURES)],
        "qa_qc": [
            (
                "QCBG-10",
                "QCBG-10: Se corrigió el listado de reproducción visible al usuario en WEBCL-3767",
            )
        ],
        "nco": [
            (
                "NCO-9",
                "NCO-9: El usuario ya no ve el modal de error al reproducir el contenido lineal tras la corrección.",
            )
        ],
        "tri": [("TRI-1", "TRI-1: hallazgo de laboratorio sin caso QC")],
    }
    monkeypatch.setattr("app.routers.releases._tickets_by_section", lambda _pdf: tickets)
    second = client.post(
        "/api/v1/releases",
        json={
            "name": "WEB incremental qa nco v2",
            "version": "16.9.98",
            "platform": "WEB",
            "deliverable_name": "WEB incremental qa nco",
            "release_type": "NUEVO",
            "analysis_data": analysis,
        },
    )
    assert second.status_code == 201, second.text
    fake_client = MagicMock()
    with patch("app.services.ai_case_engine.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = fake_client
        generated = client.post(f"/api/v1/releases/{second.json()['id']}/generate-cases").json()
    assert fake_client.post.call_count == 0
    assert generated["engine"] == "incremental-delta"
    by_jira = {row["related_jira"]: row for row in generated["candidates"]}
    assert set(by_jira) == {"QCBG-10", "NCO-9"}
    assert by_jira["QCBG-10"]["generation_origin"] == "incremental-qa-qc"
    assert by_jira["NCO-9"]["generation_origin"] == "incremental-nco"
