def _create_test_case(client) -> dict:
    release = client.post(
        "/api/v1/releases", json={"name": "Claro Video", "version": "8.15", "platform": "tvOS"}
    ).json()
    return client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "Playback", "test_case_name": "Case A"},
    ).json()


def test_create_defect_for_test_case(client) -> None:
    test_case = _create_test_case(client)

    response = client.post(
        f"/api/v1/test-cases/{test_case['id']}/defects",
        json={"title": "Crash on play", "severity": "CRITICAL"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "OPEN"
    assert body["test_case_id"] == test_case["id"]


def test_list_defects_for_test_case(client) -> None:
    test_case = _create_test_case(client)
    client.post(f"/api/v1/test-cases/{test_case['id']}/defects", json={"title": "A", "severity": "BLOCKER"})
    client.post(f"/api/v1/test-cases/{test_case['id']}/defects", json={"title": "B", "severity": "CRITICAL"})

    response = client.get(f"/api/v1/test-cases/{test_case['id']}/defects")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_update_defect_status(client) -> None:
    test_case = _create_test_case(client)
    defect = client.post(
        f"/api/v1/test-cases/{test_case['id']}/defects", json={"title": "A", "severity": "BLOCKER"}
    ).json()

    response = client.patch(f"/api/v1/defects/{defect['id']}", json={"status": "CLOSED"})

    assert response.status_code == 200
    assert response.json()["status"] == "CLOSED"


def test_deleting_test_case_cascades_to_defects(client) -> None:
    test_case = _create_test_case(client)
    defect = client.post(
        f"/api/v1/test-cases/{test_case['id']}/defects", json={"title": "A", "severity": "BLOCKER"}
    ).json()

    client.delete(f"/api/v1/test-cases/{test_case['id']}")

    assert client.patch(f"/api/v1/defects/{defect['id']}", json={"status": "CLOSED"}).status_code == 404


def test_defect_for_missing_test_case_returns_404(client) -> None:
    response = client.post("/api/v1/test-cases/999/defects", json={"title": "A", "severity": "BLOCKER"})
    assert response.status_code == 404
