def _create_release(client, **overrides):
    payload = {
        "name": overrides.pop("name", "CV WEB"),
        "version": overrides.pop("version", "7.8.1"),
        "platform": overrides.pop("platform", "WEB"),
        **overrides,
    }
    response = client.post("/api/v1/releases", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_get_or_create_deliverable_by_name(client) -> None:
    r1 = _create_release(client, version="1.0.0", deliverable_name="WEB - Funcionalidad X")
    r2 = _create_release(client, version="1.0.1", deliverable_name="web - funcionalidad x")  # case-insensitive match

    assert r1["deliverable_id"] is not None
    assert r1["deliverable_id"] == r2["deliverable_id"]

    r3 = _create_release(client, version="1.0.2", deliverable_name="WEB - Funcionalidad Y")
    assert r3["deliverable_id"] != r1["deliverable_id"]


def test_release_without_deliverable_name_stays_unclassified(client) -> None:
    release = _create_release(client, version="2.0.0")
    assert release["deliverable_id"] is None
    assert release["release_type"] is None


def test_nuevo_first_release_does_not_require_parent(client) -> None:
    release = _create_release(
        client, version="1.0.0", deliverable_name="WEB - X", release_type="NUEVO"
    )
    assert release["release_type"] == "NUEVO"
    assert release["parent_release_id"] is None


def test_evolutivo_is_not_an_accepted_release_type(client) -> None:
    response = client.post(
        "/api/v1/releases",
        json={
            "name": "CV WEB",
            "version": "1.0.0",
            "platform": "WEB",
            "deliverable_name": "WEB - X",
            "release_type": "EVOLUTIVO",
        },
    )
    assert response.status_code == 422


def test_nuevo_rejects_parent_release_id(client) -> None:
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="NUEVO")
    response = client.post(
        "/api/v1/releases",
        json={
            "name": "CV WEB", "version": "1.0.1", "platform": "WEB",
            "deliverable_name": "WEB - X", "release_type": "NUEVO", "parent_release_id": v1["id"],
        },
    )
    assert response.status_code == 422


def test_revalidacion_requires_parent(client) -> None:
    response = client.post(
        "/api/v1/releases",
        json={
            "name": "CV WEB", "version": "1.0.1", "platform": "WEB",
            "deliverable_name": "WEB - X", "release_type": "REVALIDACION",
        },
    )
    assert response.status_code == 422


def test_revalidacion_parent_must_belong_to_same_deliverable(client) -> None:
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="NUEVO")
    response = client.post(
        "/api/v1/releases",
        json={
            "name": "CV WEB", "version": "1.0.1", "platform": "WEB",
            "deliverable_name": "WEB - Y",  # different deliverable
            "release_type": "REVALIDACION", "parent_release_id": v1["id"],
        },
    )
    assert response.status_code == 409


def test_multiple_revalidaciones_of_the_same_deliverable(client) -> None:
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="NUEVO")
    v2 = _create_release(
        client, version="1.0.1", deliverable_name="WEB - X",
        release_type="REVALIDACION", parent_release_id=v1["id"],
    )
    v3 = _create_release(
        client, version="1.0.2", deliverable_name="WEB - X",
        release_type="REVALIDACION", parent_release_id=v2["id"],
    )
    assert v2["deliverable_id"] == v1["deliverable_id"] == v3["deliverable_id"]

    deliverable = client.get(f"/api/v1/deliverables/{v1['deliverable_id']}").json()
    assert deliverable["total_versions"] == 3
    assert deliverable["total_evolutivas"] == 1
    assert deliverable["total_revalidaciones"] == 2
    assert deliverable["latest_release_id"] == v3["id"]


def test_deliverable_releases_endpoint_backs_the_origin_dropdown(client) -> None:
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="NUEVO")
    _create_release(client, version="1.0.1", deliverable_name="WEB - X", release_type="REVALIDACION", parent_release_id=v1["id"])

    releases = client.get(f"/api/v1/deliverables/{v1['deliverable_id']}/releases").json()
    assert len(releases) == 2
    assert [r["version"] for r in releases] == ["1.0.0", "1.0.1"]
    assert {r["deliverable_id"] for r in releases} == {v1["deliverable_id"]}


