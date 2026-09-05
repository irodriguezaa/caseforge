"""Official lote: frozen matrix + expander, no HN re-analysis."""

from pathlib import Path

from app.schemas.coverage_matrix import CoverageMatrixResponse
from app.services.operativa_engine.matrix_expand import expand_matrix_preview
from app.services.operativa_engine.matrix_official import (
    load_approved_matrix,
    materialize_official_candidates,
    matrix_row_from_export,
)


def test_official_count_matches_preview() -> None:
    source = Path("/Users/rodriguezisr/Documents/caseforge/exports/CaseForge_Operativas_matriz_diagnostica_10BRF.json")
    if not source.exists():
        source = Path(__file__).resolve().parents[2] / "exports" / "CaseForge_Operativas_matriz_diagnostica_10BRF.json"
    if not source.exists():
        return
    matrix = load_approved_matrix(source, release_id=1, release_name="OPE")
    preview = expand_matrix_preview(matrix)
    candidates, warnings = materialize_official_candidates(matrix)
    assert warnings == []
    assert len(candidates) == preview.preview_tc_count
    assert all(case.steps for case in candidates)
    assert all(case.related_functionality for case in candidates)


def test_materialize_keeps_prices_from_matrix() -> None:
    row = matrix_row_from_export(
        {
            "BRF": "BRF-16018",
            "EPCs": "EPC-1",
            "HN/CA": "HN001",
            "behavior": "Integrar add on Crunchyroll",
            "interaction_points": "",
            "channel": "",
            "ecosystem": "OTT",
            "applicable_devices": "WEB",
            "relevant_users": "",
            "transactional": False,
            "MDP": "",
            "test_data": "Valores declarados: $ 246.00; $ 189.23",
            "origin": "directo",
            "scope_status": "IN_SCOPE",
            "reasoning": "precio de fuente",
            "duplicate_risk": "UNIQUE",
            "evidence": (
                "Comportamiento: BRF-16018:HN001:integrar\nExtracto: Precio con IVA: RD$ 246.00\n"
                "Criterios de aceptación\nPrecio con IVA: RD$ 246.00"
            ),
        }
    )
    candidates, _ = materialize_official_candidates(
        CoverageMatrixResponse(
            status="MATRIX", engine="t", release_id=1, release_name="t", rows=[row], row_count=1
        )
    )
    assert len(candidates) == 1
    blob = (candidates[0].test_data or "") + candidates[0].steps[-1].expected_result
    assert "246.00" in blob
    assert candidates[0].device == "WEB"
    assert candidates[0].hn_keys == ["HN001"]
    joined = " ".join(step.action for step in candidates[0].steps)
    assert "BRF" not in joined
    assert "HN001" not in joined


def test_materialize_email_is_channel_not_device() -> None:
    row = matrix_row_from_export(
        {
            "BRF": "BRF-17442",
            "EPCs": "EPC-1",
            "HN/CA": "HN014",
            "behavior": "Implementar el logo en correo de bienvenida",
            "surfaces": "Correo de bienvenida",
            "channel": "Email",
            "ecosystem": "",
            "applicable_devices": "",
            "relevant_users": "Registrado (tras alta)",
            "transactional": False,
            "MDP": "",
            "test_data": "Canal: Email",
            "origin": "directo",
            "scope_status": "IN_SCOPE",
            "reasoning": "email",
            "duplicate_risk": "UNIQUE",
            "evidence": "Comportamiento: BRF-17442:HN014:logo\nExtracto: logo en correo\nCriterios de aceptación\nvisualizar el logo",
        }
    )
    candidates, _ = materialize_official_candidates(
        CoverageMatrixResponse(
            status="MATRIX", engine="t", release_id=1, release_name="t", rows=[row], row_count=1
        )
    )
    assert len(candidates) == 1
    assert candidates[0].device is None
    assert "Email" in candidates[0].name
    joined = " ".join(step.action for step in candidates[0].steps)
    assert "BRF" not in joined
    assert "correo" in joined.lower() or "logo" in joined.lower()


