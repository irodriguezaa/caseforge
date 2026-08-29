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


def test_preview_excludes_cancelled_tickets_entirely(client) -> None:
    csv_text = CSV_HEADER + (
        "OPE-1,Bug,PROJ,Critical,Cancelada,10/ene/26 10:00 AM,,,,\n"
        "OPE-2,Bug,PROJ,Critical,Finalizada,10/ene/26 10:00 AM,,,,\n"
    )
    body = _upload(client, csv_text).json()
    assert body["valid_count"] == 1
    assert body["excluded_cancelled_count"] == 1
    assert body["valid"][0]["issue_key"] == "OPE-2"


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


def test_dispt_project_is_excluded_from_release_entirely(client) -> None:
    csv_text = CSV_HEADER + "REL-1,QC Bug,DISPT,Critical,Analysis,10/ene/26 10:00 AM,,,,\n"
    body = _upload(client, csv_text, view="RELEASE").json()
    assert body["valid_count"] == 0
    assert body["error_count"] == 0  # excluded silently by design (matches REL_OPERATIVO_FINAL), not an error


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
    assert stats["total"] == 3
    assert stats["qc_detected_count"] == 2
    assert stats["leaked_count"] == 1
    assert stats["leak_rate_percent"] == 33.3
    assert stats["by_cluster"]["AUP"] == 2
    assert stats["by_cluster"]["CENAM"] == 1
    assert stats["by_month"]["2026-01"] == 2
    assert stats["by_month"]["2026-02"] == 1


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


def test_get_qc_radar_config_returns_canonical_single_source_of_truth(client) -> None:
    response = client.get("/api/v1/qc-tickets/filters")
    assert response.status_code == 200
    config = response.json()
    assert config["OPERATIVAS"]["detected"]["filter_id"] == "112929"
    assert config["OPERATIVAS"]["detected"]["label"] == "Detección QC"
    assert config["OPERATIVAS"]["leaked"]["filter_id"] == "113062"
    assert config["OPERATIVAS"]["leaked"]["label"] == "Fuga"
    assert config["RELEASE"]["detected"]["filter_id"] == "113261"
    assert config["RELEASE"]["detected"]["label"] == "QC/QA Bugs"
    assert config["RELEASE"]["leaked"]["filter_id"] == "113784"
    assert config["RELEASE"]["leaked"]["label"] == "Fuga"
