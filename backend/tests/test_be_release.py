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
    assert body["swf"] == "Neoris"
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
            "swf": "Hitss",
            "description": "Notas de alcance",
            "regresivo_scope": "ACOTADO",
            "affected_component": "Login",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["entregable"] == "Billing API"
    assert body["name"] == "BE-BILLING"
    assert body["swf"] == "Hitss"
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


def test_create_qc_release_without_pdf(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"name": "BE-NO-RN", "entregable": "Core API", "swf": "Tata", "regresivo_scope": "SMOKE"},
    )
    response = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert response.status_code == 201
    body = response.json()
    assert body["platform"] == "BE"
    assert body["version"] == "BE"
    assert body["name"] == "BE-NO-RN"
    assert body["be_release_id"] == created["id"]
    assert body["swf"] == "Tata"
    assert body["regresivo_scope"] == "SMOKE"
    assert body["deliverable_name"] == "Core API"
    assert body["qc_resources"] is None
    assert body["validation_type"] is None
    assert body["operativa_release_id"] is None

    gotten = client.get(f"/api/v1/releases/{body['id']}")
    assert gotten.status_code == 200
    assert gotten.json()["be_release_id"] == created["id"]
    assert gotten.json()["swf"] == "Tata"


def test_create_qc_release_is_idempotent(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"name": "BE-ONCE", "regresivo_scope": "COMPLETO"},
    )
    first = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert first.status_code == 201
    second = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert second.status_code == 409
    assert second.json()["detail"] == "Ya existe un Release asociado a este Release BE."


def test_create_qc_release_requires_name_and_scope(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    missing_name = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert missing_name.status_code == 400

    client.patch(f"/api/v1/releases-be/{created['id']}", json={"name": "BE-X"})
    missing_scope = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert missing_scope.status_code == 400


def test_create_qc_release_acotado_requires_component(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"name": "BE-ACOTADO", "regresivo_scope": "ACOTADO"},
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
        json={"name": "BE-HIDDEN", "regresivo_scope": "SMOKE"},
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
