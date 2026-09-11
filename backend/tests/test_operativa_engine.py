"""Operativas engine: rules 65.x against real RN fixtures. Does not use Apps A–G."""

from pathlib import Path

from app.models.epc import Epc
from app.services.operativa_analyzer import analyze_operativa_rn
from app.services.operativa_engine import generate_operativa_candidates
from app.services.operativa_engine.families import FAMILY_INFRA, FAMILY_OFFER, classify_family
from app.services.operativa_engine.hn import parse_historias

JULIO = Path(__file__).parent / "fixtures" / "PMOGH-OPE-JULIO-2026-AND.pdf"
CENAM = Path(__file__).parent / "fixtures" / "PMOGH-OPE-AGOSTO-3-2026-CENAM.pdf"
GLB = Path(__file__).parent / "fixtures" / "PMOGH-OPE-SEPTIEMBRE-2026-GLB.pdf"
ENERO = Path(__file__).parent / "fixtures" / "PMOGH-OPE-ENERO-2026-DO.pdf"


def _epc(**kwargs) -> Epc:
    row = Epc(
        operativa_release_id=1,
        brf_key=kwargs["brf_key"],
        titulo=kwargs["titulo"],
        qc_suggestion="SUGERIDO_INCLUIR",
        include_in_qc=True,
    )
    for key, value in kwargs.items():
        setattr(row, key, value)
    return row


def test_hn_modifier_does_not_duplicate_superseded_criteria() -> None:
    blob = (
        "HN004 Comunicación original con copy A.\n"
        "HN008 actualiza la HN004 con copy vigente.\n"
        "HN005 Reportes de BI.\n"
        "HN006 Compartir contenido para validaciones.\n"
    )
    items = parse_historias(blob)
    by_key = {item.key: item for item in items}
    assert by_key["HN004"].superseded is True
    assert by_key["HN008"].updates == "HN004"
    assert by_key["HN005"].is_report is True
    assert by_key["HN006"].is_test_content is True


def test_epc_children_are_not_pseudo_hn_when_real_hn_present() -> None:
    blob = (
        "=== CHILD EPC-21813 (Epic) ===\nUY | OTT | Configurar add on\n"
        "=== CHILD EPC-21842 (Epic) ===\nFE|UY | OTT | Configurar add on\n"
        "HN001 Alta de oferta.\nHN002 Configuración.\n"
    )
    keys = [item.key for item in parse_historias(blob)]
    assert keys == ["HN001", "HN002"]


def test_whitelist_and_reports_generate_zero_product_cases() -> None:
    result = generate_operativa_candidates(
        release_name="OPE-TEST",
        epcs=[
            _epc(brf_key="BRF-17577", titulo="Habilitar IPs dentro del whitelist en UAT OPER"),
            _epc(brf_key="BRF-RPT", titulo="Reportes de la oferta comercial"),
        ],
        jira_loader=lambda _key: "",
    )
    assert result.candidates == []
    assert any("65.18" in note or "65.16" in note for note in result.skipped)


def test_offer_uses_qc_execution_matrix_not_ecosystem_as_device() -> None:
    result = generate_operativa_candidates(
        release_name="OPE-JULIO",
        epcs=[
            _epc(
                brf_key="BRF-17475",
                titulo="EC | OTT e IPTV | Realizar alta de la oferta comercial Type 1 Lionsgate",
            )
        ],
        jira_loader=lambda _key: "HN001 Alta de oferta. HN004 Medios de pago. HN005 Reportes.",
    )
    devices = {row.device for row in result.candidates}
    assert "OTT" not in devices
    assert "IPTV" not in devices
    assert "Pendiente de dispositivo (OTT)" not in devices
    assert "WEB" in devices
    assert "STB" in devices
    assert all(row.component == "BRF-17475" for row in result.candidates)
    assert {row.ecosystem for row in result.candidates} <= {"OTT", "IPTV"}
    assert any(row.behavior and "offer-available" in row.behavior for row in result.candidates)
    assert any(row.mdp for row in result.candidates)
    assert all(row.device_source for row in result.candidates)
    assert all(row.priority_reason for row in result.candidates)
    for row in result.candidates:
        assert row.device
        assert not row.name.endswith(row.device)
        assert f" · {row.device}" not in row.name
    assert all(row.applicability_reason for row in result.candidates)


