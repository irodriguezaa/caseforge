"""Coverage matrix phase-1 tests — Confluence HN, BRF consolidation, no TC expansion."""

from pathlib import Path

from app.models.epc import Epc, QcSuggestion
from app.services.operativa_engine.confluence import (
    confluence_html_to_text,
    extract_brf_page_id,
    extract_page_ids_from_text,
)
from app.services.operativa_engine.coverage_matrix import build_coverage_matrix
from app.services.operativa_engine.hn import parse_historias
from app.services.operativa_engine.jira_context import BrfContextBundle

FIXTURE = Path(__file__).parent / "fixtures" / "brf_17442_confluence_hn.txt"
JIRA_WITH_EPC = """
=== BRF BRF-17442 (Iniciativa) ===
FE|UY | OTT | Configurar el nuevo add on Sony One
=== CHILD EPC-21813 (Epic) ===
UY | OTT | Configurar el nuevo add on Sony One
=== CHILD EPC-21842 (Epic) ===
FE|UY | OTT | Configurar el nuevo add on Sony One
"""


def _epc(
    *,
    brf_key: str = "BRF-17442",
    epc_key: str = "EPC-21842",
    titulo: str = "FE|UY | OTT | Configurar el nuevo add on Sony One",
    dispositivos: list[str] | None = None,
) -> Epc:
    return Epc(
        id=1,
        operativa_release_id=1,
        release_id=10,
        brf_key=brf_key,
        epc_key=epc_key,
        titulo=titulo,
        alcance="Total",
        nota_rte=None,
        estado_jira="In Validate",
        qc_suggestion=QcSuggestion.SUGERIDO_INCLUIR,
        include_in_qc=True,
        alcance_funcional=None,
        dispositivos_aplicables=dispositivos
        or ["WEB", "AAF", "Android", "iOS", "tvOS", "Windows/XBOX", "Consolas", "Roku", "Fire TV", "Android TV STV"],
    )


def _bundle() -> BrfContextBundle:
    confluence = FIXTURE.read_text(encoding="utf-8")
    if confluence.startswith("=== CONFLUENCE"):
        confluence = confluence.split("\n", 1)[1].strip()
    return BrfContextBundle(
        brf_key="BRF-17442",
        jira_blob=JIRA_WITH_EPC,
        confluence_blob=confluence,
        confluence_page_id="6399164496",
        confluence_title="BRF-17442_UY | OTT | Configurar el nuevo add on Sony One",
    )


def test_confluence_html_to_text_decodes_entities() -> None:
    text = confluence_html_to_text("<p>HN005 - Integrar im&aacute;genes secundarias</p>")
    assert "imágenes" in text
    assert "HN005" in text


def test_extract_brf_page_id_prefers_matching_title() -> None:
    links = [
        {"object": {"title": "OPE Release notes", "url": "https://x.atlassian.net/wiki/pages?pageId=111"}},
        {"object": {"title": "BRF-17442_UY | OTT | Configurar el nuevo add on Sony One", "url": "https://x.atlassian.net/wiki/pages?pageId=6399164496"}},
    ]
    assert extract_brf_page_id(links, "BRF-17442") == "6399164496"


def test_extract_brf_page_id_matches_underscore_title_not_release_notes() -> None:
    links = [
        {"object": {"title": "OPE-SEPTIEMBRE-2026-AUP Release notes", "url": "https://x.atlassian.net/wiki/pages/viewpage.action?pageId=6721699844"}},
        {"object": {"title": "BRF_88020_PY | OTT | Realizar el alta de la oferta", "url": "https://x.atlassian.net/wiki/pages/viewpage.action?pageId=6694000001"}},
    ]
    assert extract_brf_page_id(links, "BRF-88020") == "6694000001"


def test_extract_page_ids_from_adf_inline_card_url() -> None:
    blob = "Consultar página de Confluence https://x.atlassian.net/wiki/spaces/ABC/pages/6694000001/BRF_88020_PY"
    assert extract_page_ids_from_text(blob) == ["6694000001"]


def test_parse_historias_splits_id_glued_to_hn_key() -> None:
    blob = "IDHN001 - Realizar alta del Type EST 1J\nIDHN002 - Implementar comunicación"
    assert [item.key for item in parse_historias(blob)] == ["HN001", "HN002"]


def test_parse_historias_skips_epc_when_real_hn_present() -> None:
    blob = JIRA_WITH_EPC + "\n" + FIXTURE.read_text(encoding="utf-8")
    keys = [item.key for item in parse_historias(blob)]
    assert "EPC-21813" not in keys
    assert "EPC-21842" not in keys
    assert "HN001" in keys
    assert "HN014" in keys
    assert len([key for key in keys if key.startswith("HN")]) == 14


