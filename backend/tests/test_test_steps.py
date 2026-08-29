def _create_test_case_with_steps(client) -> dict:
    release = client.post(
        "/api/v1/releases", json={"name": "Claro Video", "version": "8.15", "platform": "tvOS"}
    ).json()
    return client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={
            "test_case_id": "QC-001",
            "component": "Playback",
            "test_case_name": "Play a VOD asset",
            "steps": [
                {"step_number": 1, "test_step": "Open app", "expected_result": "App opens"},
                {"step_number": 2, "test_step": "Select asset", "expected_result": "Asset plays"},
            ],
        },
    ).json()


def test_list_steps_ordered_by_step_number(client) -> None:
    test_case = _create_test_case_with_steps(client)

    response = client.get(f"/api/v1/test-cases/{test_case['id']}/steps")

    assert response.status_code == 200
    steps = response.json()
    assert [s["step_number"] for s in steps] == [1, 2]


def test_add_step_with_duplicate_number_conflicts(client) -> None:
    test_case = _create_test_case_with_steps(client)

    response = client.post(
        f"/api/v1/test-cases/{test_case['id']}/steps",
        json={"step_number": 1, "test_step": "Dup", "expected_result": "Dup"},
    )

    assert response.status_code == 409


def test_update_step(client) -> None:
    test_case = _create_test_case_with_steps(client)
    step_id = test_case["steps"][0]["id"]

    response = client.patch(f"/api/v1/steps/{step_id}", json={"test_step": "Open the app fresh"})

    assert response.status_code == 200
    assert response.json()["test_step"] == "Open the app fresh"


def test_delete_step(client) -> None:
    test_case = _create_test_case_with_steps(client)
    step_id = test_case["steps"][0]["id"]

    response = client.delete(f"/api/v1/steps/{step_id}")

    assert response.status_code == 204
    remaining = client.get(f"/api/v1/test-cases/{test_case['id']}/steps").json()
    assert len(remaining) == 1


def test_reorder_steps_swaps_numbers_without_conflict(client) -> None:
    test_case = _create_test_case_with_steps(client)
    step_1_id = test_case["steps"][0]["id"]
    step_2_id = test_case["steps"][1]["id"]

    response = client.put(
        f"/api/v1/test-cases/{test_case['id']}/steps/reorder",
        json={"steps": [{"id": step_1_id, "step_number": 2}, {"id": step_2_id, "step_number": 1}]},
    )

    assert response.status_code == 200
    reordered = response.json()
    assert reordered[0]["id"] == step_2_id
    assert reordered[0]["step_number"] == 1
    assert reordered[1]["id"] == step_1_id
    assert reordered[1]["step_number"] == 2


def test_reorder_rejects_step_id_from_another_test_case(client) -> None:
    test_case = _create_test_case_with_steps(client)
    other_release = client.post(
        "/api/v1/releases", json={"name": "Other", "version": "1.0", "platform": "iOS"}
    ).json()
    other_case = client.post(
        f"/api/v1/releases/{other_release['id']}/test-cases",
        json={
            "test_case_id": "QC-001",
            "component": "Playback",
            "test_case_name": "Other case",
            "steps": [{"step_number": 1, "test_step": "X", "expected_result": "Y"}],
        },
    ).json()
    foreign_step_id = other_case["steps"][0]["id"]

    response = client.put(
        f"/api/v1/test-cases/{test_case['id']}/steps/reorder",
        json={"steps": [{"id": foreign_step_id, "step_number": 1}]},
    )

    assert response.status_code == 400
