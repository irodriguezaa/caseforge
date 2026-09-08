"""Revalidación delta generation for Release Apps."""

from app.services.revalidation_engine import generate_revalidation_candidates, nco_has_validation_evidence


def _origin_cases(*keys: str) -> list[dict]:
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
            }
        )
    return rows


def _run(tickets: dict, origin_cases: list[dict] | None = None):
    return generate_revalidation_candidates(
        release_id=2,
        release_name="RN reval",
        validation_type="Completo",
        rn_filename="rn.pdf",
        pdf_bytes=b"%PDF",
        origin_release_id=1,
        origin_release_name="RN origen v1.0.0",
        origin_cases=origin_cases if origin_cases is not None else _origin_cases("FEAT-1", "FEAT-2", "FEAT-3"),
        tickets=tickets,
    )


def test_identical_functionality_in_origin_rn_is_not_regenerated_without_origin_cases() -> None:
    result = generate_revalidation_candidates(
        release_id=2,
        release_name="16.9.2",
        validation_type="Completo",
        rn_filename="16.9.2.pdf",
        pdf_bytes=b"%PDF",
        origin_release_id=1,
        origin_release_name="16.9.1",
        origin_cases=[],
        tickets={
            "functionality": [
                ("WEBCL-3721", "WEBCL-3721: Activación HBO Max"),
                ("WEBCL-3779", "WEBCL-3779: Menú de configuración"),
                ("WEBCL-3762", "WEBCL-3762: URL handler"),
                ("WEBCL-3767", "WEBCL-3767: PayPal métricas"),
            ],
            "qa_qc": [
                ("WEBCL-3849", "WEBCL-3849: En API de HBO se muestra parametro de api_version"),
                ("WEBCL-3874", "WEBCL-3874: Se hace 2 veces el llamado"),
                ("WEBCL-3878", "WEBCL-3878: No respeta configuración default"),
                ("WEBCL-3886", "WEBCL-3886: No se vuelve a mostrar modal"),
                ("WEBCL-3900", "WEBCL-3900: Error 404 al no tener región"),
                ("WEBCL-3898", "WEBCL-3898: Falta parametro de region"),
                ("WEBCL-3902", "WEBCL-3902: Landings se quedan en spinner"),
                ("WEBCL-3904", "WEBCL-3904: QR de activación no manda donde debería"),
            ],
            "nco": [],
        },
        prior_functionality_cells={
            "WEBCL-3721": "WEBCL-3721: Activación HBO Max",
            "WEBCL-3779": "WEBCL-3779: Menú de configuración",
            "WEBCL-3762": "WEBCL-3762: URL handler",
            "WEBCL-3767": "WEBCL-3767: PayPal métricas",
        },
    )
    jiras = {row.related_jira for row in result.candidates}
    assert len(result.candidates) == 8
    assert jiras == {
        "WEBCL-3849",
        "WEBCL-3874",
        "WEBCL-3878",
        "WEBCL-3886",
        "WEBCL-3900",
        "WEBCL-3898",
        "WEBCL-3902",
        "WEBCL-3904",
    }
    assert "WEBCL-3721" not in jiras
    result = _run(
        {
            "functionality": [
                ("FEAT-1", "FEAT-1: Funcionalidad A"),
                ("FEAT-2", "FEAT-2: Funcionalidad B"),
                ("FEAT-3", "FEAT-3: Funcionalidad C"),
            ],
            "qa_qc": [],
            "nco": [],
        }
    )
    assert result.engine == "revalidation-delta"
    assert result.candidates == []
    assert any("FEAT-1" in line for line in result.analysis_details)


def test_qc_bug_generates_fix_coverage_not_full_feature_set() -> None:
    result = _run(
        {
            "functionality": [
                ("FEAT-1", "FEAT-1: Funcionalidad A"),
                ("FEAT-2", "FEAT-2: Funcionalidad B"),
                ("FEAT-3", "FEAT-3: Funcionalidad C"),
            ],
            "qa_qc": [("QCBG-10", "QCBG-10: Corrección del listado de reproducción FEAT-1")],
            "nco": [],
        }
    )
    jiras = {row.related_jira for row in result.candidates}
    assert jiras == {"QCBG-10"}
    assert result.candidates[0].origin_release_id == 1
    assert "QC-001" in result.candidates[0].related_origin_case_ids
    assert result.candidates[0].generation_origin == "revalidation-qa-qc"


