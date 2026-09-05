CSV_HEADER = (
    "Clave de incidencia,Tipo de Incidencia,Clave del proyecto,Prioridad,Estado,Creada,Resuelta,"
    "Resumen,\"Campo personalizado (Cluster)\",\"Campo personalizado (Programa Afectado)\"\n"
)


def _upload(client, csv_text: str, view: str = "OPERATIVAS", source: str = "QC_DETECTED"):
    return client.post(
        "/api/v1/qc-tickets/import/preview",
        files={"file": ("export.csv", csv_text.encode("utf-8"), "text/csv")},
        data={"view": view, "source": source},
    )


def test_preview_parses_real_jira_export_format(client) -> None:
    csv_text = CSV_HEADER + (
        "OPE-1234,QC Bug,WEBCL,Impedimento,To Develop,25/ago/26 03:45 PM,,"
        "Crash on play,AUP,Claro Video Web\n"
    )
    response = _upload(client, csv_text)

    assert response.status_code == 200
    body = response.json()
    assert body["valid_count"] == 1
    assert body["error_count"] == 0
    ticket = body["valid"][0]
    assert ticket["issue_key"] == "OPE-1234"
    assert ticket["priority_bucket"] == "BLOCKER"
    assert ticket["is_open"] is True
    assert ticket["cluster"] == "AUP"
    assert ticket["created_date"] == "2026-08-25"
    # "Claro Video Web" -> WEBCL (QCO_MAP) -> SWF HITSS (OPE_SWF_MAP)
    assert ticket["device"] == "WEBCL"
    assert ticket["swf"] == "HITSS"


def test_preview_computes_pre_post_device_from_cutoff_date(client) -> None:
    """TVOS is a PRE/POST-variant program: before 20-abr-2026 -> TVOSCL, after -> TVOSPR."""
    csv_text = CSV_HEADER + (
        "OPE-1,Bug,PROJ,Otros,Analysis,01/ene/26 10:00 AM,,,,TVOS\n"
        "OPE-2,Bug,PROJ,Otros,Analysis,01/ago/26 10:00 AM,,,,TVOS\n"
    )
    body = _upload(client, csv_text).json()
    by_key = {t["issue_key"]: t for t in body["valid"]}
    assert by_key["OPE-1"]["device"] == "TVOSCL"
    assert by_key["OPE-1"]["swf"] == "HITSS"
    assert by_key["OPE-2"]["device"] == "TVOSPR"
    assert by_key["OPE-2"]["swf"] == "NEORIS"


def test_preview_keeps_cancelled_tickets_as_closed(client) -> None:
    """Filter totals (e.g. #112929 = 2,462) include Cancelada; they must not inflate backlog."""
    csv_text = CSV_HEADER + (
        "OPE-1,Bug,PROJ,Critical,Cancelada,10/ene/26 10:00 AM,,,,\n"
        "OPE-2,Bug,PROJ,Critical,Finalizada,10/ene/26 10:00 AM,,,,\n"
    )
    body = _upload(client, csv_text).json()
    assert body["valid_count"] == 2
    assert body["excluded_cancelled_count"] == 0
    by_key = {t["issue_key"]: t for t in body["valid"]}
    assert by_key["OPE-1"]["is_open"] is False
    assert by_key["OPE-2"]["is_open"] is False


def test_release_view_uses_finalizada_or_roll_out_as_closed(client) -> None:
    csv_text = CSV_HEADER + (
        "REL-1,QC Bug,CENAM,Critical,Roll Out,10/ene/26 10:00 AM,,,,\n"
        "REL-2,QC Bug,CENAM,Critical,Finalizada,10/ene/26 10:00 AM,,,,\n"
        "REL-3,QC Bug,CENAM,Critical,Analysis,10/ene/26 10:00 AM,,,,\n"
    )
    body = _upload(client, csv_text, view="RELEASE").json()
    by_key = {t["issue_key"]: t for t in body["valid"]}
    assert by_key["REL-1"]["is_open"] is False  # Roll Out counts as closed for Release
    assert by_key["REL-2"]["is_open"] is False
    assert by_key["REL-3"]["is_open"] is True
    # CENAM -> BE (HITSS) (REL_OPERATIVO_FINAL) -> SWF HITSS (REL_SWF_MAP2)
    assert by_key["REL-1"]["swf"] == "HITSS"


