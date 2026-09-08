"""KPI 5–6: SWF distribution and App revalidaciones from persisted fields."""

from app.models.operativa_release import OperativaRelease
from app.models.release import Release
from app.services.release_kpis import swf_for_app_platform


def _create_app(client, **overrides):
    payload = {"name": "Claro Video", "version": "1.0", "platform": "WEB"}
    payload.update(overrides)
    response = client.post("/api/v1/releases", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_be_qc(client, name: str, swf: str, clusters: list[str] | None = None):
    draft = client.post("/api/v1/releases-be").json()
    patch = {
        "name": name,
        "swf": swf,
        "regresivo_scope": "SMOKE",
        "entregable": "BE Entregable",
    }
    if clusters is not None:
        patch["clusters"] = clusters
    client.patch(f"/api/v1/releases-be/{draft['id']}", json=patch)
    return client.post(f"/api/v1/releases-be/{draft['id']}/create-release").json()


def _kpis(client):
    return client.get("/api/v1/kpis/releases").json()


def test_app_platform_mapping_is_deterministic() -> None:
    hitss = ["WEB", "AAF Evolutivo", "AAF Legacy", "ADT", "FireTV", "WIN/XBOX", "WIN", "XBOX"]
    neoris = ["iOS", "tvOS", "Roku", "Coship9085", "ADR"]
    tata = ["STB IPTV", "STV Tata Samsung", "STV Tata Hisense", "SCTCL", "ATSCL"]
    for platform in hitss:
        assert swf_for_app_platform(platform) == "HITSS", platform
    for platform in neoris:
        assert swf_for_app_platform(platform) == "NEORIS", platform
    for platform in tata:
        assert swf_for_app_platform(platform) == "TATA", platform
    assert swf_for_app_platform("Kepler") is None
    assert swf_for_app_platform("IPTV AOSP") is None


def test_swf_counts_app_and_be_once_and_excludes_operativa(client, db_session) -> None:
    _create_app(client, name="Web 1", version="1.0", platform="WEB")
    _create_app(client, name="iOS 1", version="1.0", platform="iOS")
    _create_be_qc(client, "BE A", "BE Hitss", clusters=["AUP"])
    _create_be_qc(client, "BE B", "BE Neoris", clusters=["CENAM"])
    ope_row = OperativaRelease(name="OPE SWF", pdf_filename="ope.pdf")
    db_session.add(ope_row)
    db_session.commit()
    db_session.add(
        Release(
            name="OPE SWF",
            version="OPE",
            platform="Operativa",
            operativa_release_id=ope_row.id,
        )
    )
    db_session.commit()

    body = _kpis(client)
    assert body["total"] == 5
    assert body["operativa"] == 1
    swf = body["swf"]
    assert swf["considered"] == 4
    assert swf["unclassified"] == 0
    by_name = {row["swf"]: row for row in swf["by_swf"]}
    assert by_name["HITSS"]["releases"] == 1
    assert by_name["NEORIS"]["releases"] == 1
    assert by_name["BE Hitss"]["releases"] == 1
    assert by_name["BE Neoris"]["releases"] == 1
    assert "TATA" not in by_name
    assert sum(row["releases"] for row in swf["by_swf"]) == swf["considered"]
    assert {row["swf"] for row in swf["by_swf"]} == {"HITSS", "NEORIS", "BE Hitss", "BE Neoris"}


def test_unmapped_app_platform_is_unclassified_not_invented(client) -> None:
    _create_app(client, name="Kepler 1", version="1.0", platform="Kepler")
    swf = _kpis(client)["swf"]
    assert swf["considered"] == 1
    assert swf["unclassified"] == 1
    assert swf["by_swf"] == []
    row = swf["unclassified_rows"][0]
    assert row["origin"] == "APP"
    assert row["platform"] == "Kepler"
    assert "mapping" in row["reason"].lower() or "plataforma" in row["reason"].lower()


def test_aaf_variants_map_to_hitss_not_a_separate_swf(client) -> None:
    _create_app(client, name="AAF Evo", version="1.0", platform="AAF Evolutivo")
    _create_app(client, name="AAF Leg", version="1.0", platform="AAF Legacy")
    by_name = {row["swf"]: row for row in _kpis(client)["swf"]["by_swf"]}
    assert set(by_name) == {"HITSS"}
    assert by_name["HITSS"]["releases"] == 2


def test_revalidations_use_persisted_type_not_repeated_version(client) -> None:
    first = _create_app(
        client,
        name="N1",
        version="16.9.1",
        platform="WEB",
        deliverable_name="Tipo X",
        release_type="NUEVO",
    )
    _create_app(
        client,
        name="R1",
        version="16.9.1",
        platform="WEB",
        deliverable_name="Tipo X",
        release_type="REVALIDACION",
        parent_release_id=first["id"],
    )
    _create_app(
        client,
        name="R2",
        version="16.9.2",
        platform="WEB",
        deliverable_name="Tipo X",
        release_type="REVALIDACION",
        parent_release_id=first["id"],
    )
    rev = _kpis(client)["revalidation"]
    assert rev["total"] == 3
    assert rev["app"] == 3
    assert rev["nuevo"] == 1
    assert rev["revalidacion"] == 2
    assert rev["untyped_app"] == 0
    assert rev["revalidacion_percent"] == 66.7
    assert rev["scope"] == "APP"


def test_be_and_operativa_are_not_typed_as_revalidacion(client, db_session) -> None:
    _create_app(client, name="App Nuevo", version="1.0", platform="WEB", release_type="NUEVO")
    _create_be_qc(client, "BE C", "BE Nubiral", clusters=["Global"])
    ope_row = OperativaRelease(name="OPE REV", pdf_filename="ope.pdf")
    db_session.add(ope_row)
    db_session.commit()
    db_session.add(
        Release(
            name="OPE REV",
            version="OPE",
            platform="Operativa",
            operativa_release_id=ope_row.id,
        )
    )
    db_session.commit()
    rev = _kpis(client)["revalidation"]
    assert rev["total"] == 3
    assert rev["app"] == 1
    assert rev["nuevo"] == 1
    assert rev["revalidacion"] == 0
    assert rev["revalidacion_percent"] == 0.0


def test_cancelled_excluded_from_swf_and_revalidation(client) -> None:
    _create_app(
        client,
        name="Keep",
        version="1.0",
        platform="WEB",
        deliverable_name="Keep D",
        release_type="NUEVO",
    )
    drop = _create_app(
        client,
        name="Drop",
        version="2.0",
        platform="iOS",
        deliverable_name="Drop D",
        release_type="NUEVO",
    )
    client.patch(f"/api/v1/releases/{drop['id']}", json={"status": "CANCELLED"})
    body = _kpis(client)
    assert body["total"] == 1
    assert {row["swf"] for row in body["swf"]["by_swf"]} == {"HITSS"}
    assert body["revalidation"]["revalidacion"] == 0
    assert body["revalidation"]["nuevo"] == 1