def test_coverage_matrix_brf_17442_has_fourteen_behaviors() -> None:
    result = build_coverage_matrix(
        release_id=10,
        release_name="OPE-AGOSTO-2026-AUP",
        epcs=[
            _epc(epc_key="EPC-21842"),
            _epc(epc_key="EPC-21813", titulo="UY | OTT | Configurar el nuevo add on Sony One"),
        ],
        context_loader=lambda _key: _bundle(),
    )
    rows = [row for row in result.rows if row.brf_key == "BRF-17442"]
    assert len(rows) == 14
    hn_keys = sorted({key for row in rows for key in row.hn_keys})
    assert hn_keys == [f"HN{i:03d}" for i in range(1, 15)]
    assert {item.hn_key for item in result.hn_coverage} == set(hn_keys)
    assert result.hn_source_by_brf["BRF-17442"] == "CONFLUENCE"
    assert all({"EPC-21842", "EPC-21813"} <= set(row.epc_keys) for row in rows)
    behavior_keys = [row.behavior_key for row in rows]
    assert len(behavior_keys) == len(set(behavior_keys))
    assert all("Historia de negocio" not in row.behavior_title for row in rows)
    hn001 = next(row for row in rows if "HN001" in row.hn_keys)
    assert hn001.transactional is True
    assert hn001.mdp == []
    hn002 = next(row for row in rows if "HN002" in row.hn_keys)
    assert hn002.transactional is False
    assert hn002.mdp == []
    checkout = next(row for row in rows if "HN006" in row.hn_keys)
    assert "Checkout" in checkout.interaction_points
    assert "Landing Comercial" not in checkout.interaction_points


def test_coverage_matrix_email_channel_not_device() -> None:
    result = build_coverage_matrix(
        release_id=10,
        release_name="OPE-AGOSTO-2026-AUP",
        epcs=[_epc()],
        context_loader=lambda _key: _bundle(),
    )
    email_row = next(row for row in result.rows if "HN014" in row.hn_keys)
    assert email_row.channel == "Email"
    assert email_row.applicable_devices == []
    assert email_row.ecosystem is None


def test_coverage_matrix_checkout_ticket_tv_devices_only() -> None:
    result = build_coverage_matrix(
        release_id=10,
        release_name="OPE-AGOSTO-2026-AUP",
        epcs=[_epc()],
        context_loader=lambda _key: _bundle(),
    )
    checkout = next(row for row in result.rows if "HN006" in row.hn_keys)
    ticket = next(row for row in result.rows if "HN007" in row.hn_keys)
    assert set(checkout.applicable_devices) == {"tvOS", "Android TV STV", "Roku", "Fire TV"}
    assert set(ticket.applicable_devices) == {"tvOS", "Android TV STV", "Roku", "Fire TV"}
    assert "WEB" not in checkout.applicable_devices


def test_coverage_matrix_interaction_points_extracted_for_hn001() -> None:
    result = build_coverage_matrix(
        release_id=10,
        release_name="OPE-AGOSTO-2026-AUP",
        epcs=[_epc()],
        context_loader=lambda _key: _bundle(),
    )
    hn001 = next(row for row in result.rows if "HN001" in row.hn_keys)
    assert "Plan Selector" in hn001.interaction_points
    assert "Landing Comercial" in hn001.interaction_points
    assert "vCard" in hn001.interaction_points
    assert len(hn001.applicable_devices) == 10


def test_coverage_matrix_users_not_cartesian_by_default() -> None:
    result = build_coverage_matrix(
        release_id=10,
        release_name="OPE-AGOSTO-2026-AUP",
        epcs=[_epc()],
        context_loader=lambda _key: _bundle(),
    )
    visual = next(row for row in result.rows if "HN003" in row.hn_keys)
    assert visual.relevant_users == []
    email = next(row for row in result.rows if "HN014" in row.hn_keys)
    assert email.relevant_users == ["Registrado (tras alta)"]


def _jira_bundle(brf_key: str, blob: str) -> BrfContextBundle:
    return BrfContextBundle(brf_key=brf_key, jira_blob=blob, confluence_blob="")


def test_matrix_does_not_split_specialized_npvr_title() -> None:
    blob = (
        "HN002 Integrar URLs de NPVR.\n"
        "Criterios de aceptación: el canal debe tener timeshift y npvr habilitados en backend."
    )
    result = build_coverage_matrix(
        release_id=10,
        release_name="OPE",
        epcs=[_epc(brf_key="BRF-17603", epc_key="EPC-1", titulo="OTT | NPVR URLs")],
        context_loader=lambda _key: _jira_bundle("BRF-17603", blob),
    )
    rows = [row for row in result.rows if row.brf_key == "BRF-17603"]
    assert len(rows) == 1
    assert "TIMESHIFT" not in (rows[0].behavior_title or "")


