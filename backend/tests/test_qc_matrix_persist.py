"""Matrix cases become Release test cases without touching RN generation."""

import json

from app.models.release import Release
from app.models.test_case import TestCase, TestCaseStatus
from app.services.case_persistence import next_test_case_id
from app.services.qc_matrix_persist import persist_selected_matrix_cases


def _matrix() -> dict:
    return {
        "matrix": {"code": "OTT", "version": "1.2", "name": "Mini", "generated": "2026-10-12"},
        "providers": ["HBO Max"],
        "modules": [
            {"id": "ACC", "group": "Acceso", "name": "Inicio de sesión", "description": "", "related": []},
            {"id": "NAV", "group": "Navegación", "name": "Home", "description": "", "related": []},
        ],
        "devices": [
            {"code": "WEB", "label": "Web", "screen": "Medianas", "mdp_mx": ["TDC"], "mdp_other_regions": []},
        ],
        "cases": [
            {
                "id": "ACC-1",
                "module_id": "ACC",
                "title": "Login del socio",
                "steps": "1. Abrir la app\n2. Iniciar sesión",
                "expected": "Queda autenticado",
                "severity": "Blocker",
                "smoke": False,
                "platforms": ["WEB"],
                "region": "MX",
                "user_types": ["Socio"],
                "platform_notes": ["[WEB] Solo Chrome"],
                "status": "Listo",
                "sources": [],
            },
            {
                "id": "NAV-1",
                "module_id": "NAV",
                "title": "Abrir home",
                "steps": "",
                "expected": "Se ve el home",
                "severity": "Critical",
                "smoke": True,
                "platforms": ["WEB"],
                "region": "Todas",
                "user_types": [],
                "status": "Listo",
                "sources": [],
            },
        ],
    }


def _publish(client) -> None:
    created = client.post(
        "/api/v1/qc-matrices/import",
        files={"file": ("mini.json", json.dumps(_matrix()).encode(), "application/json")},
    )
    assert created.status_code == 201, created.text
    published = client.post(f"/api/v1/qc-matrices/{created.json()['id']}/publish")
    assert published.status_code == 200, published.text


