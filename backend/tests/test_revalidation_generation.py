"""Incremental generation for Release Apps (Evolutivo with history and Revalidación)."""

from app.services.revalidation_engine import (
    generate_revalidation_candidates,
    nco_has_validation_evidence,
    plan_incremental_generation,
)


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


def _run(tickets: dict, origin_cases: list[dict] | None = None, **kwargs):
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
        **kwargs,
    )


def test_identical_functionality_does_not_duplicate_origin_coverage() -> None:
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
    assert result.engine == "incremental-delta"
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
    assert result.candidates[0].generation_origin == "incremental-qa-qc"


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
    assert result.candidates[0].generation_origin == "incremental-nco"


_NCO_EVIDENCE = (
    "NCO-9: El usuario ya no ve el modal de error al reproducir el contenido lineal tras la corrección."
)


def test_qa_qc_already_bound_to_historical_tc_is_not_regenerated() -> None:
    result = _run(
        {
            "functionality": [("FEAT-1", "FEAT-1: Funcionalidad A")],
            "qa_qc": [("QCBG-10", "QCBG-10: Corrección del listado de reproducción FEAT-1")],
            "nco": [],
        },
        origin_cases=_origin_cases("FEAT-1", "QCBG-10"),
    )
    assert all(row.related_jira != "QCBG-10" for row in result.candidates)
    assert any("QCBG-10" in line and "histórico" in line.lower() for line in result.analysis_details)


def test_qa_qc_mentioned_in_prior_rn_without_historical_tc_still_generates() -> None:
    incidental = [
        {
            "id": 1,
            "test_case_id": "QC-001",
            "test_case_name": "Validar FEAT-1",
            "description": "QCBG-10 aparece citado en la descripción",
            "technical_story": "FEAT-1",
            "technical_epic": "FEAT-1",
            "evidence": "Relacionado con QCBG-10 de forma incidental",
            "justification": "QCBG-10 no es la key de este caso",
        }
    ]
    result = _run(
        {
            "functionality": [("FEAT-1", "FEAT-1: Funcionalidad A")],
            "qa_qc": [("QCBG-10", "QCBG-10: Corrección del listado de reproducción FEAT-1")],
            "nco": [],
        },
        origin_cases=incidental,
        prior_qa_qc_cells={"QCBG-10": "QCBG-10: Corrección del listado de reproducción FEAT-1"},
    )
    assert {row.related_jira for row in result.candidates} == {"QCBG-10"}


def test_nco_already_bound_to_historical_tc_is_not_regenerated() -> None:
    result = _run(
        {
            "functionality": [("FEAT-1", "FEAT-1: Funcionalidad A")],
            "qa_qc": [],
            "nco": [("NCO-9", _NCO_EVIDENCE)],
        },
        origin_cases=_origin_cases("FEAT-1", "NCO-9"),
    )
    assert all(row.related_jira != "NCO-9" for row in result.candidates)
    assert any("NCO-9" in line and "histórico" in line.lower() for line in result.analysis_details)


def test_nco_without_stable_key_is_not_deduplicated_by_text() -> None:
    similar = [
        {
            "id": 1,
            "test_case_id": "QC-001",
            "test_case_name": "Validar FEAT-1",
            "description": _NCO_EVIDENCE,
            "technical_story": "FEAT-1",
            "technical_epic": "FEAT-1",
            "evidence": _NCO_EVIDENCE,
            "justification": _NCO_EVIDENCE,
        }
    ]
    result = _run(
        {
            "functionality": [("FEAT-1", "FEAT-1: Funcionalidad A")],
            "qa_qc": [],
            "nco": [("NOTA", _NCO_EVIDENCE.replace("NCO-9", "NOTA"))],
        },
        origin_cases=similar,
    )
    assert result.candidates == []
    assert any("identificador estable" in line.lower() for line in result.analysis_details)