def test_origin_dropdown_lists_same_entregable_even_when_release_names_differ(client) -> None:
    v1 = _create_release(
        client,
        name="RN-CV - WEB -16.9.0",
        version="16.9.0",
        deliverable_name="HBO WEB",
        release_type="NUEVO",
    )
    v2 = _create_release(
        client,
        name="HBO WEB 16.10",
        version="16.10.0",
        deliverable_name="HBO WEB",
        release_type="REVALIDACION",
        parent_release_id=v1["id"],
    )
    other = _create_release(
        client,
        name="Otro producto",
        version="1.0.0",
        platform="iOS",
        deliverable_name="Disney WEB",
        release_type="NUEVO",
    )

    by_name = client.get("/api/v1/deliverables", params={"name": "HBO WEB"}).json()
    assert len(by_name) == 1
    assert by_name[0]["id"] == v1["deliverable_id"]

    origins = client.get(f"/api/v1/deliverables/{v1['deliverable_id']}/releases").json()
    origin_ids = {row["id"] for row in origins}
    assert origin_ids == {v1["id"], v2["id"]}
    assert other["id"] not in origin_ids
    assert all(row["deliverable_id"] == v1["deliverable_id"] for row in origins)


def test_lineage_fields_editable_only_in_draft(client) -> None:
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="NUEVO")
    client.patch(f"/api/v1/releases/{v1['id']}", json={"status": "IN_PROGRESS"})

    response = client.patch(f"/api/v1/releases/{v1['id']}", json={"release_type": "REVALIDACION"})
    assert response.status_code == 409


def test_lineage_fields_editable_while_draft(client) -> None:
    v1 = _create_release(client, version="1.0.0")  # still DRAFT, no deliverable yet
    response = client.patch(f"/api/v1/releases/{v1['id']}", json={"deliverable_name": "WEB - X"})
    assert response.status_code == 200
    assert response.json()["deliverable_id"] is not None


def test_cannot_delete_release_that_is_an_origin(client) -> None:
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="NUEVO")
    _create_release(client, version="1.0.1", deliverable_name="WEB - X", release_type="REVALIDACION", parent_release_id=v1["id"])

    response = client.delete(f"/api/v1/releases/{v1['id']}")
    assert response.status_code == 409


def test_old_releases_without_deliverable_are_unaffected_by_new_fields(client) -> None:
    """Backward compatibility: a Release created the pre-existing way (no lineage fields at
    all) must behave exactly as before."""
    response = client.post(
        "/api/v1/releases",
        json={"name": "Legacy", "version": "1.0.0", "platform": "WEB"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["deliverable_id"] is None
    assert body["release_type"] is None
    assert body["parent_release_id"] is None

    listing = client.get("/api/v1/releases").json()
    legacy = next(r for r in listing if r["id"] == body["id"])
    assert legacy["deliverable_name"] is None


def test_deliverable_name_has_a_unique_constraint_at_the_db_level(db_session) -> None:
    """The get-or-create flow already prevents duplicates at the API layer -- this confirms the
    UNIQUE constraint requested as a hard safety net actually exists at the DB level too."""
    from sqlalchemy.exc import IntegrityError

    from app.models.deliverable import Deliverable

    db_session.add(Deliverable(name="WEB - X"))
    db_session.flush()
    db_session.add(Deliverable(name="WEB - X"))  # exact duplicate, bypassing the API entirely
    try:
        db_session.flush()
        raised = False
    except IntegrityError:
        raised = True
    assert raised


def test_cannot_set_a_release_as_its_own_parent(client) -> None:
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="NUEVO")
    v2 = _create_release(
        client, version="1.0.1", deliverable_name="WEB - X",
        release_type="REVALIDACION", parent_release_id=v1["id"],
    )
    response = client.patch(f"/api/v1/releases/{v2['id']}", json={"parent_release_id": v2["id"]})
    assert response.status_code == 422


def test_cannot_create_a_two_release_cycle(client) -> None:
    """V1 -> V2 already exists (V2's parent is V1). Trying to then make V1's parent be V2 would
    create a 2-cycle and must be rejected."""
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="NUEVO")
    v2 = _create_release(
        client, version="1.0.1", deliverable_name="WEB - X",
        release_type="REVALIDACION", parent_release_id=v1["id"],
    )
    response = client.patch(
        f"/api/v1/releases/{v1['id']}",
        json={"release_type": "REVALIDACION", "parent_release_id": v2["id"]},
    )
    assert response.status_code == 409


def test_cannot_create_a_longer_cycle_through_an_intermediate_release(client) -> None:
    """V1 -> V2 -> V3 already exists. Making V1's parent be V3 would create a 3-release cycle."""
    v1 = _create_release(client, version="1.0.0", deliverable_name="WEB - X", release_type="NUEVO")
    v2 = _create_release(
        client, version="1.0.1", deliverable_name="WEB - X",
        release_type="REVALIDACION", parent_release_id=v1["id"],
    )
    v3 = _create_release(
        client, version="1.0.2", deliverable_name="WEB - X",
        release_type="REVALIDACION", parent_release_id=v2["id"],
    )
    response = client.patch(
        f"/api/v1/releases/{v1['id']}",
        json={"release_type": "REVALIDACION", "parent_release_id": v3["id"]},
    )
    assert response.status_code == 409
