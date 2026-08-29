def test_dashboard_summary_counts_releases_and_test_cases(client) -> None:
    release = client.post(
        "/api/v1/releases", json={"name": "Claro Video", "version": "8.15", "platform": "tvOS"}
    ).json()
    client.patch(f"/api/v1/releases/{release['id']}", json={"status": "IN_PROGRESS"})
    client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={
            "test_case_id": "QC-001",
            "component": "Playback",
            "test_case_name": "Case A",
            "priority": "CRITICAL",
        },
    )
    client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={
            "test_case_id": "QC-002",
            "component": "Playback",
            "test_case_name": "Case B",
            "priority": "BLOCKER",
        },
    )

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["releases_total"] == 1
    assert body["releases_by_status"]["IN_PROGRESS"] == 1
    assert body["test_cases_total"] == 2
    assert body["test_cases_by_status"]["UNEXECUTED"] == 2
    assert body["test_cases_by_priority"]["CRITICAL"] == 1
    assert body["test_cases_by_priority"]["BLOCKER"] == 1