def test_release_view_operativas_only_status_finalizada_closes(client) -> None:
    """Same 'Roll Out' status must NOT close an Operativas ticket -- only 'Finalizada' does."""
    csv_text = CSV_HEADER + "OPE-1,Bug,PROJ,Otros,Roll Out,10/ene/26 10:00 AM,,,,\n"
    body = _upload(client, csv_text, view="OPERATIVAS").json()
    assert body["valid"][0]["is_open"] is True


def test_dispt_project_counts_in_release_total_as_otros(client) -> None:
    csv_text = CSV_HEADER + "REL-1,QC Bug,DISPT,Critical,Analysis,10/ene/26 10:00 AM,,,,\n"
    body = _upload(client, csv_text, view="RELEASE").json()
    assert body["valid_count"] == 1
    assert body["valid"][0]["swf"] == "OTROS"


def test_preview_resolves_andina_dominicana_via_country_in_summary(client) -> None:
    csv_text = CSV_HEADER + (
        'OPE-100,Bug,PROJ,Critical,Finalizada,10/ene/26 10:00 AM,,"Falla en Ecuador para app",'
        'Andina/Dominicana,\n'
        'OPE-101,Bug,PROJ,Critical,Finalizada,10/ene/26 10:00 AM,,"Reportado en Rep. Dominicana (RD)",'
        'Andina/Dominicana,\n'
        'OPE-102,Bug,PROJ,Critical,Finalizada,10/ene/26 10:00 AM,,"Ticket sin país mencionado",'
        'Andina/Dominicana,\n'
    )
    body = _upload(client, csv_text).json()

    assert body["valid_count"] == 3
    by_key = {t["issue_key"]: t for t in body["valid"]}
    assert by_key["OPE-100"]["cluster"] == "Andina"
    assert by_key["OPE-101"]["cluster"] == "Dominicana"
    assert by_key["OPE-102"]["cluster"] == "Andina/Dominicana"  # kept visible, not dropped

    messages = " ".join(w["message"] for w in body["warnings"])
    assert "resuelto a Andina" in messages
    assert "resuelto a Dominicana" in messages
    assert "no se pudo resolver" in messages


def test_preview_folds_mexico_into_global_with_warning(client) -> None:
    csv_text = CSV_HEADER + (
        "OPE-1,Bug,PROJ,Critical,Finalizada,10/ene/26 10:00 AM,,,"
        "Mexico,Player\n"
    )
    body = _upload(client, csv_text).json()

    assert body["valid_count"] == 1
    assert body["valid"][0]["cluster"] == "Global"
    assert body["valid"][0]["is_open"] is False  # Finalizada -> closed
    assert any("agrupó bajo Global" in w["message"] for w in body["warnings"])


def test_preview_rejects_missing_required_columns(client) -> None:
    csv_text = "Clave de incidencia,Prioridad\nOPE-1,Critical\n"
    response = _upload(client, csv_text)
    assert response.status_code == 422
    assert "status_raw" in response.json()["detail"]


def test_preview_flags_duplicate_issue_key_within_file(client) -> None:
    csv_text = CSV_HEADER + (
        "OPE-1,Bug,PROJ,Critical,Finalizada,10/ene/26 10:00 AM,,,,\n"
        "OPE-1,Bug,PROJ,Critical,Finalizada,11/ene/26 10:00 AM,,,,\n"
    )
    body = _upload(client, csv_text).json()
    assert body["valid_count"] == 1
    assert body["error_count"] == 1


def test_bulk_create_is_transactional_and_source_is_set_by_upload_choice(client) -> None:
    csv_text = CSV_HEADER + "OPE-5,Bug,PROJ,Critical,Finalizada,10/ene/26 10:00 AM,,,,\n"
    preview = _upload(client, csv_text, source="LEAKED").json()
    assert preview["valid"][0]["source"] == "LEAKED"

    persist = client.post("/api/v1/qc-tickets/bulk", json=preview["valid"])
    assert persist.status_code == 201
    body = persist.json()
    assert len(body["created"]) == 1
    assert body["created"][0]["source"] == "LEAKED"


