"""Tests for the Operativa router -- 5-step pipeline (analyze-rn, header/config patch, EPC patch).

Uses the REAL OPE-AGOSTO-2026-AUP RN Operativo as fixture, same discipline as the Release RN
analyzer tests: this document's page-break continuations and multi-table structure can't be
faithfully exercised by a hand-typed sample.
"""

from pathlib import Path

import pytest

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "APMOGH-OPE-AGOSTO-2026-AUP_Release_notes.pdf"


@pytest.fixture(scope="module")
def real_rn_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


def _analyze(client, pdf_bytes: bytes):
    return client.post(
        "/api/v1/operativa/analyze-rn",
        files={"file": (FIXTURE_PATH.name, pdf_bytes, "application/pdf")},
    )


def test_analyze_rn_rejects_non_pdf(client) -> None:
    response = client.post(
        "/api/v1/operativa/analyze-rn",
        files={"file": ("notas.txt", b"hola", "text/plain")},
    )
    assert response.status_code == 400


def test_analyze_real_rn_extracts_header_from_document_not_filename(client, real_rn_bytes) -> None:
    """Paso 2: name/cluster/entregable come from page-1 evidence. The upload filename is
    stored only as pdf_filename and must not leak into name."""
    response = _analyze(client, real_rn_bytes)
    assert response.status_code == 201
    body = response.json()["operativa_release"]
    assert body["name"] == "OPE-AGOSTO-2026-AUP"
    assert body["cluster"] == "AUP"
    assert body["entregable"] == "Release Claro video"
    assert body["pdf_filename"] == FIXTURE_PATH.name
    assert not body["name"].startswith("APMOGH")
    assert body["start_date"] is None
    assert body["jira_filter_url"] is None


def test_analyze_real_rn_detects_all_twelve_epcs(client, real_rn_bytes) -> None:
    """12 = 11 from the 'Épicas Finalizadas' table + BRF-17294 (only in the second table, with
    its own explicit out-of-scope note)."""
    response = _analyze(client, real_rn_bytes)
    assert response.status_code == 201
    body = response.json()
    epcs = body["operativa_release"]["epcs"]
    assert len(epcs) == 12


def test_analyze_real_rn_suggestion_never_forces_a_final_decision(client, real_rn_bytes) -> None:
    """The clearly-ready EPCs (estado In Validate, no exclusion note) suggest inclusion;
    BRF-17294 (explicit 'fuera del scope' note) suggests exclusion. In every case,
    include_in_qc starts matching the suggestion but stays a normal editable field."""
    response = _analyze(client, real_rn_bytes)
    epcs = response.json()["operativa_release"]["epcs"]  # list, NOT keyed by brf_key -- two
    # BRFs (17442, 17443) legitimately appear twice each with a different epc_key, so a dict
    # keyed by brf_key alone would silently collapse those pairs to one entry.

    incluir_epcs = [e for e in epcs if e["qc_suggestion"] == "SUGERIDO_INCLUIR"]
    assert len(incluir_epcs) == 11
    assert all(e["include_in_qc"] is True for e in incluir_epcs)

    by_brf = {e["brf_key"]: e for e in epcs if e["brf_key"] in ("BRF-17294", "BRF-17603")}
    assert by_brf["BRF-17294"]["qc_suggestion"] == "SUGERIDO_EXCLUIR"
    assert by_brf["BRF-17294"]["include_in_qc"] is False
    assert "fuera del" in by_brf["BRF-17294"]["nota_rte"].lower()

    assert by_brf["BRF-17603"]["qc_suggestion"] == "SUGERIDO_INCLUIR"
    assert by_brf["BRF-17603"]["include_in_qc"] is True
    assert by_brf["BRF-17603"]["estado_jira"] == "In Validate"


def test_analyze_real_rn_excludes_tri_and_stop_table_rows(client, real_rn_bytes) -> None:
    """TRI-145871/TRI-144033 (Incidentes productivos) and the VPN credentials table must never
    appear as EPC rows."""
    response = _analyze(client, real_rn_bytes)
    epcs = response.json()["operativa_release"]["epcs"]
    all_keys = {e["brf_key"] for e in epcs} | {e["epc_key"] for e in epcs if e["epc_key"]}
    assert not any("TRI" in k for k in all_keys)
    assert not any("Uruguay" in str(e.get("titulo", "")) for e in epcs)