def test_qa_qc_with_historical_tc_and_explicit_rn_change_generates_delta_only() -> None:
    result = _run(
        {
            "functionality": [("FEAT-1", "FEAT-1: Funcionalidad A")],
            "qa_qc": [
                (
                    "QCBG-10",
                    "QCBG-10: Ahora el listado también oculta el banner de error además de la corrección previa.",
                )
            ],
            "nco": [],
        },
        origin_cases=_origin_cases("FEAT-1", "QCBG-10"),
        prior_qa_qc_cells={"QCBG-10": "QCBG-10: Corrección del listado de reproducción FEAT-1"},
    )
    assert {row.related_jira for row in result.candidates} == {"QCBG-10"}
    assert result.candidates[0].generation_origin == "incremental-qa-qc"


def test_new_functionality_key_is_queued_for_full_pipeline_not_generic_delta() -> None:
    tickets = {
        "functionality": [
            ("FEAT-1", "FEAT-1: Funcionalidad A"),
            ("FEAT-99", "FEAT-99: Nueva pasarela de pago"),
        ],
        "qa_qc": [],
        "nco": [],
    }
    plan = plan_incremental_generation(tickets, _origin_cases("FEAT-1", "FEAT-2", "FEAT-3"))
    assert plan.new_functionality == [("FEAT-99", "FEAT-99: Nueva pasarela de pago")]
    result = _run(tickets)
    assert result.candidates == []


def test_same_key_with_rn_cell_change_generates_delta_only() -> None:
    tickets = {
        "functionality": [
            ("FEAT-1", "FEAT-1: Ahora el listado filtra por perfil parental además del comportamiento previo."),
        ],
        "qa_qc": [],
        "nco": [],
    }
    result = _run(
        tickets,
        prior_functionality_cells={"FEAT-1": "FEAT-1: Funcionalidad A"},
    )
    assert {row.related_jira for row in result.candidates} == {"FEAT-1"}
    assert result.candidates[0].generation_origin == "incremental-functional-change"


def test_first_nuevo_uses_standard_generation(client, monkeypatch, tmp_path) -> None:
    from pathlib import Path

    from tests.test_case_generation import WEB_RN, _create_app_release_from_pdf

    release_id, analysis = _create_app_release_from_pdf(client, monkeypatch, tmp_path, Path(WEB_RN))
    client.patch(
        f"/api/v1/releases/{release_id}",
        json={"release_type": "NUEVO", "deliverable_name": "WEB - X"},
    )
    generated = client.post(f"/api/v1/releases/{release_id}/generate-cases").json()
    assert generated["engine"] == "evidence"
    assert len(generated["candidates"]) == analysis["features_count"] == 5


def test_revalidacion_without_baseline_does_not_use_incremental_engine(client, monkeypatch, tmp_path) -> None:
    from pathlib import Path

    from tests.test_case_generation import WEB_RN, _create_app_release_from_pdf

    origin_id, analysis = _create_app_release_from_pdf(client, monkeypatch, tmp_path, Path(WEB_RN))
    client.patch(
        f"/api/v1/releases/{origin_id}",
        json={"release_type": "NUEVO", "deliverable_name": "WEB - X"},
    )
    reval = client.post(
        "/api/v1/releases",
        json={
            "name": "Reval sibling",
            "version": "9.9.9",
            "platform": "WEB",
            "deliverable_name": "WEB - X",
            "release_type": "REVALIDACION",
            "parent_release_id": origin_id,
            "analysis_data": analysis,
        },
    )
    assert reval.status_code == 201, reval.text
    generated = client.post(f"/api/v1/releases/{reval.json()['id']}/generate-cases").json()
    assert generated["engine"] != "incremental-delta"


