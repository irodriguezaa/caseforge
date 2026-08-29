def _create_release(client, **overrides):
    payload = {"name": "Claro Video", "version": "8.15", "platform": "tvOS"}
    payload.update(overrides)
    return client.post("/api/v1/releases", json=payload).json()


def test_bulk_create_accepts_blocker_priority(client) -> None:
    """Regression test for the exact case that failed against a drifted Postgres enum: BLOCKER
    is a first-class, supported priority value and must persist end to end."""
    release = _create_release(client)

    response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases/bulk",
        json={
            "test_cases": [
                {
                    "test_case_id": "QC-001",
                    "component": "Playback",
                    "test_case_name": "Case A",
                    "priority": "BLOCKER",
                }
            ]
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["errors"] == []
    assert len(body["created"]) == 1
    assert body["created"][0]["priority"] == "BLOCKER"


def test_bulk_create_rolls_back_everything_on_unexpected_db_error(client, db_session, monkeypatch) -> None:
    """Simulates the class of failure that actually occurred in production: a DB-level error
    (DataError, e.g. an out-of-sync enum) on one row must not leave any other row from the same
    batch persisted, and must not crash the request uncaught."""
    from sqlalchemy.exc import DataError

    from app.models.test_case import TestCase as TestCaseModel

    release = _create_release(client)

    original_flush = db_session.flush

    def flaky_flush(*args, **kwargs):
        pending = [obj for obj in db_session.new if isinstance(obj, TestCaseModel)]
        if any(obj.test_case_id == "QC-002" for obj in pending):
            raise DataError(
                "INSERT INTO test_cases ...",
                {},
                Exception('invalid input value for enum test_case_priority: "BLOCKER"'),
            )
        return original_flush(*args, **kwargs)

    monkeypatch.setattr(db_session, "flush", flaky_flush)

    response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases/bulk",
        json={
            "test_cases": [
                {"test_case_id": "QC-001", "component": "Playback", "test_case_name": "A", "priority": "CRITICAL"},
                {"test_case_id": "QC-002", "component": "Playback", "test_case_name": "B", "priority": "BLOCKER"},
            ]
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["created"] == []
    assert len(body["errors"]) == 1
    assert body["errors"][0]["test_case_id"] == "QC-002"
    assert "base de datos rechazó" in body["errors"][0]["message"]

    monkeypatch.setattr(db_session, "flush", original_flush)
    remaining = client.get(f"/api/v1/releases/{release['id']}/test-cases").json()
    assert remaining == []


def test_create_test_case_with_nested_steps(client) -> None:
    release = _create_release(client)

    response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={
            "test_case_id": "QC-001",
            "component": "Playback",
            "test_case_name": "Play a VOD asset",
            "priority": "BLOCKER",
            "test_type": "REGRESSION",
            "steps": [
                {"step_number": 1, "test_step": "Open app", "expected_result": "App opens"},
                {"step_number": 2, "test_step": "Select asset", "expected_result": "Asset plays"},
            ],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "UNEXECUTED"
    assert len(body["steps"]) == 2
    assert body["steps"][0]["step_number"] == 1


def test_test_case_id_unique_per_release_not_globally(client) -> None:
    release_a = _create_release(client, name="Release A")
    release_b = _create_release(client, name="Release B")

    first = client.post(
        f"/api/v1/releases/{release_a['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "Playback", "test_case_name": "Case A"},
    )
    second = client.post(
        f"/api/v1/releases/{release_b['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "Playback", "test_case_name": "Case B"},
    )

    assert first.status_code == 201
    assert second.status_code == 201


def test_duplicate_test_case_id_within_same_release_conflicts(client) -> None:
    release = _create_release(client)
    client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "Playback", "test_case_name": "Case A"},
    )

    response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "Playback", "test_case_name": "Case B"},
    )

    assert response.status_code == 409


def test_duplicate_step_numbers_in_payload_rejected(client) -> None:
    release = _create_release(client)

    response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={
            "test_case_id": "QC-001",
            "component": "Playback",
            "test_case_name": "Case A",
            "steps": [
                {"step_number": 1, "test_step": "A", "expected_result": "A ok"},
                {"step_number": 1, "test_step": "B", "expected_result": "B ok"},
            ],
        },
    )

    assert response.status_code == 422


def test_create_test_case_for_missing_release_returns_404(client) -> None:
    response = client.post(
        "/api/v1/releases/999/test-cases",
        json={"test_case_id": "QC-001", "component": "Playback", "test_case_name": "Case A"},
    )
    assert response.status_code == 404


def test_update_test_case_status(client) -> None:
    release = _create_release(client)
    test_case = client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "Playback", "test_case_name": "Case A"},
    ).json()

    response = client.patch(f"/api/v1/test-cases/{test_case['id']}", json={"status": "PASS"})

    assert response.status_code == 200
    assert response.json()["status"] == "PASS"


def test_delete_test_case_cascades_to_steps(client) -> None:
    release = _create_release(client)
    test_case = client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={
            "test_case_id": "QC-001",
            "component": "Playback",
            "test_case_name": "Case A",
            "steps": [{"step_number": 1, "test_step": "A", "expected_result": "A ok"}],
        },
    ).json()
    step_id = test_case["steps"][0]["id"]

    response = client.delete(f"/api/v1/test-cases/{test_case['id']}")

    assert response.status_code == 204
    # The parent test case is gone, so its steps listing 404s via get_test_case_or_404.
    assert client.get(f"/api/v1/test-cases/{test_case['id']}/steps").status_code == 404
    # The step's own PK no longer exists either (proves the FK cascade actually ran).
    assert client.patch(f"/api/v1/steps/{step_id}", json={"test_step": "x"}).status_code == 404


def test_bulk_create_is_transactional_one_bad_row_persists_nothing(client) -> None:
    """Per product decision: the bulk endpoint is all-or-nothing. One failing row (here, a
    duplicate test_case_id) must roll back the entire batch -- including QC-002, which on its
    own would have been perfectly valid."""
    release = _create_release(client)
    client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "Playback", "test_case_name": "Existing"},
    )

    response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases/bulk",
        json={
            "test_cases": [
                {"test_case_id": "QC-001", "component": "Playback", "test_case_name": "Dup"},
                {"test_case_id": "QC-002", "component": "Playback", "test_case_name": "New one"},
            ]
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["created"] == []
    assert len(body["errors"]) == 1
    assert body["errors"][0]["test_case_id"] == "QC-001"

    # Confirm QC-002 was NOT left behind despite having no problem of its own.
    remaining = client.get(f"/api/v1/releases/{release['id']}/test-cases").json()
    assert [tc["test_case_id"] for tc in remaining] == ["QC-001"]
    assert len(body["errors"]) == 1
    assert body["errors"][0]["test_case_id"] == "QC-001"
