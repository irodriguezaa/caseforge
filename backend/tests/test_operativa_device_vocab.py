"""Operativa device vocabulary: ADR (OTT mobile), ADT (OTT STV), STB (IPTV)."""

from app.models.epc import Epc, QcSuggestion
from app.services.operativa_engine.coverage_matrix import build_coverage_matrix
from app.services.operativa_engine.devices import extract_devices_from_text, parse_declared_devices
from app.services.operativa_engine.jira_context import BrfContextBundle
from app.services.operativa_engine.matrix_expand import expand_matrix_preview


def test_named_devices_map_to_adr_adt_stb() -> None:
    found = extract_devices_from_text(
        "Dispositivos:\nAndroid\nAndroid TV para STV\nSTB (Android TV)\n",
        source="BRF-17892",
    )
    assert [item.label for item in found] == ["ADR", "ADT", "STB"]
    assert [item.ecosystem for item in found] == ["OTT", "OTT", "IPTV"]


def test_android_tv_without_stb_is_adt_not_stb() -> None:
    found = extract_devices_from_text("Android TV para STV", source="x")
    assert [item.label for item in found] == ["ADT"]
    found = extract_devices_from_text("STB (Android TV)", source="x")
    assert [item.label for item in found] == ["STB"]


def test_qc_selection_android_becomes_adr() -> None:
    found = parse_declared_devices(["Android", "Android TV para STV", "STB (Android TV)"])
    assert [item.label for item in found] == ["ADR", "ADT", "STB"]


def test_ott_and_iptv_title_keeps_all_three_devices() -> None:
    epc = Epc(
        id=1,
        operativa_release_id=1,
        release_id=10,
        brf_key="BRF-17892",
        epc_key="EPC-21987",
        titulo="BRF-17892_CENAM | OTT e IPTV | Habilitar medios de pago en dispositivos Android",
        alcance="Total",
        nota_rte=None,
        estado_jira="In Validate",
        qc_suggestion=QcSuggestion.SUGERIDO_INCLUIR,
        include_in_qc=True,
        alcance_funcional=None,
        dispositivos_aplicables=["Android", "Android TV para STV", "STB (Android TV)"],
    )
    blob = (
        "HN002 Habilitar medios de pago en dispositivos Android.\n"
        "Criterios de aceptación: el usuario habilita un medio de pago en Checkout y Ticket.\n"
    )
    matrix = build_coverage_matrix(
        release_id=10,
        release_name="OPE-SEPTIEMBRE-2026-CENAM",
        epcs=[epc],
        context_loader=lambda _key: BrfContextBundle(brf_key="BRF-17892", jira_blob=blob),
    )
    in_scope = [row for row in matrix.rows if row.scope_status == "IN_SCOPE"]
    assert in_scope
    devices = set()
    for row in in_scope:
        devices.update(row.applicable_devices)
    assert devices == {"ADR", "ADT"}
    assert all(row.ecosystem == "OTT" for row in in_scope)
    preview = expand_matrix_preview(matrix)
    assert {item.device for item in preview} == {"ADR", "ADT"}
    assert len(preview) == 2


def test_android_hns_expand_adr_and_adt_not_stb_when_header_mentions_iptv() -> None:
    epc = Epc(
        id=1,
        operativa_release_id=1,
        release_id=10,
        brf_key="BRF-17892",
        epc_key="EPC-21987",
        titulo="BRF-17892_CENAM | OTT e IPTV | Habilitar medios de pago en dispositivos Android",
        alcance="Total",
        nota_rte=None,
        estado_jira="In Validate",
        qc_suggestion=QcSuggestion.SUGERIDO_INCLUIR,
        include_in_qc=True,
        alcance_funcional=None,
        dispositivos_aplicables=["STB"],
    )
    blob = (
        "HN001 BRF-17892_CENAM | OTT e IPTV | Deshabilitar politicas de Google en dispositivos Android\n"
        "HN002 BRF-17892_CENAM | OTT e IPTV | Habilitar medios de pago en dispositivos Android.\n"
        "HN003 BRF-17892_CENAM | OTT e IPTV | Habilitar botón transaccional en dispositivos Android\n"
    )
    matrix = build_coverage_matrix(
        release_id=10,
        release_name="OPE-SEPTIEMBRE-2026-CENAM",
        epcs=[epc],
        context_loader=lambda _key: BrfContextBundle(brf_key="BRF-17892", jira_blob=blob),
    )
    in_scope = [row for row in matrix.rows if row.scope_status == "IN_SCOPE"]
    assert len(in_scope) == 3
    for row in in_scope:
        assert row.ecosystem == "OTT"
        assert set(row.applicable_devices) == {"ADR", "ADT"}
    preview = expand_matrix_preview(matrix)
    assert len(preview) == 6
    assert {item.device for item in preview} == {"ADR", "ADT"}