def test_get_operativa_release_returns_persisted_epcs(client, real_rn_bytes) -> None:
    created = _analyze(client, real_rn_bytes).json()["operativa_release"]
    response = client.get(f"/api/v1/operativa/{created['id']}")
    assert response.status_code == 200
    assert len(response.json()["epcs"]) == 12


def test_patch_epc_overrides_the_suggestion_and_is_never_locked(client, real_rn_bytes) -> None:
    """Regla de diseño explícita: el filtro automático es solo una sugerencia -- el usuario
    puede invertir la decisión en cualquier momento, en cualquier dirección."""
    created = _analyze(client, real_rn_bytes).json()["operativa_release"]
    epc_incluido = next(e for e in created["epcs"] if e["qc_suggestion"] == "SUGERIDO_INCLUIR")
    epc_excluido = next(e for e in created["epcs"] if e["brf_key"] == "BRF-17294")

    # Override manual: excluir uno que el sistema sugería incluir (caso real BRF-17702).
    response = client.patch(f"/api/v1/operativa/epcs/{epc_incluido['id']}", json={"include_in_qc": False})
    assert response.status_code == 200
    assert response.json()["include_in_qc"] is False
    assert response.json()["qc_suggestion"] == "SUGERIDO_INCLUIR"  # la sugerencia original no cambia

    # Override manual: incluir uno que el sistema sugería excluir.
    response = client.patch(f"/api/v1/operativa/epcs/{epc_excluido['id']}", json={"include_in_qc": True})
    assert response.status_code == 200
    assert response.json()["include_in_qc"] is True
    assert response.json()["qc_suggestion"] == "SUGERIDO_EXCLUIR"