def test_devices_come_from_brf_hn_content() -> None:
    result = generate_operativa_candidates(
        release_name="OPE",
        epcs=[
            _epc(
                brf_key="BRF-17475",
                titulo="EC | OTT e IPTV | Realizar alta de la oferta comercial Type 1 Lionsgate",
            )
        ],
        jira_loader=lambda _key: (
            "HN001 Alta de la oferta. Dispositivos: WEB, Android, iOS, Roku, Fire TV.\n"
            "HN004 Medios de pago y contratación."
        ),
    )
    available = [
        row for row in result.candidates if row.behavior and str(row.behavior).endswith("offer-available")
    ]
    assert {row.device for row in available} == {"WEB", "ADR", "iOS", "Roku", "Fire TV"}
    assert all(row.device_source for row in available)


def test_hn_devices_are_not_applied_to_other_hns() -> None:
    result = generate_operativa_candidates(
        release_name="OPE",
        epcs=[
            _epc(
                brf_key="BRF-17465",
                titulo="Alta del canal América TV Timeshift NPVR",
            )
        ],
        jira_loader=lambda _key: (
            "HN001 Alta del canal. Dispositivos: WEB, Android.\n"
            "HN010 Timeshift. Dispositivos: STB."
        ),
    )
    alta = {row.device for row in result.candidates if row.behavior and str(row.behavior).endswith("channel-alta")}
    timeshift = {row.device for row in result.candidates if row.behavior and str(row.behavior).endswith("channel-ts")}
    assert alta == {"WEB", "ADR"}
    assert timeshift == {"STB"}


def test_same_brf_two_epcs_are_flagged_not_deleted() -> None:
    result = generate_operativa_candidates(
        release_name="OPE",
        epcs=[
            _epc(
                brf_key="BRF-16018",
                epc_key="EPC-20875",
                titulo="OTT alta de oferta comercial con contratación",
                dispositivos_aplicables=["WEB"],
            ),
            _epc(
                brf_key="BRF-16018",
                epc_key="EPC-20553",
                titulo="OTT alta de oferta comercial con contratación",
                dispositivos_aplicables=["WEB"],
            ),
        ],
        jira_loader=lambda _key: "HN001 Alta. HN004 Medios de pago y contratación.",
    )
    assert {row.related_jira for row in result.candidates} == {"EPC-20875", "EPC-20553"}
    flagged = [row for row in result.candidates if row.duplicate_status != "UNIQUE"]
    assert flagged
    assert result.duplicate_groups >= 1
    assert all(row.duplicate_with for row in flagged)


def test_priority_follows_behavior_not_hardcoded_critical() -> None:
    result = generate_operativa_candidates(
        release_name="OPE",
        epcs=[
            _epc(
                brf_key="BRF-17475",
                titulo="OTT alta de oferta comercial con contratación",
                dispositivos_aplicables=["WEB"],
            )
        ],
        jira_loader=lambda _key: "HN001 Alta. HN004 Medios de pago y contratación.",
    )
    acquire = [row for row in result.candidates if row.behavior and str(row.behavior).endswith("offer-acquire")]
    available = [row for row in result.candidates if row.behavior and str(row.behavior).endswith("offer-available")]
    assert acquire
    assert available
    assert all(row.priority == "BLOCKER" for row in acquire)
    assert all(row.priority == "CRITICAL" for row in available)
    assert all(row.priority_reason for row in result.candidates)


def test_one_tc_per_declared_device() -> None:
    result = generate_operativa_candidates(
        release_name="OPE",
        epcs=[
            _epc(
                brf_key="BRF-17833",
                titulo="Actualizar nombre y logo del canal TCS+",
                dispositivos_aplicables=["WEB", "Android", "iOS"],
            )
        ],
        jira_loader=lambda _key: "",
    )
    identity = [row for row in result.candidates if row.behavior and str(row.behavior).endswith("identity")]
    assert {row.device for row in identity} == {"WEB", "ADR", "iOS"}
    assert len(identity) == 3