def test_qc_review_not_materialized() -> None:
    row = matrix_row_from_export(
        {
            "BRF": "BRF-16018",
            "EPCs": "EPC-1",
            "HN/CA": "HN025",
            "behavior": "No liberar a producción el add on Crunchyroll",
            "interaction_points": "",
            "channel": "",
            "ecosystem": "OTT",
            "applicable_devices": "WEB",
            "origin": "QC_REVIEW",
            "scope_status": "IN_SCOPE",
            "test_data": "",
            "MDP": "",
            "relevant_users": "",
            "transactional": False,
            "reasoning": "contradicción",
            "duplicate_risk": "OVERLAP",
            "evidence": "Comportamiento: BRF-16018:HN025:no-liberar\nExtracto: NO se debe liberar",
        }
    )
    candidates, _ = materialize_official_candidates(
        CoverageMatrixResponse(
            status="MATRIX", engine="t", release_id=1, release_name="t", rows=[row], row_count=1
        )
    )
    assert candidates == []


def test_materialize_numbered_negative_checks_are_executable() -> None:
    row = matrix_row_from_export(
        {
            "BRF": "BRF-88881",
            "EPCs": "EPC-1",
            "HN/CA": "HN001",
            "behavior": "Realizar baja del canal CanalDemo",
            "interaction_points": "Mosaico; Buscador",
            "channel": "",
            "ecosystem": "OTT",
            "applicable_devices": "WEB",
            "origin": "directo",
            "scope_status": "IN_SCOPE",
            "test_data": "",
            "MDP": "",
            "relevant_users": "",
            "transactional": False,
            "reasoning": "baja",
            "duplicate_risk": "UNIQUE",
            "evidence": (
                "Comportamiento: BRF-88881:HN001:baja\n"
                "Extracto: HN001 Realizar baja del canal CanalDemo (42) de la grilla de programación\n"
                "Criterios de aceptación\n"
                "- El Salvador\n"
                "- Guatemala\n"
                "1. El canal NO debe ser mostrado en la grilla de programación ni en el mosaico de canales.\n"
                "2. El canal NO debe ser mostrado como resultado de búsquedas en el Buscador.\n"
                "3. El canal NO debe ser mostrado en el carrusel de canales de TV en vivo.\n"
                "4. El canal NO debe ser mostrado en ningún carrusel de categoría.\n"
                "5. La frecuencia 42 correspondiente a CanalDemo no debe estar presente en Claro video.\n"
            ),
        }
    )
    candidates, warnings = materialize_official_candidates(
        CoverageMatrixResponse(
            status="MATRIX", engine="t", release_id=1, release_name="t", rows=[row], row_count=1
        )
    )
    assert warnings == []
    assert len(candidates) == 2
    countries = {case.country for case in candidates}
    assert countries == {"El Salvador", "Guatemala"}
    assert all(case.device == "WEB" for case in candidates)
    salvador = next(case for case in candidates if case.country == "El Salvador")
    actions = [step.action.lower() for step in salvador.steps]
    expecteds = [step.expected_result.lower() for step in salvador.steps]
    blob = " ".join(actions)
    assert "brf" not in blob
    assert "abrir" not in blob
    assert "hn001" not in blob
    assert "epc" not in blob
    assert "grilla" in blob
    assert "mosaico" in blob
    assert "buscador" in blob
    assert "cada país" not in blob
    assert any("no se muestra" in item or "no aparece" in item or "no está presente" in item for item in expecteds)
    assert (salvador.test_data or "").count("El Salvador") >= 1
    assert "Guatemala" not in (salvador.test_data or "")
    assert "42" in (salvador.test_data or "")
    assert "canaldemo (42)" in " ".join(expecteds)
    assert salvador.steps[0].action.startswith("Consultar") or "grilla" in salvador.steps[0].action.lower()
