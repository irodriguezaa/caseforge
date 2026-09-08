"""KPI 3: QC validation participations per official cluster."""

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


def _kpis(client):
    return client.get("/api/v1/kpis/releases").json()


def _by_cluster(body) -> dict[str, int]:
    return {row["cluster"]: row["count"] for row in body["by_cluster"]}


def test_app_single_cluster_is_one_participation(client) -> None:
    _create_app(client, name="App AUP", version="1.0", cluster="AUP")
    body = _kpis(client)
    assert body["total"] == 1
    assert _by_cluster(body) == {"Global": 0, "AUP": 1, "CENAM": 0, "Andina": 0, "Dominicana": 0}
    assert body["cluster_validations_total"] == 1
    assert body["clusters_per_release_avg"] == 1.0


def test_app_todos_expands_to_five_clusters(client) -> None:
    _create_app(client, name="App Todos", version="1.0", cluster="Todos")
    body = _kpis(client)
    assert body["total"] == 1
    assert _by_cluster(body) == {"Global": 1, "AUP": 1, "CENAM": 1, "Andina": 1, "Dominicana": 1}
    assert body["cluster_validations_total"] == 5
    assert body["clusters_per_release_avg"] == 5.0


def test_be_multi_cluster_one_participation_each_and_one_release(client) -> None:
    _create_be_qc(client, "BE Multi", clusters=["AUP", "Andina", "CENAM"])
    body = _kpis(client)
    assert body["total"] == 1
    assert body["be"] == 1
    counts = _by_cluster(body)
    assert counts["AUP"] == 1
    assert counts["Andina"] == 1
    assert counts["CENAM"] == 1
    assert counts["Global"] == 0
    assert counts["Dominicana"] == 0
    assert body["cluster_validations_total"] == 3
    assert body["clusters_per_release_avg"] == 3.0


def test_be_todos_expands_to_five_and_does_not_use_concat_label(client) -> None:
    created = _create_be_qc(client, "BE Todos", clusters=["Todos"])
    assert created.get("cluster") == "Todos"
    body = _kpis(client)
    assert body["total"] == 1
    assert body["cluster_validations_total"] == 5
    assert _by_cluster(body) == {"Global": 1, "AUP": 1, "CENAM": 1, "Andina": 1, "Dominicana": 1}


def test_operativa_single_cluster(client, db_session) -> None:
    ope_row = OperativaRelease(name="OPE AUP", pdf_filename="ope.pdf")
    db_session.add(ope_row)
    db_session.commit()
    db_session.add(
        Release(
            name="OPE AUP",
            version="OPE",
            platform="Operativa",
            cluster="AUP",
            operativa_release_id=ope_row.id,
        )
    )
    db_session.commit()
    body = _kpis(client)
    assert body["total"] == 1
    assert body["operativa"] == 1
    assert _by_cluster(body)["AUP"] == 1
    assert body["cluster_validations_total"] == 1


def test_cancelled_deleted_and_drafts_are_excluded_from_cluster_kpi(client, db_session) -> None:
    _create_app(client, name="Keep", version="1.0", cluster="Global")
    cancelled = _create_app(client, name="Cancel", version="2.0", cluster="AUP")
    client.patch(f"/api/v1/releases/{cancelled['id']}", json={"status": "CANCELLED"})
    drop = _create_app(client, name="Drop", version="3.0", cluster="CENAM")
    client.delete(f"/api/v1/releases/{drop['id']}")
    orphan_be = client.post("/api/v1/releases-be").json()
    assert orphan_be["qc_release_id"] is None
    db_session.add(OperativaRelease(name="OPE Draft", pdf_filename="draft.pdf"))
    db_session.commit()

    body = _kpis(client)
    assert body["total"] == 1
    assert _by_cluster(body)["Global"] == 1
    assert _by_cluster(body)["AUP"] == 0
    assert _by_cluster(body)["CENAM"] == 0
    assert body["cluster_validations_total"] == 1


def test_cluster_average_and_sum_across_mixed_releases(client, db_session) -> None:
    _create_app(client, name="App AUP", version="1.0", cluster="AUP")
    _create_app(client, name="App Todos", version="2.0", cluster="Todos")
    _create_be_qc(client, "BE Three", clusters=["AUP", "Andina", "CENAM"])
    ope_row = OperativaRelease(name="OPE CENAM", pdf_filename="ope.pdf")
    db_session.add(ope_row)
    db_session.commit()
    db_session.add(
        Release(
            name="OPE CENAM",
            version="OPE",
            platform="Operativa",
            cluster="CENAM",
            operativa_release_id=ope_row.id,
        )
    )
    db_session.commit()

    body = _kpis(client)
    assert body["total"] == 4
    counts = _by_cluster(body)
    # App AUP=1 + App Todos=1 + BE=1 → AUP 3
    # App Todos=1 + BE=1 + OPE=1 → CENAM 3
    # App Todos=1 + BE=1 → Andina 2
    # App Todos=1 → Global 1, Dominicana 1
    assert counts == {"Global": 1, "AUP": 3, "CENAM": 3, "Andina": 2, "Dominicana": 1}
    assert body["cluster_validations_total"] == 10
    assert body["clusters_per_release_avg"] == 2.5
    assert sum(counts.values()) == body["cluster_validations_total"]
    assert body["app"] + body["be"] + body["operativa"] == body["total"]
