"""FASE 6D: granularity, unique titles, NA per epic. Synthetic Gherkin only."""

from app.schemas.case_generation import CandidateStep, CoverageUnit, GeneratedCaseCandidate
from app.services.case_composer import (
    candidate_violates_writing_standard,
    compose_inventory,
    compose_story_units,
    phrases_similar,
    validate_composed_candidates,
)
from app.services.gherkin_coverage import build_coverage_inventory, candidates_from_jira_artifacts
from app.services.qc_candidate_rules import apply_qc_rules, merge_candidates


def _artifacts(*stories: tuple[str, str, str]) -> list[dict]:
    by_epic: dict[str, list[dict]] = {}
    for epic, story, description in stories:
        by_epic.setdefault(epic, []).append(
            {
                "key": story,
                "issuetype": "Technical Story",
                "summary": "Feature flujo",
                "description": description,
                "acceptance_criteria": "",
            }
        )
    return [
        {
            "key": epic,
            "issuetype": "Technical Epic",
            "children": children,
        }
        for epic, children in by_epic.items()
    ]


def test_d2_same_given_when_folds_distinct_then() -> None:
    description = """
Scenario: Resultado A
  Given el usuario está en el flujo
  When el usuario selecciona Continuar
  Then se muestra el resultado A
Scenario: Resultado B
  Given el usuario está en el flujo
  When el usuario selecciona Continuar
  Then se muestra el resultado B
"""
    cases = candidates_from_jira_artifacts(_artifacts(("EPC-1", "ST-1", description)), "rn.pdf", [], lambda *_a: None)
    exe = [row for row in cases if row.applicability != "na_ambiente"]
    assert len(exe) == 1
    assert len(exe[0].steps) == 1
    joined = exe[0].steps[0].expected_result.lower()
    assert "resultado a" in joined
    assert "resultado b" in joined


def test_d2_location_given_chains_to_previous_then() -> None:
    description = """
Scenario: Abre opciones
  When el usuario abre el menú de opciones
  Then se muestra la pantalla de opciones
Scenario: Confirma
  Given el usuario está en la pantalla de opciones
  When el usuario selecciona Confirmar
  Then se muestra el comprobante
"""
    cases = candidates_from_jira_artifacts(_artifacts(("EPC-1", "ST-1", description)), "rn.pdf", [], lambda *_a: None)
    longest = max(cases, key=lambda row: len(row.steps))
    assert len(longest.steps) >= 2


def test_d2_phrases_similar_location_variants() -> None:
    assert phrases_similar("se muestra la pantalla de opciones", "el usuario está en la pantalla de opciones")


def test_d3_identical_steps_same_story_merge() -> None:
    a = CoverageUnit(
        coverage_id="COV-1",
        role="G",
        behavior="ok",
        scenario="ok",
        evidence="e",
        body="When el usuario abre el panel\nThen se muestra el panel",
        user_action="el usuario abre el panel",
        observable_then=["se muestra el panel"],
        story_key="ST-1",
        artifact_key="EPC-1",
    )
    b = CoverageUnit(
        coverage_id="COV-2",
        role="G",
        behavior="ok",
        scenario="ok",
        evidence="e",
        body="When el usuario abre el panel\nThen se muestra el panel",
        user_action="el usuario abre el panel",
        observable_then=["se muestra el panel"],
        story_key="ST-1",
        artifact_key="EPC-1",
    )
    out = compose_inventory([a, b], [], lambda *_a: None)
    exe = [row for row in out if row.applicability != "na_ambiente"]
    assert len(exe) == 1
    assert set(exe[0].covers) == {"COV-1", "COV-2"}


def test_d3_distinct_intents_get_distinct_titles() -> None:
    description = """
Scenario: Guardar
  When el usuario selecciona Guardar
  Then se muestra la confirmación
Scenario: Descartar
  When el usuario selecciona Descartar
  Then se muestra la confirmación
"""
    cases = candidates_from_jira_artifacts(_artifacts(("EPC-1", "ST-1", description)), "rn.pdf", [], lambda *_a: None)
    names = [_norm_name(row.name) for row in cases]
    assert len(names) == len(set(names))


def _norm_name(name: str) -> str:
    import re

    return re.sub(r"\W+", " ", (name or "").lower()).strip()


def test_d4_two_epics_same_remote_config_are_separate_na() -> None:
    scenario = """
Scenario: Sin configuración remota
  Given la configuración remota no se logra obtener
  When el usuario abre el flujo
  Then se muestra el estado vacío en pantalla
"""
    cases = candidates_from_jira_artifacts(
        _artifacts(("EPC-A", "ST-A", scenario), ("EPC-B", "ST-B", scenario)),
        "rn.pdf",
        [],
        lambda *_a: None,
    )
    na = [row for row in cases if row.applicability == "na_ambiente"]
    exe = [row for row in cases if row.applicability == "ejecutable"]
    epics = {(row.related_functionality or "").split("|")[0].strip() for row in na}
    assert len(na) >= 2
    assert "EPC-A" in epics
    assert "EPC-B" in epics
    assert not exe
    assert not any(
        "EPC-A" in (row.related_functionality or "") and "EPC-B" in (row.related_functionality or "")
        for row in cases
    )