def test_timeshift_and_npvr_are_separate() -> None:
    result = generate_operativa_candidates(
        release_name="OPE",
        epcs=[
            _epc(
                brf_key="BRF-17465",
                titulo="Alta del canal América TV Timeshift NPVR TV Everywhere",
            )
        ],
        jira_loader=lambda _key: (
            "HN001 Alta del canal América TV.\n"
            "HN010 Timeshift.\n"
            "HN011 NPVR.\n"
        ),
    )
    keys = {row.behavior for row in result.candidates}
    assert any(key and key.endswith("channel-ts") for key in keys)
    assert any(key and key.endswith("channel-npvr") for key in keys)


def test_negative_america_tv_does_not_assert_availability() -> None:
    result = generate_operativa_candidates(
        release_name="OPE",
        epcs=[
            _epc(
                brf_key="BRF-17465",
                titulo="Alta del canal América TV Timeshift NPVR. No habilitar América TV.",
            )
        ],
        jira_loader=lambda _key: "HN010 No habilitar América TV en el release.",
    )
    keys = {row.behavior for row in result.candidates}
    assert any(key and key.endswith("negative") for key in keys)
    assert not any(key and key.endswith("channel-alta") for key in keys)
    assert not any(key and key.endswith("channel-play") for key in keys)
    joined = " ".join(
        (row.steps[0].expected_result if row.steps else "") + (row.steps[0].action if row.steps else "")
        for row in result.candidates
    ).lower()
    assert "no se encuentre publicado" in joined
    assert "esté disponible" not in joined
    assert "esta disponible" not in joined


def test_unsubscribed_user_is_not_combined_with_mdp() -> None:
    result = generate_operativa_candidates(
        release_name="OPE",
        epcs=[
            _epc(
                brf_key="BRF-17475",
                titulo="OTT alta de oferta comercial con contratación",
                dispositivos_aplicables=["WEB"],
            )
        ],
        jira_loader=lambda _key: "HN001 Alta. HN004 Medios de pago y contratación.",
    )
    transactional = [row for row in result.candidates if row.mdp]
    assert transactional
    assert all(row.user_type != "No suscrito" for row in transactional)


def test_julio_fixture_skips_whitelist_and_covers_selected_brfs() -> None:
    assert classify_family("Habilitar IPs whitelist UAT OPER") == FAMILY_INFRA
    assert classify_family("alta de la oferta comercial Type 1 Lionsgate") == FAMILY_OFFER
    pdf = JULIO.read_bytes()
    parsed = analyze_operativa_rn(pdf)
    epcs = [
        _epc(
            brf_key=row.brf_key,
            titulo=row.titulo,
            epc_key=row.epc_key,
            alcance=row.alcance,
            nota_rte=row.nota_rte,
            estado_jira=row.estado_jira,
        )
        for row in parsed
    ]
    result = generate_operativa_candidates(
        release_name="OPE-JULIO-2026-AND",
        epcs=epcs,
        pdf_bytes=pdf,
        jira_loader=lambda _key: "",
    )
    brfs = {row.related_functionality for row in result.candidates}
    assert "BRF-17577" not in brfs
    assert "BRF-17475" in brfs
    assert "BRF-17465" in brfs
    assert all(row.evidence for row in result.candidates)
    assert all(row.applied_rules for row in result.candidates)


def test_septiembre_fixture_does_not_copy_vpn_secrets() -> None:
    result = generate_operativa_candidates(
        release_name="OPE-SEPTIEMBRE-2026-GLB",
        epcs=[],
        pdf_bytes=GLB.read_bytes(),
        jira_loader=lambda _key: "",
    )
    joined = " ".join(
        (row.evidence or "") + (row.justification or "") + (row.test_data or "")
        for row in result.candidates
    ).lower()
    assert "password" not in joined
    assert "pre shared" not in joined


def test_enero_and_cenam_fixtures_run_without_cartesian() -> None:
    for path, name in ((ENERO, "OPE-ENERO"), (CENAM, "OPE-CENAM")):
        parsed = analyze_operativa_rn(path.read_bytes())
        epcs = [_epc(brf_key=row.brf_key, titulo=row.titulo, epc_key=row.epc_key) for row in parsed]
        result = generate_operativa_candidates(release_name=name, epcs=epcs, jira_loader=lambda _key: "")
        assert 0 < len(result.candidates) < 2500


