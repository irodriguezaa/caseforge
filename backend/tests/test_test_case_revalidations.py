def _create_release(client, **overrides):
    payload = {
        "name": overrides.pop("name", "CV WEB"),
        "version": overrides.pop("version", "1.0.0"),
        "platform": overrides.pop("platform", "WEB"),
        **overrides,
    }
    response = client.post("/api/v1/releases", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_test_case(client, release_id, test_case_id, status="UNEXECUTED"):
    response = client.post(
        f"/api/v1/releases/{release_id}/test-cases",
        json={
            "test_case_id": test_case_id, "component": "Player",
            "test_case_name": f"Case {test_case_id}", "status": status,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _count_all_test_cases(client, release_ids) -> int:
    total = 0
    for rid in release_ids:
        total += len(client.get(f"/api/v1/releases/{rid}/test-cases").json())
    return total


def test_revalidation_candidates_list_test_cases_from_other_releases_in_same_deliverable(client) -> None:
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="EVOLUTIVO")
    _create_test_case(client, v1["id"], "TE-001", status="FAIL")
    _create_test_case(client, v1["id"], "TE-002", status="PASS")

    v2 = _create_release(
        client, version="1.0.1", deliverable_name="WEB - X",
        release_type="REVALIDACION", parent_release_id=v1["id"],
    )

    candidates = client.get(f"/api/v1/releases/{v2['id']}/revalidation-candidates").json()
    labels = {c["test_case_label"] for c in candidates}
    assert labels == {"TE-001", "TE-002"}
    te001 = next(c for c in candidates if c["test_case_label"] == "TE-001")
    assert te001["current_status"] == "FAIL"
    assert te001["origin_release_id"] == v1["id"]


def test_adding_a_revalidation_does_not_create_a_new_test_case(client) -> None:
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="EVOLUTIVO")
    te001 = _create_test_case(client, v1["id"], "TE-001", status="FAIL")

    v2 = _create_release(
        client, version="1.0.1", deliverable_name="WEB - X",
        release_type="REVALIDACION", parent_release_id=v1["id"],
    )

    before = _count_all_test_cases(client, [v1["id"], v2["id"]])
    response = client.post(
        f"/api/v1/releases/{v2['id']}/revalidations", json={"test_case_ids": [te001["id"]]}
    )
    assert response.status_code == 201
    after = _count_all_test_cases(client, [v1["id"], v2["id"]])

    assert after == before  # NO new TestCase was created
    assert len(client.get(f"/api/v1/releases/{v2['id']}/test-cases").json()) == 0


def test_revalidation_result_is_independent_of_original_test_case_status(client) -> None:
    """V1: TE-001 -> FAIL. V2 revalidates it -> PASS. V1's own result must NOT change."""
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="EVOLUTIVO")
    te001 = _create_test_case(client, v1["id"], "TE-001", status="FAIL")

    v2 = _create_release(
        client, version="1.0.1", deliverable_name="WEB - X",
        release_type="REVALIDACION", parent_release_id=v1["id"],
    )
    revalidation = client.post(
        f"/api/v1/releases/{v2['id']}/revalidations", json={"test_case_ids": [te001["id"]]}
    ).json()[0]
    assert revalidation["status"] == "UNEXECUTED"

    updated = client.patch(
        f"/api/v1/revalidations/{revalidation['id']}", json={"status": "PASS"}
    ).json()
    assert updated["status"] == "PASS"

    original = client.get(f"/api/v1/test-cases/{te001['id']}").json()
    assert original["status"] == "FAIL"  # untouched


def test_revalidation_can_pull_a_candidate_from_any_ancestor_release_not_only_direct_parent(client) -> None:
    """V3's parent is V2, but it can still revalidate TE-001, which first appeared in V1."""
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="EVOLUTIVO")
    te001 = _create_test_case(client, v1["id"], "TE-001", status="FAIL")
    v2 = _create_release(
        client, version="1.0.1", deliverable_name="WEB - X",
        release_type="REVALIDACION", parent_release_id=v1["id"],
    )
    v3 = _create_release(
        client, version="1.0.2", deliverable_name="WEB - X",
        release_type="REVALIDACION", parent_release_id=v2["id"],
    )

    response = client.post(f"/api/v1/releases/{v3['id']}/revalidations", json={"test_case_ids": [te001["id"]]})
    assert response.status_code == 201


def test_cannot_select_the_same_test_case_twice_within_one_revalidation(client) -> None:
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="EVOLUTIVO")
    te001 = _create_test_case(client, v1["id"], "TE-001")
    v2 = _create_release(
        client, version="1.0.1", deliverable_name="WEB - X",
        release_type="REVALIDACION", parent_release_id=v1["id"],
    )

    response = client.post(
        f"/api/v1/releases/{v2['id']}/revalidations",
        json={"test_case_ids": [te001["id"], te001["id"]]},
    )
    assert response.status_code == 422

    client.post(f"/api/v1/releases/{v2['id']}/revalidations", json={"test_case_ids": [te001["id"]]})
    second_attempt = client.post(
        f"/api/v1/releases/{v2['id']}/revalidations", json={"test_case_ids": [te001["id"]]}
    )
    assert second_attempt.status_code == 409


def test_revalidation_candidate_must_belong_to_same_deliverable(client) -> None:
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="EVOLUTIVO")
    te001 = _create_test_case(client, v1["id"], "TE-001")

    other_v1 = _create_release(client, version="1.0.0", name="CV OTHER", deliverable_name="WEB - Y", release_type="EVOLUTIVO")
    other_v2 = _create_release(
        client, version="1.0.1", name="CV OTHER", deliverable_name="WEB - Y",
        release_type="REVALIDACION", parent_release_id=other_v1["id"],
    )

    response = client.post(
        f"/api/v1/releases/{other_v2['id']}/revalidations", json={"test_case_ids": [te001["id"]]}
    )
    assert response.status_code == 409


def test_only_revalidacion_releases_can_register_revalidations(client) -> None:
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="EVOLUTIVO")
    te001 = _create_test_case(client, v1["id"], "TE-001")

    response = client.post(f"/api/v1/releases/{v1['id']}/revalidations", json={"test_case_ids": [te001["id"]]})
    assert response.status_code == 409


def test_revalidation_can_involve_both_old_and_new_tickets_worth_of_test_cases(client) -> None:
    """V2 revalidates TE-001 (old) -- nothing stops a Revalidation Release from ALSO having its
    own fresh TestCases for newly reported defects, since TestCase creation is untouched."""
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="EVOLUTIVO")
    te001 = _create_test_case(client, v1["id"], "TE-001")

    v2 = _create_release(
        client, version="1.0.1", deliverable_name="WEB - X",
        release_type="REVALIDACION", parent_release_id=v1["id"],
    )
    client.post(f"/api/v1/releases/{v2['id']}/revalidations", json={"test_case_ids": [te001["id"]]})
    new_case = _create_test_case(client, v2["id"], "TE-010")  # a brand-new case, normal flow

    revalidations = client.get(f"/api/v1/releases/{v2['id']}/revalidations").json()
    own_cases = client.get(f"/api/v1/releases/{v2['id']}/test-cases").json()
    assert len(revalidations) == 1
    assert len(own_cases) == 1
    assert own_cases[0]["id"] == new_case["id"]