def test_d4_merge_candidates_never_joins_epics() -> None:
    def _cand(epic: str) -> GeneratedCaseCandidate:
        return GeneratedCaseCandidate(
            name="Mismo flujo",
            description="x",
            evidence="e",
            justification="j",
            related_functionality=epic,
            related_jira="ST-1" if epic == "EPC-A" else "ST-2",
            steps=[CandidateStep(step_number=1, action="Abrir panel", expected_result="se muestra el panel")],
            covers=[f"COV-{epic}"],
            applicability="na_ambiente",
            applicability_reason="na_ambiente:remoto",
            generation_origin="composed-flow",
        )

    merged = apply_qc_rules([_cand("EPC-A"), _cand("EPC-B")])
    epics = {(row.related_functionality or "").split("|")[0].strip() for row in merged}
    assert epics == {"EPC-A", "EPC-B"}
    joined = merge_candidates([_cand("EPC-A"), _cand("EPC-B")])
    assert (joined.related_functionality or "").split("|")[0].strip() == "EPC-A"
    assert "EPC-B" not in (joined.related_functionality or "")
    assert joined.applicability == "na_ambiente"


def test_d4b_given_without_when_is_not_a_case() -> None:
    description = """
Scenario: Estado en home
  Given el usuario está en la home
  Then se muestra el banner
Scenario: Abre detalle
  When el usuario abre el detalle
  Then se muestra el detalle
"""
    cases = candidates_from_jira_artifacts(_artifacts(("EPC-1", "ST-1", description)), "rn.pdf", [], lambda *_a: None)
    exe = [row for row in cases if row.applicability != "na_ambiente"]
    assert exe
    assert all(any(step.action for step in row.steps) for row in exe)
    actions = " ".join(step.action.lower() for row in exe for step in row.steps)
    assert "está en la home" not in actions
    assert "se encuentra" not in actions


def test_d4c_quoted_template_is_not_an_action() -> None:
    description = """
Scenario: Detalle
  When el usuario abre el detalle
  Then se muestra "@variable"
"""
    cases = candidates_from_jira_artifacts(_artifacts(("EPC-1", "ST-1", description)), "rn.pdf", [], lambda *_a: None)
    actions = " ".join(step.action for row in cases for step in row.steps)
    assert 'Abrir "@variable"' not in actions
    assert not any("@variable" in (step.action or "") for row in cases for step in row.steps)


def test_d4c_invalid_valid_only_with_input() -> None:
    description = """
Scenario: Abrir panel
  When el usuario abre el panel
  Then se muestra el error; se muestra el panel
"""
    drafts = compose_story_units(
        [
            CoverageUnit(
                coverage_id="COV-1",
                role="G",
                behavior="panel",
                scenario="Abrir panel",
                evidence="e",
                body="When el usuario abre el panel\nThen se muestra el error; se muestra el panel",
                user_action="el usuario abre el panel",
                observable_then=["se muestra el error", "se muestra el panel"],
                story_key="ST-1",
                artifact_key="EPC-1",
            )
        ]
    )
    actions = " ".join(step.action.lower() for draft in drafts for step in draft.steps)
    assert "dato inválido" not in actions


def test_d4c_prose_objetivo_does_not_create_units() -> None:
    units = build_coverage_inventory(
        _artifacts(
            (
                "EPC-1",
                "ST-1",
                """
Objetivo: entregar la experiencia en pantalla.
Alcance: criterios de compilación y cobertura unitaria.
h3. Notas
_texto técnico_
{code:gherkin}
Scenario leftover
{code}
""",
            )
        ),
        "rn.pdf",
    )
    titles = " ".join(unit.scenario for unit in units).lower()
    assert "objetivo" not in titles
    assert "alcance" not in titles
    assert "texto técnico" not in titles


def test_d5_llm_filler_and_duplicate_title_are_rejected() -> None:
    unit = CoverageUnit(
        coverage_id="COV-1",
        role="G",
        behavior="resultado",
        scenario="resultado",
        evidence="e",
        body='When el usuario selecciona "Continuar"\nThen se muestra "Listo"',
        user_action='el usuario selecciona "Continuar"',
        observable_then=['se muestra "Listo"'],
        story_key="ST-1",
        artifact_key="EPC-1",
    )
    filler = GeneratedCaseCandidate(
        name="Continuar",
        description="x",
        evidence="e",
        justification="j",
        related_jira="ST-1",
        related_functionality="EPC-1",
        covers=["COV-1"],
        steps=[
            CandidateStep(
                step_number=1,
                action='Seleccionar "Continuar"',
                expected_result='se muestra "Listo"',
                covered_unit_ids=["COV-1"],
            ),
            CandidateStep(
                step_number=2,
                action="Observar el resultado",
                expected_result='se muestra "Listo"',
                covered_unit_ids=["COV-1"],
            ),
        ],
        generation_origin="llm",
    )
    assert candidate_violates_writing_standard(filler, inventory_by_id={"COV-1": unit})
    missing_quote = GeneratedCaseCandidate(
        name="Continuar",
        description="x",
        evidence="e",
        justification="j",
        related_jira="ST-1",
        related_functionality="EPC-1",
        covers=["COV-1"],
        steps=[
            CandidateStep(
                step_number=1,
                action="Seleccionar siguiente",
                expected_result="se muestra el ok",
                covered_unit_ids=["COV-1"],
            )
        ],
        generation_origin="llm",
    )
    assert candidate_violates_writing_standard(missing_quote, inventory_by_id={"COV-1": unit})
    filled: list = []

    def _fill(missing):
        filled.extend(missing)
        return compose_inventory(missing, [], lambda *_a: None)

    out = validate_composed_candidates([filler], [unit], fill_missing=_fill)
    assert filled
    assert all(row.generation_origin != "llm" or not candidate_violates_writing_standard(row) for row in out)