def test_qa_bug_generates_fix_coverage() -> None:
    result = _run(
        {
            "functionality": [("FEAT-1", "FEAT-1: Funcionalidad A")],
            "qa_qc": [("QABG-22", "QABG-22: Se corrigió el mensaje de error al iniciar sesión")],
            "nco": [],
        }
    )
    assert {row.related_jira for row in result.candidates} == {"QABG-22"}
    assert result.candidates[0].origin_release_id == 1


def test_nco_without_evidence_is_not_invented() -> None:
    assert nco_has_validation_evidence("NCO-1", "NCO-1") is False
    result = _run(
        {
            "functionality": [("FEAT-1", "FEAT-1: Funcionalidad A")],
            "qa_qc": [],
            "nco": [("NCO-1", "NCO-1")],
        }
    )
    assert all(row.related_jira != "NCO-1" for row in result.candidates)
    assert any("NCO-1" in line and "revisión" in line.lower() for line in result.analysis_details)


def test_nco_with_evidence_generates_coverage() -> None:
    result = _run(
        {
            "functionality": [("FEAT-1", "FEAT-1: Funcionalidad A")],
            "qa_qc": [],
            "nco": [
                (
                    "NCO-9",
                    "NCO-9: El usuario ya no ve el modal de error al reproducir el contenido lineal tras la corrección.",
                )
            ],
        }
    )
    assert {row.related_jira for row in result.candidates} == {"NCO-9"}
    assert result.candidates[0].generation_origin == "revalidation-nco"


def test_new_functionality_key_generates_delta_only() -> None:
    result = _run(
        {
            "functionality": [
                ("FEAT-1", "FEAT-1: Funcionalidad A"),
                ("FEAT-99", "FEAT-99: Nueva pasarela de pago"),
            ],
            "qa_qc": [],
            "nco": [],
        }
    )
    assert {row.related_jira for row in result.candidates} == {"FEAT-99"}
    assert result.candidates[0].generation_origin == "revalidation-functional-delta"


def test_nuevo_still_uses_standard_generation(client, monkeypatch, tmp_path) -> None:
    from pathlib import Path

    from tests.test_case_generation import WEB_RN, _create_app_release_from_pdf

    nuevo_id, analysis = _create_app_release_from_pdf(client, monkeypatch, tmp_path, Path(WEB_RN))
    client.patch(f"/api/v1/releases/{nuevo_id}", json={"release_type": "NUEVO"})
    nuevo = client.post(f"/api/v1/releases/{nuevo_id}/generate-cases").json()
    assert nuevo["engine"] == "evidence"
    assert len(nuevo["candidates"]) == analysis["features_count"] == 5


def test_evolutivo_does_not_use_revalidation_engine(client, monkeypatch, tmp_path) -> None:
    from pathlib import Path

    from tests.test_case_generation import WEB_RN, _create_app_release_from_pdf

    origin_id, analysis = _create_app_release_from_pdf(client, monkeypatch, tmp_path, Path(WEB_RN))
    client.patch(
        f"/api/v1/releases/{origin_id}",
        json={"release_type": "NUEVO", "deliverable_name": "WEB - X"},
    )
    evolutivo = client.post(
        "/api/v1/releases",
        json={
            "name": "Evolutivo sibling",
            "version": "9.9.9",
            "platform": "WEB",
            "deliverable_name": "WEB - X",
            "release_type": "EVOLUTIVO",
            "parent_release_id": origin_id,
            "analysis_data": analysis,
        },
    )
    assert evolutivo.status_code == 201, evolutivo.text
    generated = client.post(f"/api/v1/releases/{evolutivo.json()['id']}/generate-cases").json()
    assert generated["engine"] != "revalidation-delta"


