def _create_release(client, **overrides):
    payload = {"name": "Claro Video", "version": "8.15", "platform": "tvOS", "cluster": "LATAM"}
    payload.update(overrides)
    return client.post("/api/v1/releases", json=payload).json()


def test_qc_summary_computes_avance_and_status_breakdown(client) -> None:
    release = _create_release(client)
    client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "Playback", "test_case_name": "A", "status": "PASS"},
    )
    client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={"test_case_id": "QC-002", "component": "Playback", "test_case_name": "B", "status": "FAIL"},
    )
    client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={"test_case_id": "QC-003", "component": "Playback", "test_case_name": "C"},
    )  # UNEXECUTED

    response = client.get("/api/v1/dashboard/qc-summary")

    assert response.status_code == 200
    body = response.json()
    assert body["test_cases_planned"] == 3
    assert body["test_cases_executed"] == 2
    assert body["pass_count"] == 1
    assert body["fail_count"] == 1
    assert body["unexecuted_count"] == 1
    # 2 executed / 3 planned = 66.7%
    assert body["percent_avance"] == 66.7
    # Per product decision, percent_cobertura shares the same formula for now.
    assert body["percent_cobertura"] == body["percent_avance"]


def test_qc_summary_filters_by_cluster(client) -> None:
    latam = _create_release(client, name="Latam Release", cluster="LATAM")
    brasil = _create_release(client, name="Brasil Release", cluster="Brasil")
    client.post(
        f"/api/v1/releases/{latam['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "X", "test_case_name": "A"},
    )
    client.post(
        f"/api/v1/releases/{brasil['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "X", "test_case_name": "A"},
    )

    latam_summary = client.get("/api/v1/dashboard/qc-summary", params={"cluster": "LATAM"}).json()
    brasil_summary = client.get("/api/v1/dashboard/qc-summary", params={"cluster": "Brasil"}).json()

    assert latam_summary["test_cases_planned"] == 1
    assert brasil_summary["test_cases_planned"] == 1


def test_qc_summary_counts_defects_and_critical_defects(client) -> None:
    release = _create_release(client)
    test_case = client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "X", "test_case_name": "A", "status": "FAIL"},
    ).json()
    client.post(f"/api/v1/test-cases/{test_case['id']}/defects", json={"title": "A", "severity": "CRITICAL"})
    client.post(f"/api/v1/test-cases/{test_case['id']}/defects", json={"title": "B", "severity": "BLOCKER"})

    body = client.get("/api/v1/dashboard/qc-summary").json()

    assert body["defects_found"] == 2
    assert body["defects_critical"] == 1  # only severity == CRITICAL counts as "crítico" here


def test_qc_summary_flags_window_at_risk_when_blocked_test_case_exists(client) -> None:
    release = _create_release(client)
    window = client.post(
        f"/api/v1/releases/{release['id']}/windows",
        json={"name": "Regresión", "start_date": "2026-08-01", "end_date": "2026-08-31"},
    ).json()
    client.patch(f"/api/v1/release-windows/{window['id']}", json={"status": "ACTIVE"})
    client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={
            "test_case_id": "QC-001",
            "component": "X",
            "test_case_name": "A",
            "status": "BLOCKED",
            "release_window_id": window["id"],
        },
    )

    body = client.get("/api/v1/dashboard/qc-summary").json()

    assert body["release_windows_active"] == 1
    at_risk_ids = [item["id"] for item in body["at_risk"]]
    assert window["id"] in at_risk_ids
    matching = next(item for item in body["at_risk"] if item["id"] == window["id"])
    assert any("BLOCKED" in reason for reason in matching["reasons"])


def test_qc_summary_planned_window_not_evaluated_for_risk(client) -> None:
    release = _create_release(client)
    window = client.post(
        f"/api/v1/releases/{release['id']}/windows",
        json={"name": "Regresión", "start_date": "2026-08-01", "end_date": "2026-08-31"},
    ).json()  # left as PLANNED, never activated
    client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={
            "test_case_id": "QC-001",
            "component": "X",
            "test_case_name": "A",
            "status": "BLOCKED",
            "release_window_id": window["id"],
        },
    )

    body = client.get("/api/v1/dashboard/qc-summary").json()

    at_risk_ids = [item["id"] for item in body["at_risk"]]
    assert window["id"] not in at_risk_ids


