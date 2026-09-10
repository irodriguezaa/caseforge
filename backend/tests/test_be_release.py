"""Tests for Release BE: optional RN, header/config, create QC Release."""


def _pdf_with_lines(*lines: str) -> bytes:
    text_ops = "\n".join(f"0 -20 Td ({line}) Tj" for line in lines)
    stream = f"BT /F1 12 Tf 72 720 Td\n{text_ops}\nET"
    return f"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length {len(stream)} >> stream
{stream}
endstream endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000306 00000 n
0000000456 00000 n
trailer << /Size 6 /Root 1 0 R >>
startxref
555
%%EOF
""".encode("latin-1")


def test_analyze_rn_rejects_non_pdf(client) -> None:
    response = client.post(
        "/api/v1/releases-be/analyze-rn",
        files={"file": ("notas.txt", b"hola", "text/plain")},
    )
    assert response.status_code == 400


def test_create_without_pdf(client) -> None:
    response = client.post("/api/v1/releases-be")
    assert response.status_code == 201
    body = response.json()
    assert body["pdf_filename"] is None
    assert body["name"] is None
    assert body["entregable"] is None
    assert body["swf"] is None
    assert body["clusters"] is None


def test_analyze_rn_extracts_clear_header_and_does_not_invent(client) -> None:
    pdf = _pdf_with_lines("Entregable: API Pagos", "Nombre: BE-PAGOS-2026", "SWF Neoris")
    response = client.post(
        "/api/v1/releases-be/analyze-rn",
        files={"file": ("be-rn.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()["be_release"]
    assert body["entregable"] == "API Pagos"
    assert body["name"] == "BE-PAGOS-2026"
    assert body["swf"] is None
    assert body["pdf_filename"] == "be-rn.pdf"
    assert not body["name"].endswith(".pdf")


def test_analyze_rn_leaves_fields_empty_without_evidence(client) -> None:
    pdf = _pdf_with_lines("Documento interno sin etiquetas")
    response = client.post(
        "/api/v1/releases-be/analyze-rn",
        files={"file": ("mystery.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()["be_release"]
    assert body["entregable"] is None
    assert body["name"] is None
    assert body["swf"] is None
    assert body["pdf_filename"] == "mystery.pdf"


def test_analyze_rn_does_not_guess_swf_when_multiple_vendors(client) -> None:
    pdf = _pdf_with_lines("Entregable: Mix", "Nombre: MIX", "Neoris y Tata")
    body = client.post(
        "/api/v1/releases-be/analyze-rn",
        files={"file": ("mix.pdf", pdf, "application/pdf")},
    ).json()["be_release"]
    assert body["swf"] is None


def test_patch_header_and_scope(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    response = client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={
            "entregable": "Billing API",
            "name": "BE-BILLING",
            "swf": "BE Hitss",
            "description": "Notas de alcance",
            "regresivo_scope": "ACOTADO",
            "affected_component": "Login",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["entregable"] == "Billing API"
    assert body["name"] == "BE-BILLING"
    assert body["swf"] == "BE Hitss"
    assert body["description"] == "Notas de alcance"
    assert body["regresivo_scope"] == "ACOTADO"
    assert body["affected_component"] == "Login"


def test_patch_scope_completo_clears_component(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"regresivo_scope": "ACOTADO", "affected_component": "Pagos"},
    )
    response = client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"regresivo_scope": "COMPLETO"},
    )
    assert response.status_code == 200
    assert response.json()["regresivo_scope"] == "COMPLETO"
    assert response.json()["affected_component"] is None


def test_patch_rejects_unknown_swf(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    response = client.patch(f"/api/v1/releases-be/{created['id']}", json={"swf": "OTROS"})
    assert response.status_code == 422


def test_patch_rejects_legacy_short_swf_names(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    for value in ("Hitss", "Neoris", "Tata"):
        response = client.patch(f"/api/v1/releases-be/{created['id']}", json={"swf": value})
        assert response.status_code == 422, value


def test_patch_single_cluster(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    response = client.patch(f"/api/v1/releases-be/{created['id']}", json={"clusters": ["AUP"]})
    assert response.status_code == 200, response.text
    assert response.json()["clusters"] == ["AUP"]
    assert client.get(f"/api/v1/releases-be/{created['id']}").json()["clusters"] == ["AUP"]


def test_patch_multiple_clusters_preserves_canonical_order(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    response = client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"clusters": ["Dominicana", "AUP", "Global"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["clusters"] == ["Global", "AUP", "Dominicana"]


def test_patch_todos_clears_individual_clusters(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(f"/api/v1/releases-be/{created['id']}", json={"clusters": ["AUP", "CENAM"]})
    response = client.patch(f"/api/v1/releases-be/{created['id']}", json={"clusters": ["Todos"]})
    assert response.status_code == 200
    assert response.json()["clusters"] == ["Todos"]


def test_patch_individual_cluster_clears_todos(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(f"/api/v1/releases-be/{created['id']}", json={"clusters": ["Todos"]})
    response = client.patch(f"/api/v1/releases-be/{created['id']}", json={"clusters": ["Andina"]})
    assert response.status_code == 200
    assert response.json()["clusters"] == ["Andina"]
    assert "Todos" not in response.json()["clusters"]


def test_patch_todos_cannot_coexist_with_individual_clusters(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    response = client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"clusters": ["Todos", "AUP", "Global"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["clusters"] == ["Todos"]


def test_patch_rejects_unknown_cluster(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    response = client.patch(f"/api/v1/releases-be/{created['id']}", json={"clusters": ["LATAM"]})
    assert response.status_code == 422


def test_create_qc_release_copies_clusters_label(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={
            "name": "BE-CLUSTERS",
            "swf": "BE Hitss",
            "regresivo_scope": "SMOKE",
            "clusters": ["CENAM", "AUP"],
        },
    )
    response = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["cluster"] == "AUP, CENAM"
    listed = client.get("/api/v1/releases-be").json()
    row = next(item for item in listed if item["id"] == created["id"])
    assert row["clusters"] == ["AUP", "CENAM"]


def test_create_qc_release_with_todos_cluster(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={
            "name": "BE-TODOS",
            "swf": "BE Neoris",
            "regresivo_scope": "COMPLETO",
            "clusters": ["Todos"],
        },
    )
    response = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert response.status_code == 201, response.text
    assert response.json()["cluster"] == "Todos"


def test_create_qc_release_without_pdf(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"name": "BE-NO-RN", "entregable": "Core API", "swf": "BE Nubiral", "regresivo_scope": "SMOKE"},
    )
    response = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert response.status_code == 201
    body = response.json()
    assert body["platform"] == "BE"
    assert body["version"] == "BE"
    assert body["name"] == "BE-NO-RN"
    assert body["be_release_id"] == created["id"]
    assert body["swf"] == "BE Nubiral"
    assert body["regresivo_scope"] == "SMOKE"
    assert body["deliverable_name"] == "Core API"
    assert body["qc_resources"] is None
    assert body["validation_type"] is None
    assert body["operativa_release_id"] is None
    assert body["start_date"] is None
    assert body["end_date"] is None
    assert body["execution_days"] is None

    gotten = client.get(f"/api/v1/releases/{body['id']}")
    assert gotten.status_code == 200
    assert gotten.json()["be_release_id"] == created["id"]
    assert gotten.json()["swf"] == "BE Nubiral"


def test_create_qc_release_copies_dates_and_business_days(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    patched = client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={
            "name": "BE-DATES",
            "swf": "BE Hitss",
            "regresivo_scope": "SMOKE",
            "start_date": "2026-09-07",
            "end_date": "2026-09-11",
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["start_date"] == "2026-09-07"
    assert body["end_date"] == "2026-09-11"

    created_qc = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert created_qc.status_code == 201, created_qc.text
    qc = created_qc.json()
    assert qc["start_date"] == "2026-09-07"
    assert qc["end_date"] == "2026-09-11"
    assert qc["execution_days"] == 5


def test_patch_dates_after_create_syncs_qc_release(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"name": "BE-SYNC-DATES", "swf": "BE Neoris", "regresivo_scope": "COMPLETO"},
    )
    qc = client.post(f"/api/v1/releases-be/{created['id']}/create-release").json()
    assert qc["start_date"] is None

    updated = client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"start_date": "2026-09-08", "end_date": "2026-09-09"},
    )
    assert updated.status_code == 200, updated.text
    detail = client.get(f"/api/v1/releases/{qc['id']}").json()
    assert detail["start_date"] == "2026-09-08"
    assert detail["end_date"] == "2026-09-09"
    assert detail["execution_days"] == 2


def test_create_qc_release_is_idempotent(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"name": "BE-ONCE", "swf": "BE Neoris", "regresivo_scope": "COMPLETO"},
    )
    first = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert first.status_code == 201
    second = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert second.status_code == 409
    assert second.json()["detail"] == "Ya existe un Release asociado a este Release BE."


def test_create_qc_release_requires_name_scope_and_swf(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    missing_name = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert missing_name.status_code == 400

    client.patch(f"/api/v1/releases-be/{created['id']}", json={"name": "BE-X"})
    missing_swf = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert missing_swf.status_code == 400
    assert "SWF" in missing_swf.json()["detail"]

    client.patch(f"/api/v1/releases-be/{created['id']}", json={"swf": "BE Hitss"})
    missing_scope = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert missing_scope.status_code == 400


def test_create_qc_release_acotado_requires_component(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"name": "BE-ACOTADO", "swf": "BE Hitss", "regresivo_scope": "ACOTADO"},
    )
    response = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert response.status_code == 400
    assert "Acotado" in response.json()["detail"]


def test_be_release_is_excluded_from_apps_list(client) -> None:
    apps = client.post(
        "/api/v1/releases",
        json={"name": "Claro Video", "version": "8.15", "platform": "tvOS"},
    )
    assert apps.status_code == 201
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"name": "BE-HIDDEN", "swf": "BE Neoris", "regresivo_scope": "SMOKE"},
    )
    qc = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert qc.status_code == 201

    listed = client.get("/api/v1/releases")
    ids = {row["id"] for row in listed.json()}
    assert apps.json()["id"] in ids
    assert qc.json()["id"] not in ids


def test_list_be_releases_includes_created_rows(client) -> None:
    first = client.post("/api/v1/releases-be").json()
    second = client.post("/api/v1/releases-be").json()
    response = client.get("/api/v1/releases-be")
    ids = {row["id"] for row in response.json()}
    assert first["id"] in ids
    assert second["id"] in ids


def test_be_release_not_found(client) -> None:
    assert client.get("/api/v1/releases-be/999999").status_code == 404
    assert client.post("/api/v1/releases-be/999999/create-release").status_code == 404
    assert client.delete("/api/v1/releases-be/999999").status_code == 404


def test_list_be_release_exposes_qc_release_id_after_create(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"name": "BE-OPEN", "swf": "BE Hitss", "regresivo_scope": "SMOKE", "clusters": ["AUP"]},
    )
    qc = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert qc.status_code == 201, qc.text
    listed = client.get("/api/v1/releases-be").json()
    row = next(item for item in listed if item["id"] == created["id"])
    assert row["qc_release_id"] == qc.json()["id"]
    assert row["qc_release_status"] == "DRAFT"
    assert row["clusters"] == ["AUP"]
    detail = client.get(f"/api/v1/releases/{row['qc_release_id']}")
    assert detail.status_code == 200
    assert detail.json()["be_release_id"] == created["id"]
    assert detail.json()["cluster"] == "AUP"


def test_delete_be_draft_without_qc_release(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    sibling = client.post("/api/v1/releases-be").json()
    response = client.delete(f"/api/v1/releases-be/{created['id']}")
    assert response.status_code == 204
    assert client.get(f"/api/v1/releases-be/{created['id']}").status_code == 404
    remaining = client.get("/api/v1/releases-be").json()
    ids = {row["id"] for row in remaining}
    assert created["id"] not in ids
    assert sibling["id"] in ids


def test_delete_be_qc_release_removes_be_row_and_keeps_others(client) -> None:
    keep = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{keep['id']}",
        json={"name": "BE-KEEP", "swf": "BE Neoris", "regresivo_scope": "COMPLETO"},
    )
    keep_qc = client.post(f"/api/v1/releases-be/{keep['id']}/create-release")
    assert keep_qc.status_code == 201

    target = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{target['id']}",
        json={"name": "BE-DROP", "swf": "BE Hitss", "regresivo_scope": "SMOKE", "clusters": ["Todos"]},
    )
    target_qc = client.post(f"/api/v1/releases-be/{target['id']}/create-release")
    assert target_qc.status_code == 201
    release_id = target_qc.json()["id"]

    response = client.delete(f"/api/v1/releases-be/{target['id']}")
    assert response.status_code == 204
    assert client.get(f"/api/v1/releases/{release_id}").status_code == 404
    assert client.get(f"/api/v1/releases-be/{target['id']}").status_code == 404
    remaining = client.get("/api/v1/releases-be").json()
    ids = {row["id"] for row in remaining}
    assert target["id"] not in ids
    assert keep["id"] in ids
    assert client.get(f"/api/v1/releases/{keep_qc.json()['id']}").status_code == 200


def test_delete_be_qc_release_via_release_endpoint_also_removes_be_row(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"name": "BE-VIA-REL", "swf": "BE Nubiral", "regresivo_scope": "SMOKE"},
    )
    qc = client.post(f"/api/v1/releases-be/{created['id']}/create-release").json()
    response = client.delete(f"/api/v1/releases/{qc['id']}")
    assert response.status_code == 204
    assert client.get(f"/api/v1/releases-be/{created['id']}").status_code == 404


def test_can_delete_in_progress_be_release(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"name": "BE-LIVE", "swf": "BE Hitss", "regresivo_scope": "SMOKE"},
    )
    qc = client.post(f"/api/v1/releases-be/{created['id']}/create-release").json()
    client.patch(f"/api/v1/releases/{qc['id']}", json={"status": "IN_PROGRESS"})
    response = client.delete(f"/api/v1/releases/{qc['id']}")
    assert response.status_code == 204
    assert client.get(f"/api/v1/releases/{qc['id']}").status_code == 404
    assert client.get(f"/api/v1/releases-be/{created['id']}").status_code == 404


def test_can_delete_cancelled_be_release(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"name": "BE-CANCELLED", "swf": "BE Hitss", "regresivo_scope": "SMOKE"},
    )
    qc = client.post(f"/api/v1/releases-be/{created['id']}/create-release").json()
    client.patch(f"/api/v1/releases/{qc['id']}", json={"status": "CANCELLED"})
    response = client.delete(f"/api/v1/releases/{qc['id']}")
    assert response.status_code == 204, response.text
    assert client.get(f"/api/v1/releases/{qc['id']}").status_code == 404
    assert client.get(f"/api/v1/releases-be/{created['id']}").status_code == 404
