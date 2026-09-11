"""Generic matrix practices must apply to BRFs that were never in the diagnostic lote."""

from app.models.epc import Epc, QcSuggestion
from app.services.operativa_engine import generate_operativa_from_matrix
from app.services.operativa_engine.jira_context import BrfContextBundle
from app.services.operativa_engine.matrix_expand import expand_matrix_preview
from app.services.operativa_engine.coverage_matrix import build_coverage_matrix


def _epc(brf_key: str, titulo: str, devices: list[str] | None = None) -> Epc:
    return Epc(
        id=99,
        operativa_release_id=1,
        release_id=88,
        brf_key=brf_key,
        epc_key="EPC-99901",
        titulo=titulo,
        alcance="Total",
        nota_rte=None,
        estado_jira="In Validate",
        qc_suggestion=QcSuggestion.SUGERIDO_INCLUIR,
        include_in_qc=True,
        alcance_funcional=None,
        dispositivos_aplicables=devices
        or ["WEB", "AAF", "Android", "iOS", "tvOS", "Windows/XBOX", "Consolas", "Roku", "Fire TV", "Android TV para STV"],
    )


def _bundle(key: str, blob: str) -> BrfContextBundle:
    return BrfContextBundle(brf_key=key, jira_blob=blob)


def test_unseen_brf_applies_email_logo_and_device_expansion() -> None:
    brf = "BRF-99999"
    blob = (
        "HN001 Iniciar el flujo de contratación.\n"
        "Criterios de aceptación: iniciar contratación en plan selector.\n"
        "HN002 Implementar el logotipo del canal Alfa.\n"
        "Criterios de aceptación: visualizar el logo en el correo de confirmación.\n"
        "HN003 Implementar el logotipo del canal Beta.\n"
        "Criterios de aceptación: visualizar el logo en el correo de confirmación.\n"
        "HN004 Mantener impacto en landing, home y mi cuenta.\n"
        "Criterios de aceptación: no se parte el impacto en TCs por canal / punto de interacción.\n"
    )
    result = generate_operativa_from_matrix(
        release_id=88,
        release_name="OPE-nuevo",
        epcs=[_epc(brf, "OTT | Nuevo add-on nunca visto")],
        context_loader=lambda key: _bundle(key, blob),
    )
    hire = [case for case in result.candidates if "contrat" in (case.name or "").lower()]
    logo = [case for case in result.candidates if "logotipo" in (case.name or "").lower()]
    mantener = [case for case in result.candidates if "mantener" in (case.name or "").lower()]
    assert len(hire) == 10
    assert len({case.device for case in hire}) == 10
    assert len(logo) == 1
    assert logo[0].device is None
    assert "Canal: Email" in (logo[0].test_data or "") or logo[0].device_source and "Email" in (logo[0].device_source or "")
    assert len(mantener) <= 1
    assert all(case.related_functionality == brf for case in result.candidates)
    matrix = build_coverage_matrix(
        release_id=88,
        release_name="OPE-nuevo",
        epcs=[_epc(brf, "OTT | Nuevo add-on nunca visto")],
        context_loader=lambda key: _bundle(key, blob),
    )
    assert {item.hn_key for item in matrix.hn_coverage} == {"HN001", "HN002", "HN003", "HN004"}
    hn004 = next(item for item in matrix.hn_coverage if item.hn_key == "HN004")
    assert hn004.disposition == "SCENARIO"
    assert hn004.status == "ABSORBED"
    assert hn004.related_hn


def test_unseen_brf_qc_review_and_oos_do_not_expand() -> None:
    brf = "BRF-88888"
    blob = "texto de infraestructura whitelist UAT sin historias de usuario"
    matrix = build_coverage_matrix(
        release_id=88,
        release_name="OPE-nuevo",
        epcs=[_epc(brf, "Habilitar IPs dentro del whitelist en UAT OPER")],
        context_loader=lambda key: _bundle(key, blob),
    )
    preview = expand_matrix_preview(matrix)
    assert preview.preview_tc_count == 0
    result = generate_operativa_from_matrix(
        release_id=88,
        release_name="OPE-nuevo",
        epcs=[_epc(brf, "Habilitar IPs dentro del whitelist en UAT OPER")],
        context_loader=lambda key: _bundle(key, blob),
    )
    assert result.candidates == []
