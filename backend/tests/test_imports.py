import io

import openpyxl

CSV_HEADER = (
    "Test Case ID,Component,Test Case Name,Description,User Type,Step,Test Step,"
    "Expected Result,Priority,Test Type,Status\n"
)


def _create_release(client) -> dict:
    return client.post(
        "/api/v1/releases", json={"name": "Claro Video", "version": "8.15", "platform": "tvOS"}
    ).json()


def _upload_csv(client, release_id: int, csv_text: str):
    return client.post(
        f"/api/v1/releases/{release_id}/test-cases/import/preview",
        files={"file": ("import.csv", csv_text.encode("utf-8"), "text/csv")},
    )


def test_preview_and_bulk_agree_on_which_priorities_are_persistable(client) -> None:
    """Guards against the exact class of bug that just occurred: preview's accepted priority
    values and the database's actual enum must never diverge. This asserts they're driven by
    the same source (TestCasePriority) rather than a second, hand-maintained list -- if BLOCKER
    is ever removed from the model without updating the importer (or vice versa), this fails."""
    from app.models.test_case import TestCasePriority
    from app.services.imports import _PRIORITY_ALIASES

    assert set(_PRIORITY_ALIASES.keys()) == {member.value for member in TestCasePriority}

    release = _create_release(client)
    csv_text = CSV_HEADER + (
        "QC-001,Playback,Play a VOD asset,,Subscriber,1,Open app,App opens,Blocker,Functional,Pendiente\n"
    )
    preview = _upload_csv(client, release["id"], csv_text).json()
    assert preview["valid_count"] == 1
    assert preview["valid"][0]["priority"] == "BLOCKER"

    persist = client.post(
        f"/api/v1/releases/{release['id']}/test-cases/bulk",
        json={"test_cases": preview["valid"]},
    )
    assert persist.status_code == 201
    assert len(persist.json()["created"]) == 1


def test_preview_valid_csv_with_two_test_cases(client) -> None:
    release = _create_release(client)
    csv_text = CSV_HEADER + (
        "QC-001,Playback,Play a VOD asset,,Subscriber,1,Open app,App opens,Critical,Functional,Pendiente\n"
        "QC-001,Playback,Play a VOD asset,,Subscriber,2,Select asset,Playback starts,Critical,Functional,Pendiente\n"
        "QC-002,Login,Login with valid user,,Subscriber,1,Enter credentials,User logs in,Blocker,Smoke,Pendiente\n"
    )

    response = _upload_csv(client, release["id"], csv_text)

    assert response.status_code == 200
    body = response.json()
    assert body["valid_count"] == 2
    assert body["error_count"] == 0
    assert body["total_rows"] == 3
    by_id = {tc["test_case_id"]: tc for tc in body["valid"]}
    assert len(by_id["QC-001"]["steps"]) == 2
    assert by_id["QC-001"]["status"] == "UNEXECUTED"  # "Pendiente" alias
    assert by_id["QC-002"]["priority"] == "BLOCKER"
    assert by_id["QC-002"]["test_type"] == "SMOKE"


def test_preview_defaults_blank_test_type_to_functional(client) -> None:
    release = _create_release(client)
    csv_text = CSV_HEADER + (
        "QC-001,Playback,Play a VOD asset,,Subscriber,1,Open app,App opens,Critical,,Pendiente\n"
    )

    response = _upload_csv(client, release["id"], csv_text)

    assert response.status_code == 200
    assert response.json()["valid"][0]["test_type"] == "FUNCTIONAL"


def test_preview_missing_required_column_is_a_structural_error(client) -> None:
    release = _create_release(client)
    csv_text = (
        "Test Case ID,Component,Test Case Name,User Type,Step,Test Step,Priority,Test Type,Status\n"
        "QC-001,Playback,Play a VOD asset,Subscriber,1,Open app,Critical,Functional,Pendiente\n"
    )  # missing "Expected Result"

    response = _upload_csv(client, release["id"], csv_text)

    assert response.status_code == 422
    assert "expected_result" in response.json()["detail"]


