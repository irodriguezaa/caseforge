from app.models.test_case import TestCase, TestCaseStatus
from tests.conftest import login_as
from tests.test_test_cases import _create_release


def _create_case(client, release_id: int, case_id: str, component: str, **extra) -> dict:
    payload = {
        "test_case_id": case_id,
        "component": component,
        "test_case_name": f"Case {case_id}",
        **extra,
    }
    response = client.post(f"/api/v1/releases/{release_id}/test-cases", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_bulk_status_updates_only_selected_ids(client) -> None:
    release = _create_release(client)
    epic = [_create_case(client, release["id"], f"QC-{i:03d}", "WEBCL-2424") for i in range(1, 11)]
    other = [_create_case(client, release["id"], f"QC-X{i}", "ADTCL-141") for i in range(1, 6)]
    ids = [row["id"] for row in epic]

    response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases/bulk-status",
        json={"ids": ids, "status": "PASS"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["failed"] == []
    assert set(body["updated"]) == set(ids)
    assert body["status"] == "PASS"

    listed = client.get(f"/api/v1/releases/{release['id']}/test-cases").json()
    by_id = {row["id"]: row for row in listed}
    for row in epic:
        assert by_id[row["id"]]["status"] == "PASS"
        assert by_id[row["id"]]["component"] == "WEBCL-2424"
        assert by_id[row["id"]]["priority"] == "CRITICAL"
        assert by_id[row["id"]]["test_case_name"] == row["test_case_name"]
    for row in other:
        assert by_id[row["id"]]["status"] == "UNEXECUTED"


def test_bulk_status_rejects_invalid_status(client) -> None:
    release = _create_release(client)
    case = _create_case(client, release["id"], "QC-001", "WEBCL-2424")
    response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases/bulk-status",
        json={"ids": [case["id"]], "status": "DONE"},
    )
    assert response.status_code == 422
    refreshed = client.get(f"/api/v1/test-cases/{case['id']}").json()
    assert refreshed["status"] == "UNEXECUTED"


def test_bulk_status_consulta_forbidden(client) -> None:
    release = _create_release(client)
    case = _create_case(client, release["id"], "QC-001", "Playback")
    login_as(client, "consulta@test.com", "consulta-pass")
    response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases/bulk-status",
        json={"ids": [case["id"]], "status": "PASS"},
    )
    assert response.status_code == 403
    login_as(client, "jefe@test.com", "jefe-pass")
    refreshed = client.get(f"/api/v1/test-cases/{case['id']}").json()
    assert refreshed["status"] == "UNEXECUTED"


def test_bulk_status_partial_errors_do_not_claim_total_success(client) -> None:
    release_a = _create_release(client, name="Release A")
    release_b = _create_release(client, name="Release B")
    local = _create_case(client, release_a["id"], "QC-001", "WEBCL-2424")
    foreign = _create_case(client, release_b["id"], "QC-002", "WEBCL-2424")

    response = client.post(
        f"/api/v1/releases/{release_a['id']}/test-cases/bulk-status",
        json={"ids": [local["id"], foreign["id"], 999_999, local["id"]], "status": "FAIL"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == [local["id"]]
    assert {item["id"] for item in body["failed"]} == {foreign["id"], 999_999}
    assert all("Release" in item["message"] or "not found" in item["message"].lower() for item in body["failed"])
    assert client.get(f"/api/v1/test-cases/{foreign['id']}").json()["status"] == "UNEXECUTED"
    assert client.get(f"/api/v1/test-cases/{local['id']}").json()["status"] == "FAIL"


def test_bulk_delete_selected_only(client) -> None:
    release = _create_release(client)
    keep = _create_case(client, release["id"], "QC-KEEP", "ADTCL-141")
    remove = [
        _create_case(client, release["id"], f"QC-{i:03d}", "WEBCL-2424")
        for i in range(1, 4)
    ]
    response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases/bulk-delete",
        json={"ids": [row["id"] for row in remove]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["failed"] == []
    assert set(body["deleted"]) == {row["id"] for row in remove}
    remaining = client.get(f"/api/v1/releases/{release['id']}/test-cases").json()
    assert [row["id"] for row in remaining] == [keep["id"]]


def test_bulk_delete_rejects_other_release_and_invalid_ids(client) -> None:
    release_a = _create_release(client, name="Release A")
    release_b = _create_release(client, name="Release B")
    local = _create_case(client, release_a["id"], "QC-001", "Playback")
    foreign = _create_case(client, release_b["id"], "QC-002", "Playback")

    response = client.post(
        f"/api/v1/releases/{release_a['id']}/test-cases/bulk-delete",
        json={"ids": [local["id"], foreign["id"], 42]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["deleted"] == [local["id"]]
    assert {item["id"] for item in body["failed"]} == {foreign["id"], 42}
    assert client.get(f"/api/v1/test-cases/{foreign['id']}").status_code == 200
    assert client.get(f"/api/v1/test-cases/{local['id']}").status_code == 404


def test_bulk_delete_consulta_forbidden(client) -> None:
    release = _create_release(client)
    case = _create_case(client, release["id"], "QC-001", "Playback")
    login_as(client, "consulta@test.com", "consulta-pass")
    response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases/bulk-delete",
        json={"ids": [case["id"]]},
    )
    assert response.status_code == 403
    login_as(client, "jefe@test.com", "jefe-pass")
    assert client.get(f"/api/v1/test-cases/{case['id']}").status_code == 200


def test_bulk_empty_ids_rejected(client) -> None:
    release = _create_release(client)
    status_response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases/bulk-status",
        json={"ids": [], "status": "PASS"},
    )
    delete_response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases/bulk-delete",
        json={"ids": []},
    )
    assert status_response.status_code == 422
    assert delete_response.status_code == 422


def test_individual_patch_and_delete_still_work(client, db_session) -> None:
    release = _create_release(client)
    case = _create_case(client, release["id"], "QC-001", "Playback", description="keep-me")
    patched = client.patch(f"/api/v1/test-cases/{case['id']}", json={"status": "BLOCKED"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "BLOCKED"
    assert patched.json()["description"] == "keep-me"
    stored = db_session.get(TestCase, case["id"])
    assert stored is not None
    assert stored.status == TestCaseStatus.BLOCKED
    assert stored.description == "keep-me"
    assert client.delete(f"/api/v1/test-cases/{case['id']}").status_code == 204