def test_qc_summary_invalid_month_format_is_rejected(client) -> None:
    response = client.get("/api/v1/dashboard/qc-summary", params={"month": "not-a-month"})
    assert response.status_code == 400


def test_qc_summary_active_items_reflects_open_releases(client) -> None:
    release = _create_release(client)
    client.patch(f"/api/v1/releases/{release['id']}", json={"status": "IN_PROGRESS"})
    client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "X", "test_case_name": "A", "status": "PASS"},
    )
    client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={"test_case_id": "QC-002", "component": "X", "test_case_name": "B"},
    )

    body = client.get("/api/v1/dashboard/qc-summary").json()

    assert len(body["active_items"]) == 1
    item = body["active_items"][0]
    assert item["release_id"] == release["id"]
    assert item["planned"] == 2
    assert item["executed"] == 1
    assert item["percent_avance"] == 50.0
    assert item["risk_level"] == "LOW"


def test_qc_summary_active_items_high_risk_when_blocked(client) -> None:
    release = _create_release(client)
    client.patch(f"/api/v1/releases/{release['id']}", json={"status": "IN_PROGRESS"})
    client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "X", "test_case_name": "A", "status": "BLOCKED"},
    )

    body = client.get("/api/v1/dashboard/qc-summary").json()

    item = body["active_items"][0]
    assert item["risk_level"] == "HIGH"
    assert any("BLOCKED" in r for r in item["risk_reasons"])


def test_qc_summary_active_items_excludes_completed_and_cancelled_releases(client) -> None:
    completed = _create_release(client, name="Completed Release")
    client.patch(f"/api/v1/releases/{completed['id']}", json={"status": "IN_PROGRESS"})
    client.patch(f"/api/v1/releases/{completed['id']}", json={"status": "COMPLETED"})

    body = client.get("/api/v1/dashboard/qc-summary").json()

    release_ids = [item["release_id"] for item in body["active_items"]]
    assert completed["id"] not in release_ids


def test_qc_summary_execution_items_include_completed_releases(client) -> None:
    completed = _create_release(client, name="Completed Exec")
    client.patch(f"/api/v1/releases/{completed['id']}", json={"status": "IN_PROGRESS"})
    client.patch(f"/api/v1/releases/{completed['id']}", json={"status": "COMPLETED"})

    body = client.get("/api/v1/dashboard/qc-summary").json()

    execution_ids = [item["release_id"] for item in body["execution_items"]]
    assert completed["id"] in execution_ids
    item = next(row for row in body["execution_items"] if row["release_id"] == completed["id"])
    assert item["status"] == "COMPLETED"


def test_qc_summary_active_items_exposes_status_and_per_status_counts(client) -> None:
    release = _create_release(client)
    client.patch(f"/api/v1/releases/{release['id']}", json={"status": "IN_PROGRESS"})
    for i, st in enumerate(["PASS", "FAIL", "BLOCKED", "UNEXECUTED"], start=1):
        client.post(
            f"/api/v1/releases/{release['id']}/test-cases",
            json={"test_case_id": f"QC-00{i}", "component": "X", "test_case_name": f"Case {i}", "status": st},
        )

    body = client.get("/api/v1/dashboard/qc-summary").json()

    item = next(i for i in body["active_items"] if i["release_id"] == release["id"])
    assert item["status"] == "IN_PROGRESS"
    assert item["pass_count"] == 1
    assert item["fail_count"] == 1
    assert item["blocked_count"] == 1
    assert item["unexecuted_count"] == 1


def test_qc_summary_active_items_exposes_window_dates_and_blocker_defects(client) -> None:
    release = _create_release(client)
    client.patch(f"/api/v1/releases/{release['id']}", json={"status": "IN_PROGRESS"})
    window = client.post(
        f"/api/v1/releases/{release['id']}/windows",
        json={"name": "Ventana inicial", "start_date": "2026-08-25", "end_date": "2026-08-28"},
    ).json()
    client.patch(f"/api/v1/release-windows/{window['id']}", json={"status": "ACTIVE"})

    test_case = client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "X", "test_case_name": "A", "status": "FAIL"},
    ).json()
    client.post(f"/api/v1/test-cases/{test_case['id']}/defects", json={"title": "Crash", "severity": "BLOCKER"})
    client.post(f"/api/v1/test-cases/{test_case['id']}/defects", json={"title": "Other", "severity": "CRITICAL"})

    body = client.get("/api/v1/dashboard/qc-summary").json()
    item = next(i for i in body["active_items"] if i["release_id"] == release["id"])

    assert item["window_start_date"] == "2026-08-25"
    assert item["window_end_date"] == "2026-08-28"
    assert item["defects_blocker_count"] == 1  # only the BLOCKER-severity one counts