def test_matrix_mantener_is_single_qc_review() -> None:
    blob = (
        "HN004 Mantener funcionalidades de Timeshift, NPVR y TV Everywhere.\n"
        "Criterios de aceptación: no se pierde timeshift ni npvr ni tv everywhere."
    )
    result = build_coverage_matrix(
        release_id=10,
        release_name="OPE",
        epcs=[_epc(brf_key="BRF-17833", epc_key="EPC-1", titulo="IPTV | cambio de canal")],
        context_loader=lambda _key: _jira_bundle("BRF-17833", blob),
    )
    rows = [row for row in result.rows if row.brf_key == "BRF-17833"]
    assert len(rows) == 1
    assert rows[0].origin == "QC_REVIEW"
    assert "TIMESHIFT" not in (rows[0].behavior_title or "")


def test_matrix_logo_channels_consolidate_to_one_behavior() -> None:
    blob = "\n".join(
        f"HN{idx:03d} Implementar el logotipo del canal Canal{idx}."
        for idx in range(2, 5)
    )
    result = build_coverage_matrix(
        release_id=10,
        release_name="OPE",
        epcs=[_epc(brf_key="BRF-17844", epc_key="EPC-1", titulo="OTT | alta canales")],
        context_loader=lambda _key: _jira_bundle("BRF-17844", blob),
    )
    rows = [row for row in result.rows if row.brf_key == "BRF-17844"]
    assert len(rows) == 1
    assert "Canal2" in (rows[0].test_data or "")
    assert "HN002" in rows[0].hn_keys
    assert "HN004" in rows[0].hn_keys


def test_matrix_timeshift_uses_iptv_not_ott_devices() -> None:
    blob = "HN003 Habilitar Timeshift en paquetes IPTV."
    result = build_coverage_matrix(
        release_id=10,
        release_name="OPE",
        epcs=[
            _epc(
                brf_key="BRF-17465",
                epc_key="EPC-1",
                titulo="OTT | baja y timeshift",
                dispositivos=["WEB", "Roku", "STB"],
            )
        ],
        context_loader=lambda _key: _jira_bundle("BRF-17465", blob),
    )
    row = next(row for row in result.rows if row.brf_key == "BRF-17465")
    assert row.ecosystem == "IPTV"
    assert row.applicable_devices == ["STB"]
    assert "Roku" not in row.applicable_devices


def test_matrix_incidental_roku_does_not_restrict_devices() -> None:
    blob = (
        "HN001 Iniciar el flujo de contratación.\n"
        "Criterios de aceptación: validar en todos los dispositivos. Nota: bug visto en Roku."
    )
    result = build_coverage_matrix(
        release_id=10,
        release_name="OPE",
        epcs=[_epc(brf_key="BRF-16018", epc_key="EPC-1")],
        context_loader=lambda _key: _jira_bundle("BRF-16018", blob),
    )
    row = next(row for row in result.rows if row.brf_key == "BRF-16018")
    assert "WEB" in row.applicable_devices
    assert len(row.applicable_devices) == 10


def test_matrix_identity_nombre_logo_same_channel() -> None:
    blob = (
        "HN001 Actualizar nombre del canal Demo.\n"
        "HN002 Actualizar logotipo del canal Demo."
    )
    result = build_coverage_matrix(
        release_id=10,
        release_name="OPE",
        epcs=[_epc(brf_key="BRF-17833", epc_key="EPC-1", titulo="OTT | identidad canal")],
        context_loader=lambda _key: _jira_bundle("BRF-17833", blob),
    )
    rows = [row for row in result.rows if row.brf_key == "BRF-17833"]
    assert len(rows) == 1
    assert "nombre y logotipo" in rows[0].behavior_title.lower()


def test_matrix_infra_is_out_of_scope_qc_review() -> None:
    result = build_coverage_matrix(
        release_id=10,
        release_name="OPE",
        epcs=[_epc(brf_key="BRF-17577", epc_key="EPC-21741", titulo="Habilitar IPs dentro del whitelist en UAT OPER")],
        context_loader=lambda _key: _jira_bundle("BRF-17577", "texto sin historias"),
    )
    rows = [row for row in result.rows if row.brf_key == "BRF-17577"]
    assert len(rows) == 1
    assert rows[0].scope_status == "OUT_OF_SCOPE"
    assert rows[0].origin == "QC_REVIEW"