def test_subsequent_evolutivo_generates_only_new_functionality_via_full_pipeline(client, monkeypatch) -> None:
    from dataclasses import replace

    from app.config import settings

    monkeypatch.setattr(
        "app.services.ai_case_engine.settings",
        replace(settings, openai_api_key=""),
    )
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
                "features_count": 2,
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
    origin_before = client.get(f"/api/v1/releases/{origin['id']}/test-cases").json()

    later = client.post(
        "/api/v1/releases",
        json={
            "name": "Siguiente",
            "version": "1.0.1",
            "platform": "WEB",
            "deliverable_name": "Entregable Z",
            "release_type": "REVALIDACION",
            "parent_release_id": origin["id"],
            "analysis_data": {
                "pdf_filename": "next.pdf",
                "pdf_file_path": "next.pdf",
                "features_count": 2,
                "qa_qc_issues_count": 0,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    ).json()

    tickets = {
        "functionality": [
            ("FEAT-1", "FEAT-1: Funcionalidad A"),
            ("FEAT-99", "FEAT-99: Nueva pasarela de pago"),
        ],
        "qa_qc": [],
        "nco": [],
        "tri": [],
    }
    monkeypatch.setattr("app.routers.releases._tickets_by_section", lambda _pdf: tickets)
    monkeypatch.setattr("app.routers.releases.read_release_note_pdf", lambda _path: b"%PDF-fake")
    monkeypatch.setattr("app.services.ai_case_engine.fetch_artifacts_for_keys", lambda _keys: [])

    generated = client.post(f"/api/v1/releases/{later['id']}/generate-cases")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert {row["related_jira"] for row in body["candidates"]} == {"FEAT-99"}
    assert all("FEAT-1" not in (row["related_jira"] or "") for row in body["candidates"] if row["related_jira"] != "FEAT-99")
    assert body["engine"] == "evidence"
    assert body["candidates"][0]["generation_origin"] == "incremental-new-functionality"

    assert client.get(f"/api/v1/releases/{origin['id']}/test-cases").json() == origin_before
    persisted = client.get(f"/api/v1/releases/{later['id']}/test-cases").json()
    assert len(persisted) == 1
    assert persisted[0]["technical_story"] == "FEAT-99"


def test_baseline_includes_intermediate_release_not_only_declared_origin(client, monkeypatch) -> None:
    v1 = client.post(
        "/api/v1/releases",
        json={
            "name": "V1",
            "version": "1.0.0",
            "platform": "WEB",
            "deliverable_name": "Entregable Z",
            "release_type": "NUEVO",
            "analysis_data": {
                "pdf_filename": "v1.pdf",
                "features_count": 1,
                "qa_qc_issues_count": 0,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    ).json()
    client.post(
        f"/api/v1/releases/{v1['id']}/test-cases/bulk",
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
    v2 = client.post(
        "/api/v1/releases",
        json={
            "name": "V2",
            "version": "1.0.1",
            "platform": "WEB",
            "deliverable_name": "Entregable Z",
            "release_type": "REVALIDACION",
            "parent_release_id": v1["id"],
            "analysis_data": {
                "pdf_filename": "v2.pdf",
                "features_count": 1,
                "qa_qc_issues_count": 0,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    ).json()
    client.post(
        f"/api/v1/releases/{v2['id']}/test-cases/bulk",
        json={
            "test_cases": [
                {
                    "test_case_id": "QC-002",
                    "component": "WEB",
                    "test_case_name": "Validar FEAT-99",
                    "description": "FEAT-99",
                    "technical_story": "FEAT-99",
                }
            ]
        },
    )
    v2_before = client.get(f"/api/v1/releases/{v2['id']}/test-cases").json()

    v3 = client.post(
        "/api/v1/releases",
        json={
            "name": "V3",
            "version": "1.0.2",
            "platform": "WEB",
            "deliverable_name": "Entregable Z",
            "release_type": "REVALIDACION",
            "parent_release_id": v1["id"],
            "analysis_data": {
                "pdf_filename": "v3.pdf",
                "pdf_file_path": "v3.pdf",
                "features_count": 2,
                "qa_qc_issues_count": 1,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    ).json()
    assert v3["parent_release_id"] == v1["id"]

    tickets = {
        "functionality": [
            ("FEAT-1", "FEAT-1: A"),
            ("FEAT-99", "FEAT-99: Nueva pasarela"),
        ],
        "qa_qc": [("BUG-1", "BUG-1: Se corrigió el error visible al usuario en el listado FEAT-1")],
        "nco": [],
        "tri": [],
    }
    monkeypatch.setattr("app.routers.releases._tickets_by_section", lambda _pdf: tickets)
    monkeypatch.setattr("app.routers.releases.read_release_note_pdf", lambda _path: b"%PDF-fake")

    generated = client.post(f"/api/v1/releases/{v3['id']}/generate-cases")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["engine"] == "incremental-delta"
    assert {row["related_jira"] for row in body["candidates"]} == {"BUG-1"}
    assert body["candidates"][0]["origin_release_id"] == v1["id"]
    assert client.get(f"/api/v1/releases/{v2['id']}/test-cases").json() == v2_before
    persisted = client.get(f"/api/v1/releases/{v3['id']}/test-cases").json()
    assert len(persisted) == 1


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
        "tri": [],
    }
    monkeypatch.setattr("app.routers.releases._tickets_by_section", lambda _pdf: tickets)
    monkeypatch.setattr("app.routers.releases.read_release_note_pdf", lambda _path: b"%PDF-fake")

    generated = client.post(f"/api/v1/releases/{reval['id']}/generate-cases")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["engine"] == "incremental-delta"
    assert {row["related_jira"] for row in body["candidates"]} == {"BUG-1"}
    assert body["candidates"][0]["origin_release_id"] == origin["id"]
    assert "QC-001" in body["candidates"][0]["related_origin_case_ids"]

    after = client.get(f"/api/v1/releases/{origin['id']}/test-cases").json()
    assert after == before
    persisted = client.get(f"/api/v1/releases/{reval['id']}/test-cases").json()
    assert len(persisted) == 1
    assert persisted[0]["test_case_name"] != "Validar FEAT-1"


def _add_identity_tc(client, release_id: int, label: str, key: str) -> None:
    created = client.post(
        f"/api/v1/releases/{release_id}/test-cases/bulk",
        json={
            "test_cases": [
                {
                    "test_case_id": label,
                    "component": "WEB",
                    "test_case_name": f"Validar {key}",
                    "description": key,
                    "technical_story": key,
                    "technical_epic": key,
                }
            ]
        },
    )
    assert created.status_code == 201, created.text


def test_qa_qc_history_spans_all_deliverable_releases_not_only_parent(client, monkeypatch) -> None:
    v1 = client.post(
        "/api/v1/releases",
        json={
            "name": "V1",
            "version": "1.0.0",
            "platform": "WEB",
            "deliverable_name": "Entregable Hist",
            "release_type": "NUEVO",
            "analysis_data": {
                "pdf_filename": "v1.pdf",
                "features_count": 1,
                "qa_qc_issues_count": 0,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    ).json()
    _add_identity_tc(client, v1["id"], "QC-001", "FEAT-1")
    _add_identity_tc(client, v1["id"], "QC-010", "BUG-1")
    v1_before = client.get(f"/api/v1/releases/{v1['id']}/test-cases").json()

    v2 = client.post(
        "/api/v1/releases",
        json={
            "name": "V2",
            "version": "1.0.1",
            "platform": "WEB",
            "deliverable_name": "Entregable Hist",
            "release_type": "REVALIDACION",
            "parent_release_id": v1["id"],
            "analysis_data": {
                "pdf_filename": "v2.pdf",
                "features_count": 1,
                "qa_qc_issues_count": 1,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    ).json()
    _add_identity_tc(client, v2["id"], "QC-020", "BUG-2")
    v2_before = client.get(f"/api/v1/releases/{v2['id']}/test-cases").json()

    v3 = client.post(
        "/api/v1/releases",
        json={
            "name": "V3",
            "version": "1.0.2",
            "platform": "WEB",
            "deliverable_name": "Entregable Hist",
            "release_type": "REVALIDACION",
            "parent_release_id": v1["id"],
            "analysis_data": {
                "pdf_filename": "v3.pdf",
                "pdf_file_path": "v3.pdf",
                "features_count": 1,
                "qa_qc_issues_count": 3,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    ).json()
    assert v3["parent_release_id"] == v1["id"]

    tickets = {
        "functionality": [("FEAT-1", "FEAT-1: A")],
        "qa_qc": [
            ("BUG-1", "BUG-1: Se corrigió el error visible al usuario en el listado FEAT-1"),
            ("BUG-2", "BUG-2: Se corrigió el banner de error en checkout"),
            ("BUG-3", "BUG-3: Se corrigió el mensaje al iniciar sesión"),
        ],
        "nco": [],
        "tri": [],
    }
    monkeypatch.setattr("app.routers.releases._tickets_by_section", lambda _pdf: tickets)
    monkeypatch.setattr("app.routers.releases.read_release_note_pdf", lambda _path: b"%PDF-fake")

    generated = client.post(f"/api/v1/releases/{v3['id']}/generate-cases")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert {row["related_jira"] for row in body["candidates"]} == {"BUG-3"}
    assert client.get(f"/api/v1/releases/{v1['id']}/test-cases").json() == v1_before
    assert client.get(f"/api/v1/releases/{v2['id']}/test-cases").json() == v2_before
    persisted = client.get(f"/api/v1/releases/{v3['id']}/test-cases").json()
    assert [row["technical_story"] for row in persisted] == ["BUG-3"]


def test_intermediate_release_tc_covers_qa_qc_even_when_parent_is_another_release(
    client, monkeypatch
) -> None:
    v1 = client.post(
        "/api/v1/releases",
        json={
            "name": "V1",
            "version": "1.0.0",
            "platform": "WEB",
            "deliverable_name": "Entregable Parent",
            "release_type": "NUEVO",
            "analysis_data": {
                "pdf_filename": "v1.pdf",
                "features_count": 1,
                "qa_qc_issues_count": 0,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    ).json()
    _add_identity_tc(client, v1["id"], "QC-001", "FEAT-1")
    v1_before = client.get(f"/api/v1/releases/{v1['id']}/test-cases").json()

    v2 = client.post(
        "/api/v1/releases",
        json={
            "name": "V2",
            "version": "1.0.1",
            "platform": "WEB",
            "deliverable_name": "Entregable Parent",
            "release_type": "REVALIDACION",
            "parent_release_id": v1["id"],
            "analysis_data": {
                "pdf_filename": "v2.pdf",
                "features_count": 1,
                "qa_qc_issues_count": 1,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    ).json()
    _add_identity_tc(client, v2["id"], "QC-010", "QCBG-10")
    v2_before = client.get(f"/api/v1/releases/{v2['id']}/test-cases").json()

    v3 = client.post(
        "/api/v1/releases",
        json={
            "name": "V3",
            "version": "1.0.2",
            "platform": "WEB",
            "deliverable_name": "Entregable Parent",
            "release_type": "REVALIDACION",
            "parent_release_id": v1["id"],
            "analysis_data": {
                "pdf_filename": "v3.pdf",
                "pdf_file_path": "v3.pdf",
                "features_count": 1,
                "qa_qc_issues_count": 1,
                "nco_issues_count": 0,
                "tri_issues_count": 0,
                "observations": [],
            },
        },
    ).json()
    assert v3["parent_release_id"] == v1["id"]

    tickets = {
        "functionality": [("FEAT-1", "FEAT-1: A")],
        "qa_qc": [("QCBG-10", "QCBG-10: Corrección del listado de reproducción FEAT-1")],
        "nco": [],
        "tri": [],
    }
    monkeypatch.setattr("app.routers.releases._tickets_by_section", lambda _pdf: tickets)
    monkeypatch.setattr("app.routers.releases.read_release_note_pdf", lambda _path: b"%PDF-fake")

    generated = client.post(f"/api/v1/releases/{v3['id']}/generate-cases")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["candidates"] == []
    assert client.get(f"/api/v1/releases/{v1['id']}/test-cases").json() == v1_before
    assert client.get(f"/api/v1/releases/{v2['id']}/test-cases").json() == v2_before
    assert client.get(f"/api/v1/releases/{v3['id']}/test-cases").json() == []

