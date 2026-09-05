def _create_release(client, **overrides):
    payload = {
        "name": "Claro Video",
        "version": "8.15",
        "platform": "tvOS",
        "cluster": "LATAM",
        "description": "Release 8.15 regression cycle",
    }
    payload.update(overrides)
    return client.post("/api/v1/releases", json=payload)


def test_create_release_defaults_to_draft(client) -> None:
    response = _create_release(client)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["name"] == "Claro Video"
    assert "id" in body


def test_create_release_duplicate_name_version_platform_conflicts(client) -> None:
    first = _create_release(client)
    assert first.status_code == 201

    duplicate = _create_release(client)

    assert duplicate.status_code == 409


def test_list_releases_includes_test_case_count(client) -> None:
    release_id = _create_release(client).json()["id"]
    client.post(
        f"/api/v1/releases/{release_id}/test-cases",
        json={
            "test_case_id": "QC-001",
            "component": "Playback",
            "test_case_name": "Play a VOD asset",
            "priority": "BLOCKER",
        },
    )

    response = client.get("/api/v1/releases")

    assert response.status_code == 200
    releases = response.json()
    assert len(releases) == 1
    assert releases[0]["test_case_count"] == 1


def test_list_releases_filters_by_status(client) -> None:
    _create_release(client, name="Release A")
    draft_only = client.get("/api/v1/releases", params={"status": "DRAFT"})
    in_progress_only = client.get("/api/v1/releases", params={"status": "IN_PROGRESS"})

    assert len(draft_only.json()) == 1
    assert len(in_progress_only.json()) == 0


def test_list_releases_excludes_be_by_default_and_includes_with_flag(client) -> None:
    app = _create_release(client).json()
    be_draft = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{be_draft['id']}",
        json={"name": "BE Hidden", "regresivo_scope": "COMPLETO"},
    )
    be = client.post(f"/api/v1/releases-be/{be_draft['id']}/create-release").json()

    default_ids = {row["id"] for row in client.get("/api/v1/releases").json()}
    assert app["id"] in default_ids
    assert be["id"] not in default_ids

    all_ids = {row["id"] for row in client.get("/api/v1/releases", params={"include_be": True}).json()}
    assert app["id"] in all_ids
    assert be["id"] in all_ids


def test_get_release_not_found_returns_404(client) -> None:
    response = client.get("/api/v1/releases/999")
    assert response.status_code == 404


def test_valid_status_transition_succeeds(client) -> None:
    release_id = _create_release(client).json()["id"]

    response = client.patch(f"/api/v1/releases/{release_id}", json={"status": "IN_PROGRESS"})

    assert response.status_code == 200
    assert response.json()["status"] == "IN_PROGRESS"


def test_invalid_status_transition_is_rejected(client) -> None:
    release_id = _create_release(client).json()["id"]

    response = client.patch(f"/api/v1/releases/{release_id}", json={"status": "COMPLETED"})

    assert response.status_code == 409


def test_draft_release_can_be_deleted(client) -> None:
    release_id = _create_release(client).json()["id"]

    response = client.delete(f"/api/v1/releases/{release_id}")

    assert response.status_code == 204
    assert client.get(f"/api/v1/releases/{release_id}").status_code == 404


def test_in_progress_app_release_can_be_deleted(client) -> None:
    release_id = _create_release(client).json()["id"]
    client.patch(f"/api/v1/releases/{release_id}", json={"status": "IN_PROGRESS"})

    response = client.delete(f"/api/v1/releases/{release_id}")

    assert response.status_code == 204
    assert client.get(f"/api/v1/releases/{release_id}").status_code == 404


def test_non_draft_release_must_be_cancelled_instead(client) -> None:
    release_id = _create_release(client).json()["id"]
    client.patch(f"/api/v1/releases/{release_id}", json={"status": "IN_PROGRESS"})

    response = client.patch(f"/api/v1/releases/{release_id}", json={"status": "CANCELLED"})

    assert response.status_code == 200
    assert response.json()["status"] == "CANCELLED"


def test_deleting_draft_release_cascades_to_test_cases_and_steps(client) -> None:
    release_id = _create_release(client).json()["id"]
    test_case = client.post(
        f"/api/v1/releases/{release_id}/test-cases",
        json={
            "test_case_id": "QC-001",
            "component": "Playback",
            "test_case_name": "Play a VOD asset",
            "steps": [{"step_number": 1, "test_step": "Open app", "expected_result": "App opens"}],
        },
    ).json()

    response = client.delete(f"/api/v1/releases/{release_id}")

    assert response.status_code == 204
    assert client.get(f"/api/v1/test-cases/{test_case['id']}").status_code == 404
