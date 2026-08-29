def _create_release(client, **overrides):
    payload = {"name": "Claro Video", "version": "8.15", "platform": "tvOS"}
    payload.update(overrides)
    return client.post("/api/v1/releases", json=payload).json()


def test_create_operational_window(client) -> None:
    response = client.post(
        "/api/v1/operational-windows",
        json={"name": "Semana 34", "start_date": "2026-08-18", "end_date": "2026-08-24", "cluster": "LATAM"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PLANNED"
    assert body["cluster"] == "LATAM"


def test_list_operational_windows_filters_by_status_and_cluster(client) -> None:
    client.post(
        "/api/v1/operational-windows",
        json={"name": "W1", "start_date": "2026-08-01", "end_date": "2026-08-07", "cluster": "LATAM"},
    )
    w2 = client.post(
        "/api/v1/operational-windows",
        json={"name": "W2", "start_date": "2026-08-08", "end_date": "2026-08-14", "cluster": "Brasil"},
    ).json()
    client.patch(f"/api/v1/operational-windows/{w2['id']}", json={"status": "ACTIVE"})

    active_only = client.get("/api/v1/operational-windows", params={"status": "ACTIVE"}).json()
    brasil_only = client.get("/api/v1/operational-windows", params={"cluster": "Brasil"}).json()

    assert len(active_only) == 1
    assert active_only[0]["name"] == "W2"
    assert len(brasil_only) == 1


def test_create_release_window_nested_under_release(client) -> None:
    release = _create_release(client)

    response = client.post(
        f"/api/v1/releases/{release['id']}/windows",
        json={"name": "Regresión completa", "start_date": "2026-08-20", "end_date": "2026-08-27"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["release_id"] == release["id"]
    assert body["status"] == "PLANNED"


def test_release_window_for_missing_release_returns_404(client) -> None:
    response = client.post(
        "/api/v1/releases/999/windows",
        json={"name": "X", "start_date": "2026-08-20", "end_date": "2026-08-27"},
    )
    assert response.status_code == 404


def test_flat_release_windows_listing_spans_all_releases(client) -> None:
    release_a = _create_release(client, name="Release A")
    release_b = _create_release(client, name="Release B")
    client.post(
        f"/api/v1/releases/{release_a['id']}/windows",
        json={"name": "W-A", "start_date": "2026-08-01", "end_date": "2026-08-07"},
    )
    client.post(
        f"/api/v1/releases/{release_b['id']}/windows",
        json={"name": "W-B", "start_date": "2026-08-08", "end_date": "2026-08-14"},
    )

    response = client.get("/api/v1/release-windows")

    assert response.status_code == 200
    names = {w["name"] for w in response.json()}
    assert names == {"W-A", "W-B"}


def test_test_case_can_link_to_both_window_types_independently(client) -> None:
    """No hierarchy: a TestCase may reference an OperationalWindow, a ReleaseWindow, both, or
    neither -- confirms there is no FK coupling the two window types together."""
    release = _create_release(client)
    ow = client.post(
        "/api/v1/operational-windows",
        json={"name": "Semana 34", "start_date": "2026-08-18", "end_date": "2026-08-24"},
    ).json()
    rw = client.post(
        f"/api/v1/releases/{release['id']}/windows",
        json={"name": "Regresión", "start_date": "2026-08-20", "end_date": "2026-08-27"},
    ).json()

    test_case = client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={
            "test_case_id": "QC-001",
            "component": "Playback",
            "test_case_name": "Case A",
            "operational_window_id": ow["id"],
            "release_window_id": rw["id"],
        },
    ).json()

    assert test_case["operational_window_id"] == ow["id"]
    assert test_case["release_window_id"] == rw["id"]


def test_deleting_operational_window_sets_test_case_link_to_null(client) -> None:
    release = _create_release(client)
    ow = client.post(
        "/api/v1/operational-windows",
        json={"name": "Semana 34", "start_date": "2026-08-18", "end_date": "2026-08-24"},
    ).json()
    test_case = client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={
            "test_case_id": "QC-001",
            "component": "Playback",
            "test_case_name": "Case A",
            "operational_window_id": ow["id"],
        },
    ).json()

    delete_response = client.delete(f"/api/v1/operational-windows/{ow['id']}")
    assert delete_response.status_code == 204

    refreshed = client.get(f"/api/v1/test-cases/{test_case['id']}").json()
    assert refreshed["operational_window_id"] is None