AUP = Path(__file__).parent / "fixtures" / "PMOGH-OPE-AGOSTO-2026-AUP.pdf"
QC_GOLDEN_CANDIDATES = [
    Path("/golden/OPE-AGOSTO-2026-AUP_QC_Operativos(1).xlsx"),
    Path("/Users/rodriguezisr/Downloads/OPE-AGOSTO-2026-AUP_QC_Operativos(1).xlsx"),
]


def test_agosto_aup_architecture_component_ecosystem_device() -> None:
    parsed = analyze_operativa_rn(AUP.read_bytes())
    epcs = [
        _epc(
            brf_key=row.brf_key,
            titulo=row.titulo,
            epc_key=row.epc_key,
            alcance=row.alcance,
            nota_rte=row.nota_rte,
            estado_jira=row.estado_jira,
        )
        for row in parsed
        if row.qc_suggestion != "SUGERIDO_EXCLUIR"
    ]
    result = generate_operativa_candidates(
        release_name="OPE-AGOSTO-2026-AUP",
        epcs=epcs,
        pdf_bytes=AUP.read_bytes(),
        jira_loader=lambda _key: "",
    )
    assert result.candidates
    pending_labels = {
        "Pendiente de dispositivo (OTT)",
        "Pendiente de dispositivo (IPTV)",
        "OTT",
        "IPTV",
    }
    for row in result.candidates:
        assert row.component and (
            row.component.startswith("BRF-")
            or row.component.startswith("TRI-")
            or row.component.startswith("QCO-")
        )
        assert row.device not in pending_labels
        assert row.device
        assert row.ecosystem in {"OTT", "IPTV", None} or row.device == "PENDING"
        assert row.device_source


def test_behavior_recortes_matrix_when_hn_lists_devices() -> None:
    result = generate_operativa_candidates(
        release_name="OPE",
        epcs=[
            _epc(
                brf_key="BRF-DEMO",
                titulo="OTT add on con contratación",
            )
        ],
        jira_loader=lambda _key: (
            "HN001 Alta. Dispositivos: WEB, AAF, Android, iOS, tvOS, Windows, Consolas, Roku, Fire TV, Android TV para STV.\n"
            "HN002 Contratación checkout. Dispositivos: WEB, Android, iOS, AAF."
        ),
    )
    available = [
        row for row in result.candidates if row.behavior and str(row.behavior).endswith("offer-available")
    ]
    acquire = [
        row for row in result.candidates if row.behavior and str(row.behavior).endswith("offer-acquire")
    ]
    assert len(available) == 10
    assert {row.device for row in acquire} == {"WEB", "ADR", "iOS", "AAF"}


def test_qc_selected_in_develop_is_not_dropped_by_status() -> None:
    result = generate_operativa_candidates(
        release_name="OPE",
        epcs=[
            _epc(
                brf_key="BRF-17834",
                titulo="OTT alta de oferta comercial Type EST EXC 39 UNI",
                estado_jira="In Develop",
            )
        ],
        jira_loader=lambda _key: "HN001 Alta de la oferta Type EST EXC 39 UNI. Group ID: GID-39UNI.",
    )
    assert result.candidates
    assert all(row.related_functionality == "BRF-17834" for row in result.candidates)