def test_stats_computes_leak_rate_and_breakdowns(client) -> None:
    detected_csv = CSV_HEADER + (
        "OPE-10,Bug,PROJ,Critical,Finalizada,10/ene/26 10:00 AM,,,AUP,\n"
        "OPE-11,Bug,PROJ,Impedimento,Finalizada,15/ene/26 10:00 AM,,,AUP,\n"
    )
    leaked_csv = CSV_HEADER + "OPE-12,Bug,PROJ,Critical,Finalizada,10/feb/26 10:00 AM,,,CENAM,\n"

    detected_preview = _upload(client, detected_csv, source="QC_DETECTED").json()
    client.post("/api/v1/qc-tickets/bulk", json=detected_preview["valid"])
    leaked_preview = _upload(client, leaked_csv, source="LEAKED").json()
    client.post("/api/v1/qc-tickets/bulk", json=leaked_preview["valid"])

    stats = client.get("/api/v1/qc-tickets/stats", params={"view": "OPERATIVAS"}).json()
    assert stats["total"] == 2
    assert stats["qc_detected_count"] == 2
    assert stats["leaked_count"] == 1
    assert stats["leak_rate_percent"] == 33.3
    assert stats["by_cluster"]["AUP"] == 2
    assert "CENAM" not in stats["by_cluster"]
    assert stats["by_month"]["2026-01"] == 2
    assert "2026-02" not in stats["by_month"]
    assert stats["leak_by_month"]["2026-02"]["leaked"] == 1.0


def test_stats_new_aggregations_operativas(client) -> None:
    """Validates the expanded-dashboard fields against real computed values, not just
    presence -- by_month_priority, open_by_priority, by_status, by_device (with the documented
    CL/PR grouping for the 5 exception families), by_program, and leak_by_month."""
    csv_text = CSV_HEADER + (
        # Two TVOS tickets straddling the PRE/POST cutoff (20 abr 2026) -> TVOSCL + TVOSPR,
        # must display-group into a single "TVOS" bucket in by_device.
        "OPE-20,Bug,PROJ,Impedimento,To Develop,10/abr/26 10:00 AM,,,AUP,TVOS\n"
        "OPE-21,Bug,PROJ,Critical,Finalizada,25/abr/26 10:00 AM,,,AUP,TVOS\n"
        # A closed ticket -- must NOT count into open_by_priority / by_status (backlog is
        # open-only).
        "OPE-22,Bug,PROJ,Critical,Finalizada,10/abr/26 10:00 AM,,,AUP,TVOS\n"
    )
    preview = _upload(client, csv_text, source="QC_DETECTED").json()
    assert preview["errors"] == []
    client.post("/api/v1/qc-tickets/bulk", json=preview["valid"])

    stats = client.get("/api/v1/qc-tickets/stats", params={"view": "OPERATIVAS"}).json()

    # by_month_priority: April has 1 Blocker (OPE-20) + 2 Critical (OPE-21, OPE-22)
    assert stats["by_month_priority"]["2026-04"] == {"BLOCKER": 1, "CRITICAL": 2, "OTHER": 0}

    # open_by_priority / by_status: only OPE-20 (To Develop) and OPE-21 (open per Operativas
    # rule, since only "Finalizada" closes) are open -- OPE-22 is Finalizada, excluded.
    # Actually OPE-21 is "Finalizada" too -- only OPE-20 is open.
    assert stats["open_by_priority"] == {"BLOCKER": 1}
    assert stats["by_status"] == {"To Develop": 1}

    # by_device: TVOSCL (OPE-20, before cutoff) + TVOSPR (OPE-21, OPE-22, after cutoff) must
    # group into one "TVOS" bucket of 3, not two separate CL/PR bars.
    assert stats["by_device"] == {"TVOS": 3}

    # by_program: raw affected_program, ungrouped.
    assert stats["by_program"] == {"TVOS": 3}

    # leak_by_month: all 3 are QC_DETECTED (no LEAKED here), so leaked=0 for April.
    assert stats["leak_by_month"]["2026-04"]["leaked"] == 0.0
    assert stats["leak_by_month"]["2026-04"]["rate"] == 0.0