def test_revalidation_http_does_not_mutate_origin_cases(client, monkeypatch) -> None:
    origin = client.post(
        "/api/v1/releases",
        json={
            "name": "Origen",
            "version": "1.0.0",
            "platform": "WEB",
            "deliverable_name": "Entregable Z",
            "release_type": "NUEVO",
            "analysis_data": {
                "pdf_filename": "origin.pdf",
                "features_count": 1,
                "qa_qc_issues_count": 0,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    ).json()
    created = client.post(
        f"/api/v1/releases/{origin['id']}/test-cases/bulk",
        json={
            "test_cases": [
                {
                    "test_case_id": "QC-001",
                    "component": "WEB",
                    "test_case_name": "Validar FEAT-1",
                    "description": "FEAT-1",
                    "technical_story": "FEAT-1",
                }
            ]
        },
    )
    assert created.status_code == 201, created.text
    before = client.get(f"/api/v1/releases/{origin['id']}/test-cases").json()

    reval = client.post(
        "/api/v1/releases",
        json={
            "name": "Reval",
            "version": "1.0.1",
            "platform": "WEB",
            "deliverable_name": "Entregable Z",
            "release_type": "REVALIDACION",
            "parent_release_id": origin["id"],
            "analysis_data": {
                "pdf_filename": "reval.pdf",
                "pdf_file_path": "reval.pdf",
                "features_count": 1,
                "qa_qc_issues_count": 1,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    ).json()

    tickets = {
        "functionality": [("FEAT-1", "FEAT-1: A")],
        "qa_qc": [("BUG-1", "BUG-1: Se corrigió el error visible al usuario en el listado FEAT-1")],
        "nco": [],
    }
    monkeypatch.setattr(
        "app.services.revalidation_engine._tickets_by_section",
        lambda _pdf: tickets,
    )
    monkeypatch.setattr("app.routers.releases.read_release_note_pdf", lambda _path: b"%PDF-fake")

    generated = client.post(f"/api/v1/releases/{reval['id']}/generate-cases")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["engine"] == "revalidation-delta"
    assert {row["related_jira"] for row in body["candidates"]} == {"BUG-1"}
    assert body["candidates"][0]["origin_release_id"] == origin["id"]
    assert "QC-001" in body["candidates"][0]["related_origin_case_ids"]

    after = client.get(f"/api/v1/releases/{origin['id']}/test-cases").json()
    assert after == before
    persisted = client.get(f"/api/v1/releases/{reval['id']}/test-cases").json()
    assert len(persisted) == 1
    assert persisted[0]["test_case_name"] != "Validar FEAT-1"


def test_revalidation_keeps_revalidation_delta_engine_without_llm(
    client, monkeypatch
) -> None:
    from dataclasses import replace
    from unittest.mock import MagicMock, patch

    from app.config import settings

    monkeypatch.setattr(
        "app.services.ai_case_engine.settings",
        replace(settings, openai_api_key="sk-test", openai_model="gpt-4o-mini"),
    )
    origin = client.post(
        "/api/v1/releases",
        json={
            "name": "Origen llm guard",
            "version": "1.0.0",
            "platform": "WEB",
            "deliverable_name": "Entregable reval llm",
            "release_type": "NUEVO",
            "analysis_data": {
                "pdf_filename": "origin.pdf",
                "features_count": 1,
                "qa_qc_issues_count": 0,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    ).json()
    created = client.post(
        f"/api/v1/releases/{origin['id']}/test-cases/bulk",
        json={
            "test_cases": [
                {
                    "test_case_id": "QC-001",
                    "component": "WEB",
                    "test_case_name": "Validar FEAT-1",
                    "description": "FEAT-1",
                    "technical_story": "FEAT-1",
                }
            ]
        },
    )
    assert created.status_code == 201, created.text
    reval = client.post(
        "/api/v1/releases",
        json={
            "name": "Reval llm guard",
            "version": "1.0.1",
            "platform": "WEB",
            "deliverable_name": "Entregable reval llm",
            "release_type": "REVALIDACION",
            "parent_release_id": origin["id"],
            "analysis_data": {
                "pdf_filename": "reval.pdf",
                "pdf_file_path": "reval.pdf",
                "features_count": 1,
                "qa_qc_issues_count": 1,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    ).json()
    tickets = {
        "functionality": [("FEAT-1", "FEAT-1: A")],
        "qa_qc": [("BUG-1", "BUG-1: Se corrigió el error visible al usuario en el listado FEAT-1")],
        "nco": [],
    }
    monkeypatch.setattr(
        "app.services.revalidation_engine._tickets_by_section",
        lambda _pdf: tickets,
    )
    monkeypatch.setattr("app.routers.releases.read_release_note_pdf", lambda _path: b"%PDF-fake")
    fake_client = MagicMock()
    with patch("app.services.ai_case_engine.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = fake_client
        generated = client.post(f"/api/v1/releases/{reval['id']}/generate-cases")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["engine"] == "revalidation-delta"
    assert fake_client.post.call_count == 0
    assert {row["related_jira"] for row in body["candidates"]} == {"BUG-1"}
