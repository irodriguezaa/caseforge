"""KPI 1–2: QC Release volume and monthly evolution from releases.created_at."""

from datetime import datetime, timezone

from app.models.operativa_release import OperativaRelease
from app.models.release import Release


def _create_app(client, **overrides):
    payload = {"name": "Claro Video", "version": "1.0", "platform": "WEB"}
    payload.update(overrides)
    return client.post("/api/v1/releases", json=payload).json()


def _create_be_qc(client, name: str, clusters: list[str] | None = None):
    draft = client.post("/api/v1/releases-be").json()
    patch = {
        "name": name,
        "swf": "BE Hitss",
        "regresivo_scope": "SMOKE",
    }
    if clusters is not None:
        patch["clusters"] = clusters
    client.patch(f"/api/v1/releases-be/{draft['id']}", json=patch)
    return client.post(f"/api/v1/releases-be/{draft['id']}/create-release").json()


def _set_created_at(db_session, release_id: int, when: datetime) -> None:
    row = db_session.get(Release, release_id)
    assert row is not None
    row.created_at = when
    db_session.commit()
    db_session.expire_all()


def _volume(client, **params):
    return client.get("/api/v1/kpis/releases", params=params).json()


def test_volume_counts_app_be_operativa_and_excludes_cancelled_drafts(
    client, db_session
) -> None:
    _create_app(client, name="App A", version="1.0")
    _create_app(client, name="App B", version="2.0")
    cancelled = _create_app(client, name="App Cancelled", version="9.0")
    client.patch(f"/api/v1/releases/{cancelled['id']}", json={"status": "CANCELLED"})

    be = _create_be_qc(client, "BE Multi", clusters=["AUP", "Andina", "CENAM"])
    assert "AUP" in (be.get("cluster") or "")
    assert "Andina" in (be.get("cluster") or "")
    assert "CENAM" in (be.get("cluster") or "")

    orphan_be = client.post("/api/v1/releases-be").json()
    assert orphan_be["qc_release_id"] is None

    ope_row = OperativaRelease(name="OPE Cycle", pdf_filename="ope.pdf")
    db_session.add(ope_row)
    db_session.commit()
    ope = Release(
        name="OPE Cycle",
        version="OPE",
        platform="Operativa",
        cluster="AUP",
        operativa_release_id=ope_row.id,
    )
    db_session.add(ope)
    db_session.commit()

    db_session.add(OperativaRelease(name="OPE Draft", pdf_filename="draft.pdf"))
    db_session.commit()

    body = _volume(client)
    assert body["app"] == 2
    assert body["be"] == 1
    assert body["operativa"] == 1
    assert body["total"] == 4
    assert body["app"] + body["be"] + body["operativa"] == body["total"]
    listed = {
        row["id"]
        for row in client.get(
            "/api/v1/releases", params={"include_be": True, "include_operativa": True}
        ).json()
    }
    assert cancelled["id"] in listed
    assert body["total"] == 4

    filtered = client.get("/api/v1/dashboard/qc-summary", params={"cluster": "AUP"}).json()
    assert "total" not in filtered
    assert "kpi_releases_total" not in filtered
    kpis_again = _volume(client)
    assert kpis_again["total"] == body["total"]
    assert kpis_again["be"] == 1


def test_volume_deleted_release_does_not_count(client) -> None:
    keep = _create_app(client, name="Keep", version="1.0")
    drop = _create_app(client, name="Drop", version="2.0")
    before = _volume(client)
    assert before["total"] == 2

    deleted = client.delete(f"/api/v1/releases/{drop['id']}")
    assert deleted.status_code == 204
    after = _volume(client)
    assert after["total"] == 1
    assert after["app"] == 1
    assert keep["id"] != drop["id"]


def test_volume_month_uses_created_at_not_start_date(client, db_session) -> None:
    july = _create_app(client, name="July App", version="1.0", start_date="2026-09-01")
    august_be = _create_be_qc(client, "August BE", clusters=["Todos"])
    ope_row = OperativaRelease(name="Sep OPE", pdf_filename="ope.pdf")
    db_session.add(ope_row)
    db_session.commit()
    september_ope = Release(
        name="Sep OPE",
        version="OPE",
        platform="Operativa",
        operativa_release_id=ope_row.id,
        start_date=datetime(2026, 1, 1).date(),
    )
    db_session.add(september_ope)
    db_session.commit()

    _set_created_at(db_session, july["id"], datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc))
    _set_created_at(db_session, august_be["id"], datetime(2026, 8, 2, 8, 0, tzinfo=timezone.utc))
    _set_created_at(db_session, september_ope.id, datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc))

    body = _volume(client)
    by_month = {row["month"]: row for row in body["by_month"]}
    assert list(by_month) == ["2026-07", "2026-08", "2026-09"]
    assert by_month["2026-07"] == {"month": "2026-07", "total": 1, "app": 1, "be": 0, "operativa": 0}
    assert by_month["2026-08"] == {"month": "2026-08", "total": 1, "app": 0, "be": 1, "operativa": 0}
    assert by_month["2026-09"] == {"month": "2026-09", "total": 1, "app": 0, "be": 0, "operativa": 1}
    for row in body["by_month"]:
        assert row["app"] + row["be"] + row["operativa"] == row["total"]


def test_volume_fills_empty_months_between_first_and_last(client, db_session) -> None:
    early = _create_app(client, name="Early", version="1.0")
    late = _create_app(client, name="Late", version="2.0")
    _set_created_at(db_session, early["id"], datetime(2026, 6, 1, tzinfo=timezone.utc))
    _set_created_at(db_session, late["id"], datetime(2026, 8, 1, tzinfo=timezone.utc))

    months = [row["month"] for row in _volume(client)["by_month"]]
    assert months == ["2026-06", "2026-07", "2026-08"]
    gap = next(row for row in _volume(client)["by_month"] if row["month"] == "2026-07")
    assert gap["total"] == 0
