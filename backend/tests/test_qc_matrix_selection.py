"""Scope selection against a published QC matrix. No RN generation and no dedup."""

import json

from app.models.release import Release


def _matrix() -> dict:
    return {
        "matrix": {"code": "OTT", "version": "1.0", "name": "Mini", "generated": "2026-10-12"},
        "providers": ["HBO Max"],
        "modules": [
            {"id": "ACC", "group": "Acceso", "name": "Inicio de sesión", "description": "", "related": ["COM-TX"]},
            {"id": "COM-TX", "group": "Comercial", "name": "Transacciones", "description": "", "related": []},
            {"id": "NAV", "group": "Navegación", "name": "Home", "description": "", "related": []},
        ],
        "devices": [
            {"code": "WEB", "label": "Web", "screen": "Pantallas medianas", "mdp_mx": ["TDC"], "mdp_other_regions": []},
            {"code": "WIN", "label": "Windows", "screen": "Pantallas medianas", "mdp_mx": [], "mdp_other_regions": []},
        ],
        "cases": [
            _case("NAV-SMK", "NAV", "Smoke del home", smoke=True, platforms=["WEB"]),
            _case("ACC-1", "ACC", "Login de checkout", platforms=["WEB"]),
            _case("TX-1", "COM-TX", "Pagar con {MDP} en {PROVEEDOR}", platforms=["WEB"]),
            _case("TX-WIN", "COM-TX", "Pagar con {MDP}", platforms=["WIN"]),
            _case("NAV-WIN", "NAV", "Home en Windows", platforms=["WIN"]),
            _case("ACC-OTRA", "ACC", "Login otras regiones", platforms=["WEB"], region="Otras regiones"),
            _case("NAV-MX", "NAV", "Home México", platforms=["WEB"], region="MX", smoke=False),
        ],
    }


def _case(
    base_id: str,
    module_id: str,
    title: str,
    *,
    smoke: bool = False,
    platforms: list[str],
    region: str = "Todas",
    steps: str = "1. Abrir",
) -> dict:
    return {
        "id": base_id,
        "module_id": module_id,
        "title": title,
        "steps": steps,
        "expected": "Se observa el resultado",
        "severity": "Critical",
        "smoke": smoke,
        "platforms": platforms,
        "region": region,
        "user_types": [],
        "status": "Listo",
        "sources": [],
    }


def _publish(client) -> int:
    created = client.post(
        "/api/v1/qc-matrices/import",
        files={"file": ("mini.json", json.dumps(_matrix()).encode(), "application/json")},
    )
    assert created.status_code == 201, created.text
    matrix_id = created.json()["id"]
    published = client.post(f"/api/v1/qc-matrices/{matrix_id}/publish")
    assert published.status_code == 200
    return matrix_id


def test_scope_filters_device_region_and_templates(client) -> None:
    matrix_id = _publish(client)
    analysis = {"normalized": {"technical_epics": [{"id": "E-1", "title": "La sesión del socio falla"}]}}

    smoke = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "WEB", "validation_type": "Smoke Test", "raw_analysis": analysis},
    )
    assert smoke.status_code == 200, smoke.text
    assert [row["base_id"] for row in smoke.json()["cases"]] == ["NAV-SMK"]
    assert smoke.json()["show_module_selector"] is False

    regresivo = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "WEB", "validation_type": "Regresivo", "raw_analysis": analysis},
    ).json()
    assert regresivo["suggested_modules"] == ["ACC"]
    assert regresivo["suggestions"][0]["matched_words"] == ["sesión"]
    assert regresivo["related_modules"] == ["COM-TX"]
    assert regresivo["show_module_selector"] is True
    assert regresivo["impact_summary"] == "Se agregarán 2 casos de 2 módulos (1 tocado + 1 relacionado)."
    assert {row["base_id"] for row in regresivo["cases"]} == {"ACC-1", "TX-1"}
    paid = next(row for row in regresivo["cases"] if row["base_id"] == "TX-1")
    assert paid["title"] == "Pagar con TDC en HBO Max"
    assert "ACC-OTRA" not in {row["base_id"] for row in regresivo["cases"]}

    no_afectacion = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "WEB", "validation_type": "No Afectación", "touched_modules": ["ACC"], "raw_analysis": analysis},
    ).json()
    completa = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "WEB", "validation_type": "Regresión completa", "touched_modules": ["ACC"], "raw_analysis": analysis},
    ).json()
    union = {row["base_id"] for row in regresivo["cases"]} | {row["base_id"] for row in no_afectacion["cases"]}
    # Regresivo above used the suggestion, which is also ACC. Recompute regresivo with the same explicit list.
    regresivo_explicit = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "WEB", "validation_type": "Regresivo", "touched_modules": ["ACC"]},
    ).json()
    union = {row["base_id"] for row in regresivo_explicit["cases"]} | {row["base_id"] for row in no_afectacion["cases"]}
    assert {row["base_id"] for row in completa["cases"]} == union
    assert completa["show_module_selector"] is False
    assert "ACC-OTRA" not in union

    acotadas = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "WEB", "validation_type": "Pruebas Acotadas"},
    ).json()
    assert acotadas["case_count"] == 0
    picked = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "WEB", "validation_type": "Pruebas Acotadas", "touched_modules": ["ACC"]},
    ).json()
    assert [row["base_id"] for row in picked["cases"]] == ["ACC-1"]

    windows = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "WIN/XBOX", "validation_type": "Regresión completa", "touched_modules": ["ACC", "COM-TX", "NAV"]},
    ).json()
    assert [row["base_id"] for row in windows["cases"]] == ["NAV-WIN"]
    assert windows["transactions_included"] is False

    nada = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "WEB", "validation_type": "N/A"},
    ).json()
    assert nada["case_count"] == 0

    release = client.post(
        "/api/v1/releases",
        json={"name": "Scope", "version": "1", "platform": "WEB", "validation_type": "Smoke Test"},
    ).json()
    assert release["qc_matrix_version_id"] == matrix_id