def _release(client, validation_type: str, modules: list[str], cluster: str = "AUP") -> dict:
    created = client.post(
        "/api/v1/releases",
        json={
            "name": f"Matriz {validation_type}",
            "version": "1",
            "platform": "WEB",
            "cluster": cluster,
            "validation_type": validation_type,
            "qc_matrix_touched_modules": modules,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_matrix_cases_get_their_own_ids_and_keep_na(client, db_session) -> None:
    _publish(client)
    release = _release(client, "Regresivo", ["ACC", "NAV"])
    manual = client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={
            "test_case_id": "QC-001",
            "component": "RN",
            "test_case_name": "Caso del RN",
            "priority": "CRITICAL",
            "test_type": "FUNCTIONAL",
            "source_type": "functionality",
            "generated_by_engine": True,
        },
    )
    assert manual.status_code == 201, manual.text

    stored = db_session.get(Release, release["id"])
    assert persist_selected_matrix_cases(db_session, stored) == 2
    db_session.commit()

    rows = client.get(f"/api/v1/releases/{release['id']}/test-cases").json()
    by_label = {row["test_case_id"]: row for row in rows}
    assert "QC-001" in by_label
    assert by_label["QC-001"]["source_type"] == "functionality"
    matrix_rows = [row for row in rows if row["source_type"] == "qc_matrix"]
    assert [row["test_case_id"] for row in matrix_rows] == ["RG-001", "RG-002"]
    assert next_test_case_id([row["test_case_id"] for row in rows]) == "QC-002"

    login = next(row for row in matrix_rows if row["technical_story"] == "ACC-1")
    assert login["component"] == "Inicio de sesión"
    assert login["test_case_name"] == "Login del socio (Solo Chrome)"
    assert login["priority"] == "BLOCKER"
    assert login["test_type"] == "FUNCTIONAL"
    assert login["status"] == "UNEXECUTED"
    assert login["generated_by_engine"] is False
    detail = client.get(f"/api/v1/test-cases/{login['id']}").json()
    assert [step["test_step"] for step in detail["steps"]] == ["Abrir la app", "Iniciar sesión"]
    assert detail["steps"][0]["expected_result"] == "—"
    assert detail["steps"][1]["expected_result"] == "Queda autenticado"
    assert "Matriz OTT 1.2" in (detail["scenario_origin"] or "")
    assert "ACC-1" in (detail["scenario_origin"] or "")
    assert "Socio" in (detail["test_data"] or "")
    assert "Cluster: AUP" in (detail["test_data"] or "")
    assert "México" not in (detail["test_data"] or "")

    home = next(row for row in matrix_rows if row["technical_story"] == "NAV-1")
    home_detail = client.get(f"/api/v1/test-cases/{home['id']}").json()
    assert home_detail["steps"][0]["test_step"] == "Ejecutar: Abrir home"
    assert home_detail["priority"] == "CRITICAL"

    marked = client.patch(f"/api/v1/test-cases/{login['id']}", json={"status": "N_A"})
    assert marked.status_code == 200, marked.text
    db_session.expire_all()
    again = db_session.get(Release, release["id"])
    again.qc_matrix_touched_modules = ["ACC"]
    db_session.commit()
    assert persist_selected_matrix_cases(db_session, again) == 1
    db_session.commit()
    kept = db_session.get(TestCase, login["id"])
    assert kept is not None
    assert kept.status == TestCaseStatus.N_A
    assert kept.test_case_id == "RG-001"
    remaining = client.get(f"/api/v1/releases/{release['id']}/test-cases").json()
    assert [row["test_case_id"] for row in remaining if row["source_type"] == "qc_matrix"] == ["RG-001"]
    assert any(row["test_case_id"] == "QC-001" for row in remaining)


def _matrix_rows(client, release_id: int) -> list[dict]:
    rows = client.get(f"/api/v1/releases/{release_id}/test-cases").json()
    return [row for row in rows if row["source_type"] == "qc_matrix"]


def test_generating_twice_does_not_duplicate_matrix_cases(client, db_session) -> None:
    _publish(client)
    release = _release(client, "Regresivo", ["ACC", "NAV"])
    stored = db_session.get(Release, release["id"])
    assert persist_selected_matrix_cases(db_session, stored) == 2
    db_session.commit()
    first = [row["test_case_id"] for row in _matrix_rows(client, release["id"])]

    db_session.expire_all()
    again = db_session.get(Release, release["id"])
    assert persist_selected_matrix_cases(db_session, again) == 2
    db_session.commit()
    second = [row["test_case_id"] for row in _matrix_rows(client, release["id"])]
    assert second == first == ["RG-001", "RG-002"]


def test_changing_scope_replaces_unexecuted_matrix_cases(client, db_session) -> None:
    _publish(client)
    release = _release(client, "Regresivo", ["ACC", "NAV"])
    stored = db_session.get(Release, release["id"])
    assert persist_selected_matrix_cases(db_session, stored) == 2
    db_session.commit()

    db_session.expire_all()
    changed = db_session.get(Release, release["id"])
    changed.validation_type = "No Afectación"
    changed.qc_matrix_touched_modules = ["ACC"]
    db_session.commit()
    assert persist_selected_matrix_cases(db_session, changed) == 1
    db_session.commit()

    rows = _matrix_rows(client, release["id"])
    assert [row["test_case_id"] for row in rows] == ["NF-001"]
    assert rows[0]["technical_story"] == "NAV-1"
    assert rows[0]["status"] == "UNEXECUTED"


def test_regenerate_keeps_executed_matrix_cases(client, db_session) -> None:
    _publish(client)
    release = _release(client, "Regresivo", ["ACC", "NAV"])
    stored = db_session.get(Release, release["id"])
    assert persist_selected_matrix_cases(db_session, stored) == 2
    db_session.commit()
    rows = _matrix_rows(client, release["id"])
    login = next(row for row in rows if row["technical_story"] == "ACC-1")
    home = next(row for row in rows if row["technical_story"] == "NAV-1")
    assert client.patch(f"/api/v1/test-cases/{login['id']}", json={"status": "PASS"}).status_code == 200
    assert client.patch(f"/api/v1/test-cases/{home['id']}", json={"status": "FAIL"}).status_code == 200

    db_session.expire_all()
    same_scope = db_session.get(Release, release["id"])
    assert persist_selected_matrix_cases(db_session, same_scope) == 2
    db_session.commit()
    kept = {row["test_case_id"]: row["status"] for row in _matrix_rows(client, release["id"])}
    assert kept == {"RG-001": "PASS", "RG-002": "FAIL"}

    assert client.patch(f"/api/v1/test-cases/{login['id']}", json={"status": "BLOCKED"}).status_code == 200
    assert client.patch(f"/api/v1/test-cases/{home['id']}", json={"status": "N_A"}).status_code == 200
    db_session.expire_all()
    other_scope = db_session.get(Release, release["id"])
    other_scope.validation_type = "Smoke Test"
    db_session.commit()
    assert persist_selected_matrix_cases(db_session, other_scope) == 1
    db_session.commit()
    after = {row["test_case_id"]: row["status"] for row in _matrix_rows(client, release["id"])}
    assert after == {"RG-001": "BLOCKED", "RG-002": "N_A"}


def test_be_create_persists_matrix_cases_per_device(client) -> None:
    _publish(client)
    created = client.post("/api/v1/releases-be").json()
    patched = client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"name": "BE-MATRIX", "swf": "BE Hitss", "regresivo_scope": "Smoke Test"},
    )
    assert patched.status_code == 200, patched.text
    qc = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert qc.status_code == 201, qc.text
    assert qc.json()["validation_type"] == "Smoke Test"
    rows = client.get(f"/api/v1/releases/{qc.json()['id']}/test-cases").json()
    matrix_rows = [row for row in rows if row["source_type"] == "qc_matrix"]
    assert [row["test_case_id"] for row in matrix_rows] == ["SM-001"]
    assert matrix_rows[0]["device"] == "WEB"
    assert "Dispositivo: WEB" in (matrix_rows[0]["test_data"] or "")