def test_preview_rejects_invalid_priority(client) -> None:
    release = _create_release(client)
    csv_text = CSV_HEADER + (
        "QC-001,Playback,Play a VOD asset,,Subscriber,1,Open app,App opens,High,Functional,Pendiente\n"
    )

    response = _upload_csv(client, release["id"], csv_text)

    assert response.status_code == 200
    body = response.json()
    assert body["valid_count"] == 0
    assert body["error_count"] == 1
    assert "Priority" in body["errors"][0]["message"]


def test_preview_flags_inconsistent_metadata_within_same_test_case_id(client) -> None:
    release = _create_release(client)
    csv_text = CSV_HEADER + (
        "QC-001,Playback,Play a VOD asset,,Subscriber,1,Open app,App opens,Critical,Functional,Pendiente\n"
        "QC-001,Playback,A totally different case,,Subscriber,2,Select asset,Plays,Critical,Functional,Pendiente\n"
    )

    response = _upload_csv(client, release["id"], csv_text)

    assert response.status_code == 200
    body = response.json()
    assert body["valid_count"] == 0
    assert body["error_count"] == 1
    assert "test_case_name" in body["errors"][0]["message"]


def test_preview_flags_duplicate_step_numbers(client) -> None:
    release = _create_release(client)
    csv_text = CSV_HEADER + (
        "QC-001,Playback,Play a VOD asset,,Subscriber,1,Open app,App opens,Critical,Functional,Pendiente\n"
        "QC-001,Playback,Play a VOD asset,,Subscriber,1,Select asset,Plays,Critical,Functional,Pendiente\n"
    )

    response = _upload_csv(client, release["id"], csv_text)

    body = response.json()
    assert body["valid_count"] == 0
    assert body["error_count"] == 1
    assert "Step" in body["errors"][0]["message"]


def test_preview_flags_test_case_id_already_in_release(client) -> None:
    release = _create_release(client)
    client.post(
        f"/api/v1/releases/{release['id']}/test-cases",
        json={"test_case_id": "QC-001", "component": "Playback", "test_case_name": "Existing"},
    )
    csv_text = CSV_HEADER + (
        "QC-001,Playback,Play a VOD asset,,Subscriber,1,Open app,App opens,Critical,Functional,Pendiente\n"
    )

    response = _upload_csv(client, release["id"], csv_text)

    body = response.json()
    assert body["valid_count"] == 0
    assert body["error_count"] == 1
    assert "ya existe" in body["errors"][0]["message"]


def test_preview_accepts_xlsx(client) -> None:
    release = _create_release(client)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "Test Case ID",
            "Component",
            "Test Case Name",
            "Description",
            "User Type",
            "Step",
            "Test Step",
            "Expected Result",
            "Priority",
            "Test Type",
            "Status",
        ]
    )
    sheet.append(
        ["QC-001", "Playback", "Play a VOD asset", None, "Subscriber", 1, "Open app", "App opens",
         "Critical", "Functional", "Pendiente"]
    )
    buffer = io.BytesIO()
    workbook.save(buffer)

    response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases/import/preview",
        files={
            "file": (
                "import.xlsx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["valid_count"] == 1
    assert body["valid"][0]["test_case_id"] == "QC-001"


def test_preview_persist_roundtrip_via_existing_bulk_endpoint(client) -> None:
    """The whole point of this pipeline: preview's `valid` list feeds the existing bulk endpoint
    unchanged, so Approve -> Persist requires no new persistence code."""
    release = _create_release(client)
    csv_text = CSV_HEADER + (
        "QC-001,Playback,Play a VOD asset,,Subscriber,1,Open app,App opens,Critical,Functional,Pendiente\n"
        "QC-001,Playback,Play a VOD asset,,Subscriber,2,Select asset,Plays,Critical,Functional,Pendiente\n"
    )

    preview = _upload_csv(client, release["id"], csv_text).json()
    persist = client.post(
        f"/api/v1/releases/{release['id']}/test-cases/bulk",
        json={"test_cases": preview["valid"]},
    )

    assert persist.status_code == 201
    persisted = persist.json()
    assert len(persisted["created"]) == 1
    assert len(persisted["created"][0]["steps"]) == 2
    assert len(persisted["errors"]) == 0


def test_preview_rejects_unsupported_file_type(client) -> None:
    release = _create_release(client)
    response = client.post(
        f"/api/v1/releases/{release['id']}/test-cases/import/preview",
        files={"file": ("import.txt", b"whatever", "text/plain")},
    )
    assert response.status_code == 422