def test_no_afectacion_recalculates_when_touched_modules_change(client) -> None:
    _publish(client)

    def preview(touched: list[str]) -> dict:
        response = client.post(
            "/api/v1/qc-matrices/preview",
            json={"platform": "WEB", "validation_type": "No Afectación", "touched_modules": touched},
        )
        assert response.status_code == 200, response.text
        return response.json()

    only_acc = preview(["ACC"])
    only_acc_ids = {row["base_id"] for row in only_acc["cases"]}
    assert "ACC-1" not in only_acc_ids
    assert "TX-1" in only_acc_ids
    assert only_acc["related_modules"] == ["COM-TX"]
    assert only_acc["case_count"] == 3
    assert only_acc["impact_summary"] == "Se agregarán 3 casos de los 2 módulos no relacionados con el cambio."

    with_nav = preview(["ACC", "NAV"])
    assert {row["base_id"] for row in with_nav["cases"]} == {"TX-1"}
    assert with_nav["case_count"] == 1
    assert with_nav["impact_summary"] == "Se agregará 1 caso de los 1 módulo no relacionados con el cambio."
    assert with_nav["impact_summary"] != only_acc["impact_summary"]
    assert with_nav["case_count"] != only_acc["case_count"]

    removed = preview(["ACC"])
    assert removed["case_count"] == only_acc["case_count"]
    assert removed["impact_summary"] == only_acc["impact_summary"]


def test_player_suggestion_providers_and_kepler(client) -> None:
    payload = {
        "matrix": {"code": "OTT", "version": "1.2", "name": "Player", "generated": "2026-10-12"},
        "providers": ["HBO Max", "Paramount+"],
        "modules": [
            {"id": "REP-VOD", "group": "Acceso", "name": "Player VOD", "description": "", "related": ["VCARD"]},
            {"id": "VCARD", "group": "Reproducción", "name": "VCard", "description": "", "related": []},
            {"id": "ACC", "group": "Reproducción", "name": "Inicio de sesión", "description": "", "related": []},
        ],
        "devices": [
            {"code": "iOS", "label": "iOS", "screen": "Chicas", "mdp_mx": ["iTunes", "PayPal"], "mdp_other_regions": []},
            {"code": "FTV", "label": "FireTV", "screen": "Grandes", "mdp_mx": ["Amazon"], "mdp_other_regions": []},
        ],
        "cases": [
            _case("PLAY-1", "REP-VOD", "Reproducir VOD", platforms=["iOS", "FTV"], steps="1. Abrir {PROVEEDOR}"),
            _case("PLAY-PKG", "REP-VOD", "Contratar {PAQUETE}", platforms=["iOS", "FTV"]),
            _case("VC-1", "VCARD", "Abrir ficha", platforms=["iOS", "FTV"]),
            _case("ACC-1", "ACC", "Login", platforms=["iOS", "FTV"]),
        ],
    }
    created = client.post(
        "/api/v1/qc-matrices/import",
        files={"file": ("player.json", json.dumps(payload).encode(), "application/json")},
    )
    assert created.status_code == 201, created.text
    assert client.post(f"/api/v1/qc-matrices/{created.json()['id']}/publish").status_code == 200
    analysis = {"normalized": {"technical_epics": [{"id": "IOSPR-1", "title": "El player no reproduce el contenido"}]}}

    preview = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "iOS", "validation_type": "Regresivo", "raw_analysis": analysis},
    ).json()
    assert preview["suggested_modules"] == ["REP-VOD"]
    assert preview["suggestions"][0]["matched_words"] == ["player"]
    assert preview["related_modules"] == ["VCARD"]
    titles = [row["title"] for row in preview["cases"]]
    assert titles.count("Reproducir VOD — HBO Max") == 1
    assert titles.count("Reproducir VOD — Paramount+") == 1
    package = next(row for row in preview["cases"] if row["base_id"] == "PLAY-PKG")
    assert package["title"] == "Contratar {PAQUETE}"
    assert package["pending_templates"] == []
    assert "Login" not in titles

    only_player = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "iOS", "validation_type": "Regresivo", "touched_modules": ["REP-VOD"], "raw_analysis": analysis},
    ).json()
    none_touched = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "iOS", "validation_type": "Regresivo", "touched_modules": [], "raw_analysis": analysis},
    ).json()
    with_login = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "iOS", "validation_type": "Regresivo", "touched_modules": ["REP-VOD", "ACC"], "raw_analysis": analysis},
    ).json()
    assert none_touched["case_count"] < only_player["case_count"] < with_login["case_count"]

    override = client.post(
        "/api/v1/qc-matrices/preview",
        json={
            "platform": "iOS",
            "validation_type": "Pruebas Acotadas",
            "touched_modules": ["REP-VOD"],
            "template_values": {"PROVEEDOR": "Disney+"},
        },
    ).json()
    assert [row["title"] for row in override["cases"] if row["base_id"] == "PLAY-1"] == ["Reproducir VOD — Disney+"]
    assert override["show_module_selector"] is True

    fire = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "FireTV", "validation_type": "Regresión completa"},
    ).json()
    kepler = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "Kepler", "validation_type": "Regresión completa"},
    ).json()
    assert [(row["base_id"], row["title"]) for row in kepler["cases"]] == [(row["base_id"], row["title"]) for row in fire["cases"]]
    assert kepler["device_code"] == "FTV"
    assert fire["show_module_selector"] is False
    assert kepler["show_module_selector"] is False

    tata = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "STV Tata Samsung", "validation_type": "Regresivo", "raw_analysis": analysis},
    ).json()
    assert tata["case_count"] == 0
    assert "no tienen columna" in tata["note"]