def test_qc_summary_active_items_exposes_deliverable_context(client) -> None:
    v1 = client.post(
        "/api/v1/releases",
        json={
            "name": "CV WEB", "version": "1.0.0", "platform": "WEB",
            "deliverable_name": "WEB - Funcionalidad X", "release_type": "NUEVO",
        },
    ).json()
    v2 = client.post(
        "/api/v1/releases",
        json={
            "name": "CV WEB", "version": "1.0.1", "platform": "WEB",
            "deliverable_name": "WEB - Funcionalidad X", "release_type": "REVALIDACION",
            "parent_release_id": v1["id"],
        },
    ).json()
    client.patch(f"/api/v1/releases/{v2['id']}", json={"status": "IN_PROGRESS"})

    body = client.get("/api/v1/dashboard/qc-summary").json()
    item = next(i for i in body["active_items"] if i["release_id"] == v2["id"])

    assert item["deliverable_name"] == "WEB - Funcionalidad X"
    assert item["release_type"] == "REVALIDACION"
    assert item["deliverable_release_ordinal"] == 2  # v2 (v1 came first)
    assert item["deliverable_total_versions"] == 2  # v1 + v2, regardless of v1's own status
    assert item["deliverable_total_revalidaciones"] == 1


def test_qc_summary_active_items_deliverable_fields_are_none_without_deliverable(client) -> None:
    release = _create_release(client)  # no deliverable_name passed
    client.patch(f"/api/v1/releases/{release['id']}", json={"status": "IN_PROGRESS"})

    body = client.get("/api/v1/dashboard/qc-summary").json()
    item = next(i for i in body["active_items"] if i["release_id"] == release["id"])

    assert item["deliverable_name"] is None
    assert item["release_type"] is None
    assert item["deliverable_release_ordinal"] is None
    assert item["deliverable_total_versions"] is None
    assert item["deliverable_total_revalidaciones"] is None
    assert item["origin_kind"] == "APP"


def test_qc_summary_origin_kinds_and_in_progress_counts(client, db_session) -> None:
    from app.models.operativa_release import OperativaRelease
    from app.models.release import Release, ReleaseStatus

    app = _create_release(client, name="App Cycle", version="1.0")
    client.patch(f"/api/v1/releases/{app['id']}", json={"status": "IN_PROGRESS"})

    be_draft = client.post("/api/v1/releases-be").json()
    client.patch(
        f"/api/v1/releases-be/{be_draft['id']}",
        json={"name": "BE Cycle", "regresivo_scope": "SMOKE"},
    )
    be = client.post(f"/api/v1/releases-be/{be_draft['id']}/create-release").json()
    client.patch(f"/api/v1/releases/{be['id']}", json={"status": "IN_PROGRESS"})

    ope_row = OperativaRelease(name="OPE Cycle", pdf_filename="ope.pdf")
    db_session.add(ope_row)
    db_session.commit()
    ope = Release(
        name="OPE Cycle",
        version="OPE",
        platform="Operativa",
        cluster="AUP",
        operativa_release_id=ope_row.id,
        status=ReleaseStatus.IN_PROGRESS,
    )
    db_session.add(ope)
    db_session.commit()

    body = client.get("/api/v1/dashboard/qc-summary").json()
    assert body["in_progress_app"] == 1
    assert body["in_progress_be"] == 1
    assert body["in_progress_operativa"] == 1
    assert body["in_progress_total"] == 3
    assert body["in_progress_total"] == (
        body["in_progress_app"] + body["in_progress_be"] + body["in_progress_operativa"]
    )

    by_id = {item["release_id"]: item for item in body["active_items"]}
    assert by_id[app["id"]]["origin_kind"] == "APP"
    assert by_id[be["id"]]["origin_kind"] == "BE"
    assert by_id[ope.id]["origin_kind"] == "OPERATIVA"
