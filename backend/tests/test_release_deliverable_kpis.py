"""KPI: Releases por Entregable y Versiones (App only). Dynamic deliverable names from FK."""

from app.models.deliverable import Deliverable
from app.models.operativa_release import OperativaRelease
from app.models.release import Release
from app.services.release_kpis import SIN_ENTREGABLE_LABEL


def _create_app(client, **overrides):
    payload = {"name": "Claro Video", "version": "1.0", "platform": "WEB"}
    payload.update(overrides)
    response = client.post("/api/v1/releases", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_be_qc(client, name: str, clusters: list[str] | None = None, entregable: str | None = None):
    draft = client.post("/api/v1/releases-be").json()
    patch = {
        "name": name,
        "swf": "BE Hitss",
        "regresivo_scope": "SMOKE",
    }
    if clusters is not None:
        patch["clusters"] = clusters
    if entregable is not None:
        patch["entregable"] = entregable
    client.patch(f"/api/v1/releases-be/{draft['id']}", json=patch)
    return client.post(f"/api/v1/releases-be/{draft['id']}/create-release").json()


def _kpis(client):
    return client.get("/api/v1/kpis/releases").json()


def _by_name(body) -> dict[str, dict]:
    return {row["deliverable_name"]: row for row in body["by_deliverable"]}


def test_app_releases_and_distinct_versions_per_deliverable(client) -> None:
    _create_app(client, name="App A 1.0", version="1.0", deliverable_name="Alpha WEB")
    _create_app(client, name="App A 1.1", version="1.1", deliverable_name="Alpha WEB")
    _create_app(client, name="App B 9.0", version="9.0", deliverable_name="Beta iOS")
    body = _kpis(client)
    by_name = _by_name(body)
    assert by_name["Alpha WEB"]["releases"] == 2
    assert by_name["Alpha WEB"]["versions"] == 2
    assert by_name["Beta iOS"]["releases"] == 1
    assert by_name["Beta iOS"]["versions"] == 1
    assert {row["deliverable_name"] for row in body["by_deliverable"]} == {"Alpha WEB", "Beta iOS"}
    assert sum(row["releases"] for row in body["by_deliverable"]) == body["app"]


def test_revalidations_same_version_count_as_one_version(client) -> None:
    first = _create_app(
        client,
        name="Cycle 1",
        version="16.9.1",
        deliverable_name="Entregable X",
        release_type="NUEVO",
    )
    _create_app(
        client,
        name="Cycle 2",
        version="16.9.1",
        deliverable_name="Entregable X",
        release_type="REVALIDACION",
        parent_release_id=first["id"],
    )
    _create_app(
        client,
        name="Cycle 3",
        version="16.9.1",
        deliverable_name="Entregable X",
        release_type="REVALIDACION",
        parent_release_id=first["id"],
    )
    row = _by_name(_kpis(client))["Entregable X"]
    assert row["releases"] == 3
    assert row["versions"] == 1


def test_revalidations_new_version_counts_as_another_version(client) -> None:
    first = _create_app(
        client,
        name="Cycle 1",
        version="16.9.1",
        deliverable_name="Entregable Y",
        release_type="NUEVO",
    )
    _create_app(
        client,
        name="Cycle 2",
        version="16.9.2",
        deliverable_name="Entregable Y",
        release_type="REVALIDACION",
        parent_release_id=first["id"],
    )
    row = _by_name(_kpis(client))["Entregable Y"]
    assert row["releases"] == 2
    assert row["versions"] == 2


def test_groups_by_deliverable_id_not_release_name(client) -> None:
    _create_app(client, name="RN-CV - WEB -16.9.0", version="16.9.0", deliverable_name="Gamma WEB")
    _create_app(client, name="RN-CV - WEB -16.9.1", version="16.9.1", deliverable_name="Gamma WEB")
    rows = _kpis(client)["by_deliverable"]
    assert len(rows) == 1
    assert rows[0]["deliverable_name"] == "Gamma WEB"
    assert rows[0]["releases"] == 2
    assert rows[0]["versions"] == 2


def test_be_and_operativa_are_excluded_from_deliverable_kpi(client, db_session) -> None:
    _create_app(client, name="App Keep", version="1.0", deliverable_name="Alpha WEB")
    _create_be_qc(client, "BE One", clusters=["AUP"], entregable="Backend Uno")
    _create_be_qc(client, "BE Two", clusters=["CENAM"], entregable="Backend Uno")
    ope_row = OperativaRelease(name="OPE-MENSUAL-NORTE", pdf_filename="ope.pdf")
    ope_deliverable = Deliverable(name="OPE-MENSUAL-NORTE")
    db_session.add_all([ope_row, ope_deliverable])
    db_session.commit()
    db_session.add(
        Release(
            name="OPE-MENSUAL-NORTE",
            version="OPE",
            platform="Operativa",
            cluster="AUP",
            operativa_release_id=ope_row.id,
            deliverable_id=ope_deliverable.id,
        )
    )
    db_session.commit()

    body = _kpis(client)
    names = {row["deliverable_name"] for row in body["by_deliverable"]}
    assert names == {"Alpha WEB"}
    assert body["be"] == 2
    assert body["operativa"] == 1
    assert body["app"] == 1
    assert sum(row["releases"] for row in body["by_deliverable"]) == body["app"]


def test_missing_deliverable_uses_sin_entregable_bucket(client) -> None:
    _create_app(client, name="Orphan App", version="3.0")
    body = _kpis(client)
    row = _by_name(body)[SIN_ENTREGABLE_LABEL]
    assert row["deliverable_id"] is None
    assert row["releases"] == 1
    assert row["versions"] == 1


def test_sin_entregable_absent_when_every_release_has_deliverable(client) -> None:
    _create_app(client, name="Named", version="1.0", deliverable_name="Con Entregable")
    names = {row["deliverable_name"] for row in _kpis(client)["by_deliverable"]}
    assert SIN_ENTREGABLE_LABEL not in names


def test_sorted_by_releases_then_versions_desc(client) -> None:
    _create_app(client, name="Z1", version="1.0", deliverable_name="Zeta")
    _create_app(client, name="A1", version="1.0", deliverable_name="Alfa")
    _create_app(client, name="A2", version="1.0", deliverable_name="Alfa")
    _create_app(client, name="M1", version="1.0", deliverable_name="Mismo")
    _create_app(client, name="M2", version="2.0", deliverable_name="Mismo")
    rows = _kpis(client)["by_deliverable"]
    assert [row["deliverable_name"] for row in rows] == ["Mismo", "Alfa", "Zeta"]
    assert [row["releases"] for row in rows] == [2, 2, 1]
    assert [row["versions"] for row in rows] == [2, 1, 1]


def test_cancelled_and_unused_deliverable_rows_are_excluded(client, db_session) -> None:
    keep = _create_app(client, name="Keep", version="1.0", deliverable_name="Vivo")
    cancelled = _create_app(client, name="Cancel", version="2.0", deliverable_name="Vivo")
    client.patch(f"/api/v1/releases/{cancelled['id']}", json={"status": "CANCELLED"})
    db_session.add(Deliverable(name="Huérfano sin Releases"))
    db_session.commit()
    body = _kpis(client)
    names = {row["deliverable_name"] for row in body["by_deliverable"]}
    assert names == {"Vivo"}
    assert _by_name(body)["Vivo"]["releases"] == 1
    assert keep["deliverable_id"] is not None


def test_new_deliverable_appears_without_catalog(client) -> None:
    _create_app(client, name="First", version="1.0", deliverable_name="Nuevo Uno")
    assert {row["deliverable_name"] for row in _kpis(client)["by_deliverable"]} == {"Nuevo Uno"}
    _create_app(client, name="Second", version="1.0", deliverable_name="Nuevo Dos")
    names = {row["deliverable_name"] for row in _kpis(client)["by_deliverable"]}
    assert names == {"Nuevo Uno", "Nuevo Dos"}
