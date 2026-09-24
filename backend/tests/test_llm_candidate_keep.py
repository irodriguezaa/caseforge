"""LLM candidate keep/resolve and coverage-fill interaction."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.schemas.case_generation import CandidateStep, CoverageUnit, GeneratedCaseCandidate
from app.services.ai_case_engine import (
    _keep_llm_functionality_candidates,
    generate_release_app_candidates,
)
from app.services.qc_candidate_rules import apply_qc_rules


def _unit(cid: str, scenario: str, story: str = "STORY-1", epic: str = "EPIC-1") -> CoverageUnit:
    return CoverageUnit(
        coverage_id=cid,
        role="A",
        behavior=scenario,
        scenario=scenario,
        evidence=f"{story}: {scenario}",
        jira_key=story,
        rn_key=epic,
        feature_story=story,
        traceability=f"RN={epic}; Story={story}; Scenario={scenario}",
        artifact_key=epic,
        story_key=story,
    )


def _candidate(
    *,
    name: str = "Ver el ticket",
    func: str | None = "EPIC-1",
    jira: str | None = "STORY-1",
    covers: list[str] | None = None,
    expected: str = "El usuario ve el Ticket en pantalla",
    action: str = "El usuario abre el Ticket",
    justification: str = "LLM",
) -> GeneratedCaseCandidate:
    return GeneratedCaseCandidate(
        name=name,
        description=name,
        steps=[CandidateStep(step_number=1, action=action, expected_result=expected)],
        related_functionality=func,
        related_jira=jira,
        evidence="llm",
        justification=justification,
        covers=covers or ["COV-001"],
    )


def _keep(candidates: list[GeneratedCaseCandidate], units: list[CoverageUnit] | None = None):
    units = units or [_unit("COV-001", "Ver el ticket")]
    artifacts = [
        {
            "key": "EPIC-1",
            "summary": "MDP: Actualizar pantalla de Ticket con método de pago asociado",
            "children": [{"key": "STORY-1", "summary": "Feature: Actualizar pantalla de Ticket"}],
        }
    ]
    tickets = {"functionality": [("EPIC-1", "MDP: Actualizar pantalla de Ticket con método de pago asociado")]}
    return _keep_llm_functionality_candidates(
        candidates,
        {"EPIC-1", "STORY-1"},
        {unit.coverage_id for unit in units},
        inventory=units,
        artifacts=artifacts,
        tickets=tickets,
    )


def test_llm_valid_jira_key_is_accepted() -> None:
    kept = _keep([_candidate(func="EPIC-1", jira="STORY-1")])
    assert len(kept) == 1
    assert kept[0].related_functionality == "EPIC-1"
    assert kept[0].generation_origin == "llm"


def test_llm_epic_summary_resolves_to_key() -> None:
    kept = _keep(
        [
            _candidate(
                func="MDP: Actualizar pantalla de Ticket con método de pago asociado",
                jira="Feature: Actualizar pantalla de Ticket",
            )
        ]
    )
    assert len(kept) == 1
    assert kept[0].related_functionality == "EPIC-1"
    assert kept[0].related_jira == "STORY-1"
    assert "LLM related_functionality original" in (kept[0].evidence or "")
    assert "llm-ref-resolved" in (kept[0].applied_rules or [])


def test_llm_unknown_jira_key_is_rejected() -> None:
    kept = _keep([_candidate(func="ZZZZ-999", jira="STORY-1")])
    assert kept == []


def test_llm_unknown_coverage_id_is_rejected() -> None:
    kept = _keep([_candidate(covers=["COV-999"])])
    assert kept == []


def test_llm_partial_cover_does_not_keep_unknown_ids() -> None:
    units = [_unit("COV-001", "Uno"), _unit("COV-002", "Dos")]
    kept = _keep([_candidate(covers=["COV-001", "COV-999"])], units)
    assert len(kept) == 1
    assert kept[0].covers == ["COV-001"]


def _two_story_artifacts() -> list[dict]:
    return [
        {
            "key": "EPIC-1",
            "issuetype": "Epic",
            "summary": "MDP: Actualizar pantalla de Ticket con método de pago asociado",
            "description": "",
            "acceptance_criteria": "",
            "children": [
                {
                    "key": "STORY-1",
                    "issuetype": "Story",
                    "summary": "Feature visible ticket",
                    "description": (
                        "Feature: Ticket\n"
                        "Scenario: Ver el ticket actualizado\n"
                        "  When el usuario visualiza la pantalla de Ticket\n"
                        "  Then se muestra el Ticket con el método de pago\n"
                        "Scenario: Ver el texto truncado\n"
                        "  When el texto supera el límite\n"
                        '  Then debe mostrarse "..." al final del texto\n'
                    ),
                    "acceptance_criteria": "",
                }
            ],
        }
    ]


def _llm_http(candidates: list[dict]) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"candidates": candidates})}}]
    }
    client = MagicMock()
    client.post.return_value = response
    return client


def _llm_item(name: str, covers: list[str], **extra: object) -> dict:
    item = {
        "name": name,
        "description": name,
        "precondition": "El usuario inició sesión",
        "requires_condition": False,
        "steps": [
            {
                "step_number": 1,
                "action": extra.get("action") or "El usuario abre la pantalla de Ticket",
                "expected_result": extra.get("expected") or "El usuario ve el Ticket con el método de pago",
            }
        ],
        "related_functionality": extra.get("related_functionality", "EPIC-1"),
        "related_jira": extra.get("related_jira", "STORY-1"),
        "related_rn": "rn.pdf",
        "evidence": "llm-evidence-unique",
        "justification": extra.get("justification") or "Redacción LLM del CoverageUnit.",
        "possible_duplicate_of": None,
        "confidence": "high",
        "review_required": True,
        "covers": covers,
    }
    if extra.get("test_data") is not None:
        item["test_data"] = extra["test_data"]
        item["steps"][0]["test_data"] = extra["test_data"]
    return item


def _generate(fake_client: MagicMock):
    with patch("app.services.ai_case_engine.fetch_artifacts_for_keys", lambda _keys: _two_story_artifacts()):
        with patch("app.services.ai_case_engine.httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value = fake_client
            with patch("app.services.ai_case_engine.settings") as settings:
                settings.openai_api_key = "sk-test"
                settings.openai_model = "gpt-4o-mini"
                settings.openai_base_url = "https://api.openai.com/v1"
                return generate_release_app_candidates(
                    release_id=1,
                    release_name="trace",
                    validation_type="Funcional",
                    analysis_present=True,
                    rn_filename="rn.pdf",
                    pdf_bytes=b"pdf",
                    release_context={"name": "trace"},
                    existing_cases=[],
                    tickets={"functionality": [("EPIC-1", "MDP ticket")]},
                )


def test_llm_cover_skips_fill_for_that_unit() -> None:
    fake = _llm_http(
        [
            _llm_item("Ver el ticket actualizado", ["COV-001"]),
            _llm_item(
                "Ver el texto truncado",
                ["COV-002"],
                expected='El usuario ve "..." al final del texto',
            ),
        ]
    )
    proposal = _generate(fake)
    assert fake.post.call_count == 1
    assert all(item.generation_origin == "llm" for item in proposal.candidates)
    assert "coverage-fill" not in (proposal.engine or "")
    assert set(proposal.covered_coverage_ids) == {"COV-001", "COV-002"}


def test_llm_partial_inventory_fills_only_missing() -> None:
    fake = _llm_http([_llm_item("Ver el ticket actualizado", ["COV-001"])])
    proposal = _generate(fake)
    assert proposal.engine == "llm+coverage-fill"
    origins = {item.generation_origin for item in proposal.candidates}
    assert "llm" in origins
    assert "coverage-fill" in origins
    fill = [item for item in proposal.candidates if item.generation_origin == "coverage-fill"]
    assert fill
    assert all("COV-001" not in (item.covers or []) for item in fill)
    llm = [item for item in proposal.candidates if item.generation_origin == "llm"]
    assert any("COV-001" in (item.covers or []) for item in llm)
    assert "llm-evidence-unique" in " ".join(item.evidence or "" for item in llm)


def test_llm_failure_falls_back_to_deterministic() -> None:
    fake = MagicMock()
    fake.post.side_effect = RuntimeError("timeout")
    proposal = _generate(fake)
    assert proposal.engine in {"evidence-jira", "evidence-fallback"}
    assert proposal.candidates
    assert all(item.generation_origin != "llm" for item in proposal.candidates)


def test_equivalent_llm_cases_are_deduped() -> None:
    left = _candidate(name="Uno", covers=["COV-001"], expected="El usuario ve el Ticket en pantalla")
    right = _candidate(name="Dos", covers=["COV-002"], expected="El usuario ve el Ticket en pantalla")
    left.related_jira = "STORY-1"
    right.related_jira = "STORY-2"
    merged = apply_qc_rules([left, right])
    assert len(merged) == 1
    assert set(merged[0].covers) == {"COV-001", "COV-002"}


def test_accepted_candidate_keeps_traceability() -> None:
    kept = _keep([_candidate(func="EPIC-1", jira="STORY-1")])
    assert kept[0].related_functionality == "EPIC-1"
    assert kept[0].related_jira == "STORY-1"
    assert kept[0].covers == ["COV-001"]


def test_llm_technical_language_moves_out_of_user_columns() -> None:
    fake = _llm_http(
        [
            _llm_item(
                "Ver el ticket actualizado",
                ["COV-001"],
                action="El usuario visualiza el Ticket",
                expected="la aplicación construye paymentMethodData.account en pantalla",
            ),
            _llm_item(
                "Ver el texto truncado",
                ["COV-002"],
                expected='El usuario ve "..." al final del texto',
            ),
        ]
    )
    proposal = _generate(fake)
    blob = " ".join(
        f"{step.action} {step.expected_result}"
        for item in proposal.candidates
        if item.generation_origin == "llm"
        for step in item.steps
    )
    assert "paymentMethodData" not in blob
    assert "la aplicación construye" not in blob.lower()
    llm = next(item for item in proposal.candidates if item.generation_origin == "llm")
    assert llm.justification == "Redacción LLM del CoverageUnit."