def test_patch_epc_alcance_funcional_and_dispositivos(client, real_rn_bytes) -> None:
    created = _analyze(client, real_rn_bytes).json()["operativa_release"]
    epc = created["epcs"][0]

    response = client.patch(
        f"/api/v1/operativa/epcs/{epc['id']}",
        json={
            "alcance_funcional": "Criterio de aceptación pegado manualmente desde Jira.",
            "dispositivos_aplicables": ["WEB", "iOS"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["alcance_funcional"] == "Criterio de aceptación pegado manualmente desde Jira."
    assert body["dispositivos_aplicables"] == ["WEB", "iOS"]


def test_patch_operativa_release_updates_header_and_config(client, real_rn_bytes) -> None:
    created = _analyze(client, real_rn_bytes).json()["operativa_release"]
    response = client.patch(
        f"/api/v1/operativa/{created['id']}",
        json={
            "entregable": "Release Claro video (corregido)",
            "name": "OPE-AGOSTO-2026-AUP",
            "cluster": "Andina",
            "start_date": "2026-08-01",
            "end_date": "2026-08-15",
            "jira_filter_url": "https://jira.example/filter/1",
            "jira_filter_manual": "project = OPE AND fixVersion = AGOSTO",
            "instrucciones_adicionales": "Validar add-ons Sony One.",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["entregable"] == "Release Claro video (corregido)"
    assert body["cluster"] == "Andina"
    assert body["start_date"] == "2026-08-01"
    assert body["end_date"] == "2026-08-15"
    assert body["jira_filter_url"] == "https://jira.example/filter/1"
    assert body["jira_filter_manual"] == "project = OPE AND fixVersion = AGOSTO"
    assert body["instrucciones_adicionales"] == "Validar add-ons Sony One."
    assert len(body["epcs"]) == 12


def test_patch_operativa_release_description(client, real_rn_bytes) -> None:
    created = _analyze(client, real_rn_bytes).json()["operativa_release"]
    response = client.patch(
        f"/api/v1/operativa/{created['id']}",
        json={"description": "Notas de alcance para QC."},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Notas de alcance para QC."


def test_list_operativa_releases_returns_created_rows(client, real_rn_bytes) -> None:
    first = _analyze(client, real_rn_bytes).json()["operativa_release"]
    second = _analyze(client, real_rn_bytes).json()["operativa_release"]
    response = client.get("/api/v1/operativa")
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()}
    assert first["id"] in ids
    assert second["id"] in ids


def test_patch_operativa_release_blank_header_clears_to_null(client, real_rn_bytes) -> None:
    created = _analyze(client, real_rn_bytes).json()["operativa_release"]
    response = client.patch(
        f"/api/v1/operativa/{created['id']}",
        json={"entregable": "  ", "cluster": ""},
    )
    assert response.status_code == 200
    assert response.json()["entregable"] is None
    assert response.json()["cluster"] is None


def test_patch_operativa_release_not_found_returns_404(client) -> None:
    response = client.patch("/api/v1/operativa/999999", json={"cluster": "AUP"})
    assert response.status_code == 404


def test_patch_epc_not_found_returns_404(client) -> None:
    response = client.patch("/api/v1/operativa/epcs/999999", json={"include_in_qc": True})
    assert response.status_code == 404


def test_create_qc_release_from_operativa(client, real_rn_bytes) -> None:
    created = _analyze(client, real_rn_bytes).json()["operativa_release"]
    client.patch(
        f"/api/v1/operativa/{created['id']}",
        json={"start_date": "2026-08-03", "end_date": "2026-08-14"},
    )
    expected_included = [e for e in created["epcs"] if e["include_in_qc"]]

    response = client.post(f"/api/v1/operativa/{created['id']}/create-release")
    assert response.status_code == 201
    body = response.json()
    assert body["platform"] == "Operativa"
    assert body["version"] == "OPE"
    assert body["name"] == "OPE-AGOSTO-2026-AUP"
    assert body["operativa_release_id"] == created["id"]
    assert body["qc_resources"] is None
    assert body["validation_type"] is None
    assert body["cluster"] == "AUP"
    assert body["deliverable_name"] == "Release Claro video"
    assert body["execution_days"] == 10
    assert body["status"] == "DRAFT"

    gotten = client.get(f"/api/v1/releases/{body['id']}")
    assert gotten.status_code == 200
    assert gotten.json()["operativa_release_id"] == created["id"]

    frozen = client.get(f"/api/v1/operativa/qc-releases/{body['id']}/epcs")
    assert frozen.status_code == 200
    frozen_ids = {row["id"] for row in frozen.json()}
    assert frozen_ids == {e["id"] for e in expected_included}
    assert all(row["release_id"] == body["id"] for row in frozen.json())

    listed = client.get("/api/v1/operativa")
    assert listed.status_code == 200
    listed_row = next(row for row in listed.json() if row["id"] == created["id"])
    assert listed_row["qc_release_id"] == body["id"]
    assert listed_row["qc_release_status"] == "DRAFT"


def test_create_qc_release_from_operativa_is_idempotent(client, real_rn_bytes) -> None:
    created = _analyze(client, real_rn_bytes).json()["operativa_release"]
    first = client.post(f"/api/v1/operativa/{created['id']}/create-release")
    assert first.status_code == 201

    second = client.post(f"/api/v1/operativa/{created['id']}/create-release")
    assert second.status_code == 409
    assert second.json()["detail"] == "Ya existe un Release asociado a esta Operativa."

    listed = client.get("/api/v1/releases")
    operativa_in_apps = [
        row for row in listed.json() if row.get("operativa_release_id") == created["id"]
    ]
    assert operativa_in_apps == []
    listed_ope = client.get("/api/v1/releases", params={"include_operativa": True})
    operativa_releases = [
        row for row in listed_ope.json() if row.get("operativa_release_id") == created["id"]
    ]
    assert len(operativa_releases) == 1


def test_create_qc_release_requires_name(client, real_rn_bytes) -> None:
    created = _analyze(client, real_rn_bytes).json()["operativa_release"]
    client.patch(f"/api/v1/operativa/{created['id']}", json={"name": ""})
    response = client.post(f"/api/v1/operativa/{created['id']}/create-release")
    assert response.status_code == 400
    assert "Nombre" in response.json()["detail"]


def test_create_qc_release_freezes_included_epcs(client, real_rn_bytes) -> None:
    created = _analyze(client, real_rn_bytes).json()["operativa_release"]
    excluded = next(e for e in created["epcs"] if e["include_in_qc"] is False)
    included = next(e for e in created["epcs"] if e["include_in_qc"] is True)

    created_release = client.post(f"/api/v1/operativa/{created['id']}/create-release")
    assert created_release.status_code == 201
    release_id = created_release.json()["id"]
    frozen_before = {row["id"] for row in client.get(f"/api/v1/operativa/qc-releases/{release_id}/epcs").json()}

    client.patch(f"/api/v1/operativa/epcs/{excluded['id']}", json={"include_in_qc": True})
    client.patch(f"/api/v1/operativa/epcs/{included['id']}", json={"include_in_qc": False})

    frozen_after = client.get(f"/api/v1/operativa/qc-releases/{release_id}/epcs").json()
    frozen_ids = {row["id"] for row in frozen_after}
    assert frozen_ids == frozen_before
    assert excluded["id"] not in frozen_ids
    assert included["id"] in frozen_ids


def test_delete_qc_release_removes_operativa_and_rn(client, real_rn_bytes) -> None:
    created = _analyze(client, real_rn_bytes).json()["operativa_release"]
    operativa_id = created["id"]
    pdf_path = created.get("pdf_file_path")
    qc = client.post(f"/api/v1/operativa/{operativa_id}/create-release")
    assert qc.status_code == 201
    release_id = qc.json()["id"]
    client.patch(f"/api/v1/releases/{release_id}", json={"status": "IN_PROGRESS"})

    response = client.delete(f"/api/v1/releases/{release_id}")

    assert response.status_code == 204
    assert client.get(f"/api/v1/releases/{release_id}").status_code == 404
    assert client.get(f"/api/v1/operativa/{operativa_id}").status_code == 404
    if pdf_path:
        assert not Path(pdf_path).exists()


def test_delete_operativa_draft_removes_rn(client, real_rn_bytes) -> None:
    created = _analyze(client, real_rn_bytes).json()["operativa_release"]
    operativa_id = created["id"]
    pdf_path = created.get("pdf_file_path")

    response = client.delete(f"/api/v1/operativa/{operativa_id}")

    assert response.status_code == 204
    assert client.get(f"/api/v1/operativa/{operativa_id}").status_code == 404
    if pdf_path:
        assert not Path(pdf_path).exists()


def test_frozen_epcs_endpoint_rejects_device_release(client) -> None:
    created = client.post(
        "/api/v1/releases",
        json={"name": "Claro Video", "version": "8.15", "platform": "tvOS"},
    )
    assert created.status_code == 201
    response = client.get(f"/api/v1/operativa/qc-releases/{created.json()['id']}/epcs")
    assert response.status_code == 404


def test_create_qc_release_not_found(client) -> None:
    response = client.post("/api/v1/operativa/999999/create-release")
    assert response.status_code == 404


SEPT_AUP_PATH = Path(__file__).parent / "fixtures" / "PMOGH-OPE-SEPTIEMBRE-2026-AUP.pdf"
JULIO_PATH = Path(__file__).parent / "fixtures" / "PMOGH-OPE-JULIO-2026-AND.pdf"


def test_reconstruct_split_epc_key_and_continuation_without_rn_ids() -> None:
    from app.services.operativa_analyzer import (
        collect_epc_candidates_from_tables,
        parse_epc_identity_cell,
        stitch_wrapped_epc_key,
    )

    key, title = parse_epc_identity_cell("EPC-8800\n1: AR | CV | Alta del type")
    assert key == "EPC-88001"
    assert "Alta del type" in title
    stitched, rest = stitch_wrapped_epc_key("EPC-8800", "1: resto del titulo In Validate")
    assert stitched == "EPC-88001"
    assert "resto del titulo" in rest

    header = ["Brief Key", "Clave", "Tipo de Epica", "Alcance", "Nota RTE", "Versiones"]
    page1 = [
        header,
        ["BRF-88001", "EPC-8800", "Operativo", "Total", "No requiere", "OPE-X"],
        ["", "1: titulo partido", "", "", "pruebas de QC", ""],
    ]
    page2 = [
        ["", "continúa el titulo In Validate", "", "", "", ""],
        ["BRF-88002", "EPC-88002: Otra oferta In Validate", "Operativo", "Total", "", "OPE-X"],
    ]
    scope = [
        ["Clave", "Tipo de BRF", "Estado", "Alcance", "Nota RTE", "Versiones"],
        ["BRF-88001: titulo scope", "Operativo", "To Develop", "", "", "OPE-X"],
        ["BRF-88002: otra", "Operativo", "In Develop", "", "", "OPE-X"],
    ]
    rows = collect_epc_candidates_from_tables([[page1], [page2], [scope]])
    pairs = {(item.brf_key, item.epc_key) for item in rows}
    assert pairs == {("BRF-88001", "EPC-88001"), ("BRF-88002", "EPC-88002")}
    first = next(item for item in rows if item.brf_key == "BRF-88001")
    assert first.estado_jira == "In Validate"
    assert "titulo partido" in first.titulo
    assert "continúa el titulo" in first.titulo


def test_scope_table_does_not_duplicate_epc_source_rows() -> None:
    from app.services.operativa_analyzer import collect_epc_candidates_from_tables

    epc_table = [
        ["Brief Key", "Clave", "Tipo de Epica", "Alcance", "Nota RTE", "Versiones"],
        ["BRF-88010", "EPC-88010: Alta In Validate", "Operativo", "Total", "", "OPE-X"],
    ]
    scope = [
        ["Clave", "Tipo de BRF", "Estado", "Alcance", "Nota RTE", "Versiones"],
        ["BRF-88010: Alta", "Operativo", "To Develop", "", "", "OPE-X"],
        ["BRF-88011: Solo en scope fuera del scope", "Operativo", "In Develop", "Total", "fuera del scope", "OPE-X"],
    ]
    rows = collect_epc_candidates_from_tables([[epc_table], [scope]])
    assert len(rows) == 2
    with_epc = next(item for item in rows if item.epc_key == "EPC-88010")
    assert with_epc.estado_jira == "In Validate"
    only_scope = next(item for item in rows if item.brf_key == "BRF-88011")
    assert only_scope.epc_key is None
    assert only_scope.qc_suggestion == "SUGERIDO_EXCLUIR"


def test_cover_blob_mentioning_brf_is_not_a_row() -> None:
    from app.services.operativa_analyzer import collect_epc_candidates_from_tables

    cover = [
        [
            "OPE-X Release notes Release Claro video Brief Key Clave Tipo de Epica "
            "BRF-88020 EPC-88020: no debe salir de esta celda de portada"
        ]
    ]
    real = [
        ["Brief Key", "Clave", "Tipo de Epica", "Alcance", "Nota RTE", "Versiones"],
        ["BRF-88020", "EPC-88020: Titulo real In Validate", "Operativo", "Total", "", "OPE-X"],
    ]
    rows = collect_epc_candidates_from_tables([[cover, real]])
    assert [(item.brf_key, item.epc_key) for item in rows] == [("BRF-88020", "EPC-88020")]


def test_september_aup_rn_reconstructs_epc_table_not_scope_duplicates(client) -> None:
    pdf_bytes = SEPT_AUP_PATH.read_bytes()
    response = client.post(
        "/api/v1/operativa/analyze-rn",
        files={"file": (SEPT_AUP_PATH.name, pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 201
    epcs = response.json()["operativa_release"]["epcs"]
    pairs = {(row["brf_key"], row["epc_key"]) for row in epcs}
    assert pairs == {
        ("BRF-17795", "EPC-22041"),
        ("BRF-17849", "EPC-22031"),
        ("BRF-17794", "EPC-22030"),
        ("BRF-17048", "EPC-21879"),
    }
    assert all(row["epc_key"] for row in epcs)
    row_17795 = next(row for row in epcs if row["brf_key"] == "BRF-17795")
    assert "pincode" in (row_17795["titulo"] or "").lower() or "tata" in (row_17795["titulo"] or "").lower()
    assert row_17795["estado_jira"] == "In Validate"
    assert row_17795["qc_suggestion"] == "SUGERIDO_EXCLUIR"
    row_17794 = next(row for row in epcs if row["brf_key"] == "BRF-17794")
    assert row_17794["qc_suggestion"] == "SUGERIDO_EXCLUIR"


def test_julio_rn_keeps_epc_source_structure(client) -> None:
    pdf_bytes = JULIO_PATH.read_bytes()
    response = client.post(
        "/api/v1/operativa/analyze-rn",
        files={"file": (JULIO_PATH.name, pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 201
    epcs = response.json()["operativa_release"]["epcs"]
    assert epcs
    keys = [(row["brf_key"], row["epc_key"]) for row in epcs]
    assert len(keys) == len(set(keys))
    assert all(row["brf_key"].startswith("BRF-") for row in epcs)
    assert not any("TRI" in (row["brf_key"] or "") or (row["epc_key"] or "").startswith("TRI") for row in epcs)


def test_suggestion_excludes_pin_lot_generation_and_no_qc_rte_without_locking_checkbox() -> None:
    from app.services.operativa_analyzer import EpcCandidate, _compute_suggestion, collect_epc_candidates_from_tables

    assert (
        _compute_suggestion(None, "In Validate", "PY | CV | Generar lotes de pincodes Prepaid")
        == "SUGERIDO_EXCLUIR"
    )
    assert (
        _compute_suggestion(None, "In Validate", "AR | CV | Generar lotes de PIN para recarga")
        == "SUGERIDO_EXCLUIR"
    )
    assert (
        _compute_suggestion("No requiere pruebas de QC", "In Validate", "OTT | Alta de oferta EST")
        == "SUGERIDO_EXCLUIR"
    )
    assert (
        _compute_suggestion("No requiere validación de QC", "In Validate", "OTT | Alta de oferta EST")
        == "SUGERIDO_EXCLUIR"
    )
    assert (
        _compute_suggestion(None, "In Validate", "OTT | Alta de la oferta comercial Type EST 1J")
        == "SUGERIDO_INCLUIR"
    )
    assert (
        _compute_suggestion(None, "In Validate", "OTT | Alta de parental control (PIN de acceso)")
        == "SUGERIDO_INCLUIR"
    )
    assert (
        _compute_suggestion(None, "In Validate", "WEB | Validar ingreso de PIN en checkout")
        == "SUGERIDO_INCLUIR"
    )

    both = EpcCandidate(
        "BRF-88040",
        "EPC-88040",
        "Generación de lotes de pincodes",
        "Total",
        "No requiere pruebas de QC",
        "In Validate",
    )
    assert both.qc_suggestion == "SUGERIDO_EXCLUIR"

    header = ["Brief Key", "Clave", "Tipo de Epica", "Alcance", "Nota RTE", "Versiones"]
    rows = collect_epc_candidates_from_tables(
        [
            [
                [
                    header,
                    [
                        "BRF-88041",
                        "EPC-88041: Generar lotes de pincodes TATA In Validate",
                        "Operativo",
                        "Total",
                        "No requiere pruebas de QC",
                        "OPE-X",
                    ],
                    [
                        "BRF-88042",
                        "EPC-88042: Alta de oferta Type EST In Validate",
                        "Operativo",
                        "Total",
                        "",
                        "OPE-X",
                    ],
                ]
            ]
        ]
    )
    pin_row = next(item for item in rows if item.brf_key == "BRF-88041")
    offer_row = next(item for item in rows if item.brf_key == "BRF-88042")
    assert pin_row.qc_suggestion == "SUGERIDO_EXCLUIR"
    assert offer_row.qc_suggestion == "SUGERIDO_INCLUIR"


def test_excluded_pin_suggestion_checkbox_stays_editable(client) -> None:
    """Sugerido: excluir never locks include_in_qc -- QC can still include the EPC."""
    pdf_bytes = SEPT_AUP_PATH.read_bytes()
    created = client.post(
        "/api/v1/operativa/analyze-rn",
        files={"file": (SEPT_AUP_PATH.name, pdf_bytes, "application/pdf")},
    ).json()["operativa_release"]
    excluded = next(
        row
        for row in created["epcs"]
        if row["qc_suggestion"] == "SUGERIDO_EXCLUIR" and "pincode" in (row["titulo"] or "").lower()
    )
    assert excluded["include_in_qc"] is False
    response = client.patch(f"/api/v1/operativa/epcs/{excluded['id']}", json={"include_in_qc": True})
    assert response.status_code == 200
    assert response.json()["include_in_qc"] is True
    assert response.json()["qc_suggestion"] == "SUGERIDO_EXCLUIR"
