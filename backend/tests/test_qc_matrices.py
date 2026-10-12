"""QC matrix import, publish, and reversible migration."""

import importlib.util
import json
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.models.release import Release
from tests.conftest import login_as

OTT_PATH = Path("/Users/rodriguezisr/Downloads/qcpulse_matriz_base_ott_v1.2.json")
IPTV_PATH = Path("/Users/rodriguezisr/Downloads/qcpulse_matriz_base_iptv_v1.1(1).json")


def _import(client, path: Path):
    return client.post(
        "/api/v1/qc-matrices/import",
        files={"file": (path.name, path.read_bytes(), "application/json")},
    )


@pytest.mark.skipif(not OTT_PATH.exists() or not IPTV_PATH.exists(), reason="matrix JSON not on this machine")
def test_import_official_matrices_match_file_counts(client) -> None:
    ott = json.loads(OTT_PATH.read_text())
    iptv = json.loads(IPTV_PATH.read_text())

    ott_response = _import(client, OTT_PATH)
    assert ott_response.status_code == 201, ott_response.text
    ott_body = ott_response.json()
    assert ott_body["code"] == "OTT"
    assert ott_body["version"] == "1.2"
    assert ott_body["case_count"] == len(ott["cases"]) == 556
    assert ott_body["module_count"] == len(ott["modules"]) == 41
    assert ott_body["device_count"] == len(ott["devices"]) == 10

    iptv_response = _import(client, IPTV_PATH)
    assert iptv_response.status_code == 201, iptv_response.text
    iptv_body = iptv_response.json()
    assert iptv_body["case_count"] == len(iptv["cases"]) == 208
    assert iptv_body["module_count"] == len(iptv["modules"]) == 34
    assert iptv.get("devices", []) == []
    assert iptv_body["device_count"] == len(iptv["matrix"]["platforms"]) == 1

    again = _import(client, OTT_PATH)
    assert again.status_code == 201
    assert again.json()["id"] == ott_body["id"]
    assert again.json()["case_count"] == 556


def test_publish_republish_keeps_versions_and_release_pin(client, db_session) -> None:
    first = client.post(
        "/api/v1/qc-matrices/import",
        files={"file": ("ott.json", json.dumps(_tiny("OTT", "1.0")).encode(), "application/json")},
    )
    second = client.post(
        "/api/v1/qc-matrices/import",
        files={"file": ("ott.json", json.dumps(_tiny("OTT", "1.1", title="Otro")).encode(), "application/json")},
    )
    assert first.status_code == 201 and second.status_code == 201
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    published = client.post(f"/api/v1/qc-matrices/{first_id}/publish")
    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["published_by"] == "jefe@test.com"

    client.post(f"/api/v1/qc-matrices/{second_id}/publish")
    rows = {row["id"]: row for row in client.get("/api/v1/qc-matrices").json()}
    assert rows[first_id]["status"] == "historical"
    assert rows[second_id]["status"] == "published"

    release = client.post(
        "/api/v1/releases",
        json={"name": "Pinned", "version": "1", "platform": "WEB"},
    ).json()
    stored = db_session.get(Release, release["id"])
    stored.qc_matrix_version_id = first_id
    db_session.commit()

    republished = client.post(f"/api/v1/qc-matrices/{first_id}/publish")
    assert republished.status_code == 200
    rows = {row["id"]: row for row in client.get("/api/v1/qc-matrices").json()}
    assert rows[first_id]["status"] == "published"
    assert rows[second_id]["status"] == "historical"
    assert len(rows) == 2
    pinned = client.get(f"/api/v1/releases/{release['id']}").json()
    assert pinned["qc_matrix_version_id"] == first_id


def test_export_import_round_trip_keeps_cases(client) -> None:
    created = client.post(
        "/api/v1/qc-matrices/import",
        files={"file": ("m.json", json.dumps(_tiny("IPTV", "9.0")).encode(), "application/json")},
    )
    assert created.status_code == 201
    matrix_id = created.json()["id"]
    exported = client.get(f"/api/v1/qc-matrices/{matrix_id}/export")
    assert exported.status_code == 200
    again = client.post(
        "/api/v1/qc-matrices/import",
        files={
            "file": (
                "Matriz_IPTV_v9.0.xlsx",
                exported.content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert again.status_code == 201, again.text
    assert again.json()["id"] == matrix_id
    assert again.json()["case_count"] == 1
    assert again.json()["module_count"] == 1
    detail = client.get(f"/api/v1/qc-matrices/{matrix_id}").json()
    assert detail["cases"][0]["title"] == "Acceso"
    assert detail["cases"][0]["platforms"] == ["WEB"]
    assert detail["cases"][0]["smoke"] is True


def test_case_without_id_is_created_on_reimport(client) -> None:
    payload = _tiny("OTT", "2.0")
    payload["cases"][0]["id"] = ""
    first = client.post(
        "/api/v1/qc-matrices/import",
        files={"file": ("m.json", json.dumps(payload).encode(), "application/json")},
    )
    second = client.post(
        "/api/v1/qc-matrices/import",
        files={"file": ("m.json", json.dumps(payload).encode(), "application/json")},
    )
    assert first.json()["case_count"] == 1
    assert second.json()["case_count"] == 2
    assert second.json()["id"] == first.json()["id"]


def test_tester_cannot_import(client) -> None:
    login_as(client, "tester@test.com", "tester-pass")
    response = client.post(
        "/api/v1/qc-matrices/import",
        files={"file": ("m.json", json.dumps(_tiny("OTT", "3.0")).encode(), "application/json")},
    )
    assert response.status_code == 403


def test_qc_matrix_migration_applies_reverts_and_applies() -> None:
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0030_qc_matrices.py"
    spec = importlib.util.spec_from_file_location("qc_matrix_migration_0030", path)
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
    names = set(inspect(engine).get_table_names())
    assert "qc_matrix_versions" in names
    assert "qc_matrix_cases" in names
    release_columns = {column["name"] for column in inspect(engine).get_columns("releases")}
    assert "qc_matrix_version_id" in release_columns


def _tiny(code: str, version: str, title: str = "Acceso") -> dict:
    return {
        "matrix": {"code": code, "version": version, "name": f"Matriz {code}", "generated": "2026-10-12", "platforms": ["WEB"]},
        "providers": [],
        "scope_rules": {},
        "modules": [{"id": "ACC", "group": "Acceso", "name": "Acceso", "description": "", "related": []}],
        "devices": [{"code": "WEB", "label": "Web", "screen": "Pantallas medianas", "mdp_mx": ["TDC"], "mdp_other_regions": []}],
        "cases": [
            {
                "id": f"{code}-ACC-001",
                "module_id": "ACC",
                "title": title,
                "steps": "1. Abrir",
                "expected": "Se ve el home",
                "severity": "Blocker",
                "smoke": True,
                "platforms": ["WEB"],
                "region": "Todas",
                "platform_notes": ["[WEB] Entrar por el home"],
                "user_types": ["Anónimo"],
                "status": "Listo",
                "sources": [],
            }
        ],
    }