def test_stats_new_aggregations_release(client) -> None:
    """Validates severity_by_swf, swf_by_month, by_quarter, leak_by_swf, and leak_by_project
    for the Release view."""
    qc_csv = CSV_HEADER + (
        "REL-30,Bug,CENAM,Impedimento,Finalizada,10/ene/26 10:00 AM,,,,\n"
        "REL-31,Bug,CENAM,Critical,Finalizada,15/abr/26 10:00 AM,,,,\n"
    )
    qc_preview = _upload(client, qc_csv, view="RELEASE", source="QC_DETECTED").json()
    assert qc_preview["errors"] == []
    client.post("/api/v1/qc-tickets/bulk", json=qc_preview["valid"])

    leaked_csv = (
        'Clave de incidencia,Clave del proyecto,Prioridad,Estado,Creada,"Enlace a la incidencia (Relates)"\n'
        "REL-32,CENAM,Critical,Finalizada,15/abr/26 10:00 AM,\n"
    )
    leaked_preview = _upload(client, leaked_csv, view="RELEASE", source="LEAKED").json()
    assert leaked_preview["errors"] == []
    client.post("/api/v1/qc-tickets/bulk", json=leaked_preview["valid"])

    stats = client.get("/api/v1/qc-tickets/stats", params={"view": "RELEASE"}).json()

    # CENAM maps to SWF "HITSS" — volume KPIs follow #113261 (QC/QA Bugs), not fuga.
    swf_key = next(iter(stats["by_swf"].keys()))
    assert stats["severity_by_swf"][swf_key] == {"BLOCKER": 1, "CRITICAL": 1, "OTHER": 0}

    assert stats["swf_by_month"]["2026-01"] == {swf_key: 1}
    assert stats["swf_by_month"]["2026-04"][swf_key] == 1

    assert stats["by_quarter"]["2026-Q1"] == 1
    assert stats["by_quarter"]["2026-Q2"] == 1

    assert stats["leak_by_swf"] == {swf_key: 1}
    assert stats["leak_by_project"] == {"CENAM": 1}


def test_release_fuga_genuina_excludes_tickets_already_attributed_to_a_qc_qa_bug(client) -> None:
    """A leaked ticket linked to an already-imported QC/QA Bug is NOT a genuine leak."""
    qc_bugs_csv = CSV_HEADER + "REL-BUG-1,QC Bug,CENAM,Critical,Finalizada,10/ene/26 10:00 AM,,,,\n"
    qc_preview = _upload(client, qc_bugs_csv, view="RELEASE", source="QC_DETECTED").json()
    client.post("/api/v1/qc-tickets/bulk", json=qc_preview["valid"])

    fuga_csv = (
        'Clave de incidencia,Clave del proyecto,Prioridad,Estado,Creada,"Enlace a la incidencia (Relates)"\n'
        "REL-FUGA-1,CENAM,Critical,Finalizada,10/ene/26 10:00 AM,REL-BUG-1\n"
        "REL-FUGA-2,CENAM,Critical,Finalizada,10/ene/26 10:00 AM,\n"
    )
    fuga_preview = _upload(client, fuga_csv, view="RELEASE", source="LEAKED").json()
    by_key = {t["issue_key"]: t for t in fuga_preview["valid"]}
    assert by_key["REL-FUGA-1"]["is_attributed"] is True
    assert by_key["REL-FUGA-2"]["is_attributed"] is False

    client.post("/api/v1/qc-tickets/bulk", json=fuga_preview["valid"])
    stats = client.get("/api/v1/qc-tickets/stats", params={"view": "RELEASE"}).json()
    assert stats["leaked_count"] == 2
    assert stats["genuine_leak_count"] == 1  # only REL-FUGA-2