def test_brf_17834_uses_hn_facts_not_generic_title_placeholder() -> None:
    blob = """
=== CHILD HN-17834-01 (Historia de negocio) ===
HN001 Alta de nueva oferta comercial Type EST EXC 39 UNI.
Group ID: GID-EST-EXC-39.
Precio por dispositivo: WEB USD 3.99, Android USD 3.99, iOS USD 4.99.
Modalidad compra y renta. Trailer habilitado. Descarga en OTT. HO según paquete.
Medios de pago: Visa.
Canal / Punto de interacción: Plan Selector, Landing Comercial, vCard, Home, Checkout.
"""
    result = generate_operativa_candidates(
        release_name="OPE-AGOSTO",
        epcs=[_epc(brf_key="BRF-17834", titulo="Realizar alta de nueva oferta comercial Type EST EXC 39 UNI")],
        jira_loader=lambda _key: blob,
    )
    joined_steps = " ".join(
        step.action + " " + step.expected_result
        for row in result.candidates
        for step in row.steps
    )
    assert "El usuario recorre el comportamiento funcional descrito en el BRF." not in joined_steps
    assert "Se observa el resultado de negocio vigente." not in joined_steps
    assert any(row.group_id == "GID-EST-EXC-39" for row in result.candidates)
    assert any("Plan Selector" in (row.test_data or "") or "Plan Selector" in joined_steps for row in result.candidates)
    assert any("trailer" in step.action.lower() for row in result.candidates for step in row.steps)
    assert any(row.behavior and str(row.behavior).endswith("offer-acquire") for row in result.candidates)
    assert all(row.hn_source == "HN_PRESENT" for row in result.candidates)
    assert all(row.hn_keys for row in result.candidates)


def test_brf_17844_nine_channels_are_one_alta_behavior() -> None:
    blob = """
HN001 Alta de 9 canales.
Canal 1 - Noticias Uno
Canal 2 - Noticias Dos
Canal 3 - Deportes
Canal 4 - Cine
Canal 5 - Infantil
Canal 6 - Música
Canal 7 - Documentales
Canal 8 - Series
Canal 9 - Local
Número, nombre, logo, EPG Full, EPG Mini, Player Live, Panel de Opciones, Mosaico, Buscador, suscripción.
"""
    result = generate_operativa_candidates(
        release_name="OPE",
        epcs=[
            _epc(
                brf_key="BRF-17844",
                titulo="Alta de 9 canales con nombre y logo",
                dispositivos_aplicables=["WEB", "Android"],
            )
        ],
        jira_loader=lambda _key: blob,
    )
    alta = [row for row in result.candidates if row.behavior and str(row.behavior).endswith("channel-alta")]
    assert {row.device for row in alta} == {"WEB", "ADR"}
    assert len(alta) == 2
    expected = alta[0].steps[0].expected_result.lower()
    assert "canales" in expected
    assert any(token in expected for token in ("noticias uno", "canal 1", "9"))


def test_missing_hn_is_marked_not_invented() -> None:
    result = generate_operativa_candidates(
        release_name="OPE",
        epcs=[_epc(brf_key="BRF-99999", titulo="Ajuste menor de copy en landing")],
        jira_loader=lambda _key: "",
    )
    assert result.candidates
    assert all(row.hn_source == "HN_ABSENT" for row in result.candidates)
    assert all(not row.hn_keys for row in result.candidates)
    assert all(row.group_id is None for row in result.candidates)
    assert all(row.confidence == "low" for row in result.candidates)
    joined = " ".join(row.steps[0].action for row in result.candidates)
    assert "El usuario recorre el comportamiento funcional descrito en el BRF." not in joined


def test_search_casing_is_not_auto_generated() -> None:
    result = generate_operativa_candidates(
        release_name="OPE",
        epcs=[
            _epc(
                brf_key="BRF-17844",
                titulo="Alta de canal con buscador",
                dispositivos_aplicables=["WEB"],
            )
        ],
        jira_loader=lambda _key: "HN001 Alta del canal. El usuario busca el canal en el buscador.",
    )
    text = " ".join(step.action.lower() for row in result.candidates for step in row.steps)
    assert "mayúsculas" not in text
    assert "minúsculas" not in text
    assert "casing" not in text


def test_jira_child_without_hn_code_is_still_a_source() -> None:
    blob = """
=== CHILD EPC-CHILD-1 (Historia de negocio) ===
Configurar oferta Type EST con Group ID: GID-CHILD.
Plan Selector y Checkout.
"""
    items = parse_historias(blob)
    assert any(item.key == "EPC-CHILD-1" for item in items)
    result = generate_operativa_candidates(
        release_name="OPE",
        epcs=[_epc(brf_key="BRF-17834", titulo="Alta de la oferta comercial Type EST")],
        jira_loader=lambda _key: blob,
    )
    assert any(row.group_id == "GID-CHILD" for row in result.candidates)
    assert any("EPC-CHILD-1" in row.hn_keys for row in result.candidates)