def test_saved_modules_stay_on_the_pinned_version(client, db_session) -> None:
    first = _publish(client)
    newer = client.post(
        "/api/v1/qc-matrices/import",
        files={"file": ("mini.json", json.dumps({**_matrix(), "matrix": {**_matrix()["matrix"], "version": "2.0"}}).encode(), "application/json")},
    )
    assert newer.status_code == 201
    client.post(f"/api/v1/qc-matrices/{newer.json()['id']}/publish")

    release = client.post(
        "/api/v1/releases",
        json={"name": "Pinned scope", "version": "1", "platform": "WEB"},
    ).json()
    # Created while 2.0 is published, so it pins 2.0. Move the pin back to 1.0 and republish 2.0.
    stored = db_session.get(Release, release["id"])
    stored.qc_matrix_version_id = first
    db_session.commit()
    client.post(f"/api/v1/qc-matrices/{newer.json()['id']}/publish")

    saved = client.post(
        f"/api/v1/qc-matrices/releases/{release['id']}/selection",
        json={"touched_modules": ["NAV"], "template_values": {"PROVEEDOR": "HBO Max"}},
    )
    assert saved.status_code == 200, saved.text
    body = client.get(f"/api/v1/releases/{release['id']}").json()
    assert body["qc_matrix_version_id"] == first
    assert body["qc_matrix_touched_modules"] == ["NAV"]
    preview = client.post("/api/v1/qc-matrices/preview", json={"release_id": release["id"], "validation_type": "Regresivo"}).json()
    assert preview["matrix_version_id"] == first
    assert preview["touched_modules"] == ["NAV"]


def test_selection_columns_migration_is_reversible() -> None:
    import importlib.util
    from pathlib import Path

    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine, inspect, text

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0031_qc_matrix_selection.py"
    spec = importlib.util.spec_from_file_location("qc_matrix_migration_0031", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE releases (id INTEGER PRIMARY KEY)"))

    def run(direction: str) -> None:
        with engine.begin() as conn:
            context = MigrationContext.configure(conn)
            with Operations.context(context):
                getattr(migration, direction)()

    run("upgrade")
    run("downgrade")
    run("upgrade")
    columns = {column["name"] for column in inspect(engine).get_columns("releases")}
    assert "qc_matrix_touched_modules" in columns
    assert "qc_matrix_template_values" in columns


def test_be_preview_unions_unique_mapped_devices(client) -> None:
    _publish(client)
    preview = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "BE", "validation_type": "Smoke Test"},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["platform"] == "BE"
    assert body["device_code"] == "ALL"
    assert [row["base_id"] for row in body["cases"]] == ["NAV-SMK"]
    assert body["cases"][0]["device_code"] == "WEB"
    assert "dispositivos" in body["impact_summary"]
    assert body["show_module_selector"] is False

    acotadas = client.post(
        "/api/v1/qc-matrices/preview",
        json={"platform": "BE", "validation_type": "Pruebas Acotadas", "touched_modules": ["NAV"]},
    )
    assert acotadas.status_code == 200, acotadas.text
    ids = {(row["base_id"], row["device_code"]) for row in acotadas.json()["cases"]}
    assert ("NAV-SMK", "WEB") in ids
    assert ("NAV-MX", "WEB") in ids
    assert ("NAV-WIN", "WIN") in ids
    assert acotadas.json()["show_module_selector"] is True