def test_stats_bug_type_qc_excludes_qa_and_leaked_tickets(client) -> None:
    """QC-only view must exclude QA Bug tickets AND exclude LEAKED-source tickets entirely --
    fuga is a QA+QC-only concept per product decision."""
    csv_text = CSV_HEADER + (
        "REL-40,QC Bug,CENAM,Impedimento,Finalizada,10/ene/26 10:00 AM,,,,\n"
        "REL-41,QA Bug,CENAM,Critical,Finalizada,10/ene/26 10:00 AM,,,,\n"
    )
    preview = _upload(client, csv_text, view="RELEASE", source="QC_DETECTED").json()
    assert preview["errors"] == []
    client.post("/api/v1/qc-tickets/bulk", json=preview["valid"])

    leaked_csv = (
        'Clave de incidencia,Clave del proyecto,Prioridad,Estado,Creada,"Enlace a la incidencia (Relates)"\n'
        "REL-42,CENAM,Critical,Finalizada,10/ene/26 10:00 AM,\n"
    )
    leaked_preview = _upload(client, leaked_csv, view="RELEASE", source="LEAKED").json()
    client.post("/api/v1/qc-tickets/bulk", json=leaked_preview["valid"])

    qc_stats = client.get("/api/v1/qc-tickets/stats", params={"view": "RELEASE", "bug_type": "QC"}).json()
    assert qc_stats["total"] == 1
    assert qc_stats["blocker_count"] == 1
    assert qc_stats["leaked_count"] == 0

    qa_stats = client.get("/api/v1/qc-tickets/stats", params={"view": "RELEASE", "bug_type": "QA"}).json()
    assert qa_stats["total"] == 1
    assert qa_stats["critical_count"] == 1

    all_stats = client.get("/api/v1/qc-tickets/stats", params={"view": "RELEASE"}).json()
    assert all_stats["total"] == 2  # QA+QC Bugs only (filter 113261); fuga stays out of Total
    assert all_stats["leaked_count"] == 1


def test_list_qc_tickets_bug_type_filter(client) -> None:
    csv_text = CSV_HEADER + (
        "REL-50,QC Bug,CENAM,Impedimento,Finalizada,10/ene/26 10:00 AM,,,,\n"
        "REL-51,QA Bug,CENAM,Critical,Finalizada,10/ene/26 10:00 AM,,,,\n"
    )
    preview = _upload(client, csv_text, view="RELEASE", source="QC_DETECTED").json()
    client.post("/api/v1/qc-tickets/bulk", json=preview["valid"])

    qc_only = client.get("/api/v1/qc-tickets", params={"view": "RELEASE", "bug_type": "QC"}).json()
    assert [t["issue_key"] for t in qc_only] == ["REL-50"]


def test_jira_refresh_upserts_existing_and_creates_new(client, monkeypatch) -> None:
    from datetime import date

    from app.models.qc_ticket import QcTicketPriority, QcTicketSource, QcTicketView
    from app.schemas.qc_tickets import QcTicketCreate
    from app.services.jira_client import JiraFetchResult

    csv_text = CSV_HEADER + (
        "OPE-1,Bug,PROJ,Critical,To Develop,10/ene/26 10:00 AM,,,AUP,\n"
        "OPE-STALE,Bug,PROJ,Critical,To Develop,10/ene/26 10:00 AM,,,AUP,\n"
    )
    preview = _upload(client, csv_text).json()
    client.post("/api/v1/qc-tickets/bulk", json=preview["valid"])

    def fake_discover() -> tuple[None, None]:
        return None, None

    def fake_fetch(filter_id, view, source, cluster_field_id=None, program_field_id=None):
        if source == QcTicketSource.QC_DETECTED:
            return JiraFetchResult(
                tickets=[
                    QcTicketCreate(
                        issue_key="OPE-1",
                        issue_type="Bug",
                        project_key="PROJ",
                        priority_bucket=QcTicketPriority.CRITICAL,
                        status_raw="Finalizada",
                        is_open=False,
                        view=QcTicketView.OPERATIVAS,
                        source=QcTicketSource.QC_DETECTED,
                        cluster="AUP",
                        created_date=date(2026, 1, 10),
                    ),
                    QcTicketCreate(
                        issue_key="OPE-99",
                        issue_type="Bug",
                        project_key="PROJ",
                        priority_bucket=QcTicketPriority.BLOCKER,
                        status_raw="Analysis",
                        is_open=True,
                        view=QcTicketView.OPERATIVAS,
                        source=QcTicketSource.QC_DETECTED,
                        cluster="CENAM",
                        created_date=date(2026, 8, 1),
                    ),
                ],
                skipped_invalid=[],
                raw_issue_count=2,
            )
        return JiraFetchResult(tickets=[], skipped_invalid=[], raw_issue_count=0)

    monkeypatch.setattr("app.routers.qc_tickets.jira_client.ensure_authenticated", lambda: None)
    monkeypatch.setattr("app.routers.qc_tickets.jira_client.discover_custom_field_ids", fake_discover)
    monkeypatch.setattr("app.routers.qc_tickets.jira_client.fetch_tickets_by_filter", fake_fetch)

    response = client.post("/api/v1/qc-tickets/jira/refresh", params={"view": "OPERATIVAS"})
    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 1
    assert body["updated"] == 1
    assert body["filter_ids"] == ["112929", "113062"]
    assert body["filters"][0]["filter_id"] == "112929"
    assert body["filters"][0]["jira_count"] == 2
    assert body["filters"][0]["mapped"] == 2

    tickets = {row["issue_key"]: row for row in client.get("/api/v1/qc-tickets", params={"view": "OPERATIVAS"}).json()}
    assert tickets["OPE-1"]["is_open"] is False
    assert tickets["OPE-1"]["status_raw"] == "Finalizada"
    assert tickets["OPE-99"]["cluster"] == "CENAM"
    assert "OPE-STALE" not in tickets


