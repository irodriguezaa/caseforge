"""HN classification is independent of offer templates and of specific BRF keys."""

from app.models.epc import Epc, QcSuggestion
from app.services.operativa_engine.coverage_matrix import build_coverage_matrix
from app.services.operativa_engine.hn import parse_historias
from app.services.operativa_engine.hn_roles import classify_historias
from app.services.operativa_engine.jira_context import BrfContextBundle

OFFER_BLOB = """
HN001 Alta del Type EST EXC 49 UNI
Criterios de aceptación: el Type queda disponible para el usuario.

HN002 Valores de configuración
Compra = Sí
Renta = No
Descarga = Sí
Preview/Trailer = Sí
Modelo de negocio: EST
Especificación: EXC 49 UNI

HN003 Medios de pago
Criterios de aceptación: el usuario puede completar la transacción con los medios habilitados.

HN004 Comunicación
Criterios de aceptación: se envía la comunicación de alta.

HN005 Reportes mensuales de consumo
Criterios de aceptación: el área de BI recibe el reporte.

HN006 Compartir contenido para validaciones
ID program: 179137434
Título: Prueba Type EST EXC 49
Supplier: Warner
Región: MEX
Hasta: 31-Aug-26
ID group: 1490053
"""


def _epc(**overrides: object) -> Epc:
    data = dict(
        id=1,
        operativa_release_id=1,
        release_id=10,
        brf_key="BRF-99001",
        epc_key="EPC-99001",
        titulo="OTT | Configurar Type EST EXC 49 UNI",
        alcance="Total",
        nota_rte=None,
        estado_jira="In Validate",
        qc_suggestion=QcSuggestion.SUGERIDO_INCLUIR,
        include_in_qc=True,
        alcance_funcional=None,
        dispositivos_aplicables=["WEB", "Android", "iOS"],
    )
    data.update(overrides)
    return Epc(**data)  # type: ignore[arg-type]


def test_classify_offer_hns_without_dropping_any() -> None:
    classified = classify_historias(parse_historias(OFFER_BLOB))
    assert set(classified) == {"HN001", "HN002", "HN003", "HN004", "HN005", "HN006"}
    assert classified["HN001"].disposition == "PRIMARY_BEHAVIOR"
    assert classified["HN002"].disposition == "SUPPORTING"
    assert classified["HN002"].related_to == "HN001"
    assert classified["HN003"].disposition == "PRIMARY_BEHAVIOR"
    assert classified["HN004"].disposition == "PRIMARY_BEHAVIOR"
    assert classified["HN005"].disposition == "OOS_QC"
    assert classified["HN006"].disposition == "TEST_DATA"
    assert classified["HN006"].related_to == "HN001"


def test_matrix_merges_supporting_and_test_data_into_primary() -> None:
    result = build_coverage_matrix(
        release_id=10,
        release_name="OPE-generic",
        epcs=[_epc()],
        context_loader=lambda _key: BrfContextBundle(brf_key="BRF-99001", jira_blob=OFFER_BLOB),
    )
    titles = [row.behavior_title.lower() for row in result.rows]
    assert not any("valores de configuración" in title or "valores de configuracion" in title for title in titles)
    assert not any("reportes" in title for title in titles)
    assert not any("compartir contenido" in title for title in titles)

    alta = next(row for row in result.rows if "HN001" in row.hn_keys and "HN002" in row.hn_keys)
    assert "HN006" in alta.hn_keys
    blob = (alta.test_data or "") + "\n" + (alta.evidence or "")
    assert "Group ID: 1490053" in blob
    assert "ID program" not in (alta.test_data or "")
    assert "179137434" not in (alta.test_data or "")
    assert "Compra: Sí" in blob
    assert "Renta: No" in blob

    by_hn = {item.hn_key: item for item in result.hn_coverage}
    assert by_hn["HN002"].disposition == "SUPPORTING"
    assert by_hn["HN005"].disposition == "OOS_QC"
    assert by_hn["HN006"].disposition == "TEST_DATA"
    assert len(result.rows) >= 3


ALTA_COM_BLOB = """
ID
HN001 - Realizar alta del Type EST 1J
Historia de negocio
Yo como negocio de Claro Paraguay
Quiero realizar el alta de la oferta comercial Type EST 1J
Criterios de aceptación
El Type EST 1J debe permitir la reproducción del tráiler.

ID
HN002 - Implementar comunicación
Historia de negocio
Quiero implementar la comunicación de la oferta comercial
Criterios de aceptación
Se debe implementar la comunicación correspondiente.

ID
HN003 - Mostrar en reportes mensuales
Historia de negocio
Quiero mostrar la información transaccional
Criterios de aceptación
Se debe mostrar el precio con IVA en los reportes.

ID
HN004 - Compartir contenido para validaciones
Historia de negocio
Quiero compartir la información del contenido al equipo de pruebas
Criterios de aceptación
ID program: 179343910
ID group: 1494783
"""


def test_alta_and_comunicacion_without_forcing_mdp_template() -> None:
    classified = classify_historias(parse_historias(ALTA_COM_BLOB))
    assert classified["HN001"].disposition == "PRIMARY_BEHAVIOR"
    assert classified["HN002"].disposition == "PRIMARY_BEHAVIOR"
    assert classified["HN003"].disposition == "OOS_QC"
    assert classified["HN004"].disposition == "TEST_DATA"
    result = build_coverage_matrix(
        release_id=10,
        release_name="OPE-generic",
        epcs=[_epc(brf_key="BRF-99002", epc_key="EPC-99002", titulo="OTT | Realizar el alta de la oferta")],
        context_loader=lambda _key: BrfContextBundle(brf_key="BRF-99002", jira_blob=ALTA_COM_BLOB),
    )
    titles = " ".join(row.behavior_title.lower() for row in result.rows)
    assert "alta" in titles
    assert "comunicaci" in titles
    assert "medios de pago" not in titles
    assert "reportes" not in titles
    alta = next(row for row in result.rows if "HN001" in row.hn_keys)
    assert "Group ID: 1494783" in (alta.test_data or "")
    assert "ID program" not in (alta.test_data or "")
    assert "179343910" not in (alta.test_data or "")


def test_tester_test_data_uses_group_id_not_id_program() -> None:
    from app.schemas.matrix_preview import PreviewTestCase
    from app.services.operativa_engine.hn_roles import extract_supporting_facts
    from app.services.operativa_engine.matrix_steps import build_tester_test_data

    blob = """
    ID program: 179343910
    Título: Prueba Type EST 1J MX y Latam
    Supplier: Paramount
    ID group: 1494783
    """
    facts = extract_supporting_facts(blob)
    assert "Group ID: 1494783" in facts
    assert not any("program" in line.lower() for line in facts)
    preview = PreviewTestCase(
        brf_key="BRF-99010",
        hn_keys=["HN001", "HN004"],
        behavior_key="alta",
        behavior_title="Realizar alta del Type EST",
        evidence="Extracto con ID program: 179343910 e ID group: 1494783",
        expansion_reason="device",
        device="Windows/XBOX",
        test_data="\n".join(["BRF: BRF-99010", "HN: HN001, HN004", *facts, "ID program: 179343910"]),
    )
    tester = build_tester_test_data(preview)
    assert "Group ID: 1494783" in tester
    assert "ID program" not in tester
    assert "179343910" not in tester