def test_generate_be_release_loads_matrix_after_create(client) -> None:
    created = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{created['id']}",
        json={"name": "BE-GENERATE", "swf": "BE Hitss", "regresivo_scope": "Smoke Test"},
    )
    qc = client.post(f"/api/v1/releases-be/{created['id']}/create-release")
    assert qc.status_code == 201, qc.text
    assert client.get(f"/api/v1/releases/{qc.json()['id']}/test-cases").json() == []

    _publish(client)
    generated = client.post(f"/api/v1/releases/{qc.json()['id']}/generate-cases?background=true")
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body["status"] == "DONE"
    assert body["engine"] == "qc_matrix"
    assert body["test_case_count"] == 1
    rows = client.get(f"/api/v1/releases/{qc.json()['id']}/test-cases").json()
    matrix_rows = [row for row in rows if row["source_type"] == "qc_matrix"]
    assert [row["test_case_id"] for row in matrix_rows] == ["SM-001"]
    assert matrix_rows[0]["device"] == "WEB"


def test_na_scope_does_not_persist_matrix_cases(client, db_session) -> None:
    _publish(client)
    release = _release(client, "N/A", ["ACC"])
    stored = db_session.get(Release, release["id"])
    assert persist_selected_matrix_cases(db_session, stored) == 0
    rows = client.get(f"/api/v1/releases/{release['id']}/test-cases").json()
    assert rows == []