def test_jira_refresh_keeps_detection_and_leak_as_independent_rows(client, monkeypatch) -> None:
    """Same Jira key can exist in #112929 and #113062; leak must not overwrite detection."""
    from datetime import date

    from app.models.qc_ticket import QcTicketPriority, QcTicketSource, QcTicketView
    from app.schemas.qc_tickets import QcTicketCreate
    from app.services.jira_client import JiraFetchResult

    def fake_discover() -> tuple[None, None]:
        return None, None

    shared = QcTicketCreate(
        issue_key="OPE-OVERLAP",
        issue_type="Bug",
        project_key="PROJ",
        priority_bucket=QcTicketPriority.CRITICAL,
        status_raw="Analysis",
        is_open=True,
        view=QcTicketView.OPERATIVAS,
        source=QcTicketSource.QC_DETECTED,
        cluster="AUP",
        created_date=date(2026, 1, 10),
    )
    leaked = shared.model_copy(update={"source": QcTicketSource.LEAKED})

    def fake_fetch(filter_id, view, source, cluster_field_id=None, program_field_id=None):
        if source == QcTicketSource.QC_DETECTED:
            return JiraFetchResult(tickets=[shared], skipped_invalid=[], raw_issue_count=1)
        return JiraFetchResult(tickets=[leaked], skipped_invalid=[], raw_issue_count=1)

    monkeypatch.setattr("app.routers.qc_tickets.jira_client.ensure_authenticated", lambda: None)
    monkeypatch.setattr("app.routers.qc_tickets.jira_client.discover_custom_field_ids", fake_discover)
    monkeypatch.setattr("app.routers.qc_tickets.jira_client.fetch_tickets_by_filter", fake_fetch)

    response = client.post("/api/v1/qc-tickets/jira/refresh", params={"view": "OPERATIVAS"})
    assert response.status_code == 200
    body = response.json()
    assert body["created"] == 2

    stats = client.get("/api/v1/qc-tickets/stats", params={"view": "OPERATIVAS"}).json()
    assert stats["total"] == 1
    assert stats["qc_detected_count"] == 1
    assert stats["leaked_count"] == 1


def test_jira_refresh_aborts_when_detection_filter_is_empty(client, monkeypatch) -> None:
    from app.models.qc_ticket import QcTicketSource
    from app.services.jira_client import JiraFetchResult

    csv_text = CSV_HEADER + "OPE-KEEP,Bug,PROJ,Critical,To Develop,10/ene/26 10:00 AM,,,AUP,\n"
    preview = _upload(client, csv_text).json()
    client.post("/api/v1/qc-tickets/bulk", json=preview["valid"])

    monkeypatch.setattr("app.routers.qc_tickets.jira_client.ensure_authenticated", lambda: None)
    monkeypatch.setattr("app.routers.qc_tickets.jira_client.discover_custom_field_ids", lambda: (None, None))
    monkeypatch.setattr(
        "app.routers.qc_tickets.jira_client.fetch_tickets_by_filter",
        lambda *_args, **_kwargs: JiraFetchResult(tickets=[], skipped_invalid=[], raw_issue_count=0),
    )

    response = client.post("/api/v1/qc-tickets/jira/refresh", params={"view": "OPERATIVAS"})
    assert response.status_code == 502
    assert "0 issues" in response.json()["detail"]

    tickets = client.get("/api/v1/qc-tickets", params={"view": "OPERATIVAS"}).json()
    assert [row["issue_key"] for row in tickets] == ["OPE-KEEP"]
    assert tickets[0]["source"] == QcTicketSource.QC_DETECTED.value
