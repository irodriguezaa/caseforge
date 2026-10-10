"""FASE 6B LLM path without network: recorded JSON is validated."""

from app.schemas.case_generation import CoverageUnit
from app.services.case_composer import validate_composed_candidates
from app.schemas.case_generation import CandidateStep, GeneratedCaseCandidate


def test_mock_llm_payload_is_repaired_and_covers_units() -> None:
    unit = CoverageUnit(
        coverage_id="COV-001",
        role="G",
        behavior="se muestra el resultado",
        scenario="se muestra el resultado",
        evidence="e",
        body="When el usuario selecciona Continuar\nThen se muestra el resultado",
        user_action="el usuario selecciona Continuar",
        observable_then=["se muestra el resultado"],
        story_key="ST-1",
        artifact_key="EPC-1",
        applicability="ejecutable",
    )
    llm = GeneratedCaseCandidate(
        name="Validar resultado",
        description="x",
        evidence="e",
        justification="j",
        related_jira="ST-1",
        related_functionality="EPC-1",
        covers=["COV-001"],
        steps=[
            CandidateStep(
                step_number=1,
                action="El usuario ingresa al flujo correspondiente",
                expected_result="otra cosa",
                covered_unit_ids=["COV-001"],
            )
        ],
        generation_origin="llm",
    )
    out = validate_composed_candidates([llm], [unit], fill_missing=lambda m: [])
    assert out
    assert "Validar" not in out[0].name
    assert "Seleccionar" in out[0].steps[0].action
    assert "resultado" in (out[0].steps[0].expected_result or "").lower()
