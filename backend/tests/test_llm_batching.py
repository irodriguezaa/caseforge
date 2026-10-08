"""Deterministic OpenAI batching: Story boundaries, 50k chunks, per-batch fallback."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.schemas.case_generation import CoverageUnit
from app.services.ai_case_engine import (
    _ENGINE_RULES,
    _JSON_INSTRUCTIONS,
    apply_qc_rules,
    generate_release_app_candidates,
    llm_payload_chars,
    partition_coverage_for_llm,
    reconcile_llm_coverage,
)
from tests.test_llm_candidate_keep import _generate, _llm_http, _llm_item, _unit


def _story(key: str, scenario: str, then: str = "se muestra el resultado") -> dict:
    return {
        "key": key,
        "issuetype": "Technical Story",
        "summary": key,
        "description": (
            f"Feature: {key}\n"
            f"Scenario: {scenario}\n"
            f"  When el usuario abre la pantalla\n"
            f"  Then {then}\n"
        ),
        "acceptance_criteria": "",
    }


def _epic(key: str, children: list[dict]) -> dict:
    return {
        "key": key,
        "issuetype": "Technical Epic",
        "summary": key,
        "description": "",
        "acceptance_criteria": "",
        "children": children,
    }


def test_small_story_is_one_batch() -> None:
    units = [
        _unit("COV-001", "Uno", story="STORY-1", epic="EPIC-1"),
        _unit("COV-002", "Dos", story="STORY-1", epic="EPIC-1"),
    ]
    batches = partition_coverage_for_llm(
        units,
        tickets={"functionality": [("EPIC-1", "epic")]},
        artifacts=[_epic("EPIC-1", [_story("STORY-1", "Uno")])],
        context={"name": "t"},
        existing=[],
    )
    assert len(batches) == 1
    assert batches[0].epc == "EPIC-1"
    assert batches[0].story == "STORY-1"
    assert [unit.coverage_id for unit in batches[0].units] == ["COV-001", "COV-002"]
    assert {unit.batch_id for unit in batches[0].units} == {batches[0].batch_id}


def test_multiple_stories_are_multiple_batches() -> None:
    units = [
        _unit("COV-001", "Uno", story="STORY-1", epic="EPIC-1"),
        _unit("COV-002", "Dos", story="STORY-2", epic="EPIC-1"),
    ]
    batches = partition_coverage_for_llm(
        units,
        tickets={"functionality": [("EPIC-1", "epic")]},
        artifacts=[_epic("EPIC-1", [_story("STORY-1", "Uno"), _story("STORY-2", "Dos")])],
        context={"name": "t"},
        existing=[],
    )
    assert [batch.story for batch in batches] == ["STORY-1", "STORY-2"]
    assert batches[0].batch_id != batches[1].batch_id


def test_story_over_limit_is_chunked_deterministically() -> None:
    units = [
        _unit("COV-001", "Uno", story="STORY-1", epic="EPIC-1"),
        _unit("COV-002", "Dos", story="STORY-1", epic="EPIC-1"),
        _unit("COV-003", "Tres", story="STORY-1", epic="EPIC-1"),
    ]
    tickets = {"functionality": [("EPIC-1", "epic")]}
    artifacts = [_epic("EPIC-1", [_story("STORY-1", "Uno")])]
    context = {"name": "t"}
    one = llm_payload_chars(context, [], tickets, artifacts, units[:1])
    batches = partition_coverage_for_llm(
        units,
        tickets=tickets,
        artifacts=artifacts,
        context=context,
        existing=[],
        limit=one,
    )
    assert len(batches) >= 2
    covered = [unit.coverage_id for batch in batches for unit in batch.units]
    assert covered == ["COV-001", "COV-002", "COV-003"]
    assert all(batch.story == "STORY-1" for batch in batches)


def _two_story_artifacts() -> list[dict]:
    return [
        _epic(
            "EPIC-1",
            [
                _story("STORY-1", "Ver el ticket actualizado", "se muestra el Ticket"),
                _story("STORY-2", "Ver el texto truncado", 'debe mostrarse "..."'),
            ],
        )
    ]


def _generate_stories(fake: MagicMock, artifacts: list[dict], tickets=None):
    with patch("app.services.ai_case_engine.fetch_artifacts_for_keys", lambda _keys: artifacts):
        with patch("app.services.ai_case_engine.httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value = fake
            with patch("app.services.ai_case_engine.settings") as settings:
                settings.openai_api_key = "sk-test"
                settings.openai_model = "gpt-4o-mini"
                settings.openai_base_url = "https://api.openai.com/v1"
                return generate_release_app_candidates(
                    release_id=1,
                    release_name="batch",
                    validation_type="Funcional",
                    analysis_present=True,
                    rn_filename="rn.pdf",
                    pdf_bytes=b"pdf",
                    release_context={"name": "batch"},
                    existing_cases=[],
                    tickets=tickets or {"functionality": [("EPIC-1", "MDP ticket")]},
                )


def test_coverage_unit_is_traceable_to_batch() -> None:
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
    assert proposal.generation_stats
    assert proposal.generation_stats.llm_batches
    batch_id = proposal.generation_stats.llm_batches[0]["batch_id"]
    llm = [row for row in proposal.candidates if row.generation_origin == "llm"]
    assert llm
    assert all(row.batch_id for row in llm)
    assert proposal.generation_stats.coverage_unit_status["COV-001"] in {
        "llm_covered",
        "llm_merged",
    }


def test_failed_batch_falls_back_only_that_batch() -> None:
    ok = _llm_http(
        [
            _llm_item(
                "Ver el texto truncado",
                ["COV-002"],
                related_jira="STORY-2",
                expected='El usuario ve "..." al final del texto',
            )
        ]
    ).post.return_value
    fake = MagicMock()
    fake.post.side_effect = [RuntimeError("timeout"), ok]
    proposal = _generate_stories(fake, _two_story_artifacts())
    origins = {row.generation_origin for row in proposal.candidates}
    assert "llm" in origins
    llm_covers = {cid for row in proposal.candidates if row.generation_origin == "llm" for cid in (row.covers or [])}
    assert "COV-002" in llm_covers
    assert proposal.generation_stats
    statuses = proposal.generation_stats.coverage_unit_status
    assert statuses.get("COV-001") == "llm_failed"
    failed_rows = [row for row in proposal.generation_stats.llm_batches if row.get("error")]
    assert failed_rows
    assert failed_rows[0]["story"] == "STORY-1"


def test_second_pass_sends_only_uncovered_units() -> None:
    first = _llm_item("Ver el ticket actualizado", ["COV-001"])
    second = _llm_item(
        "Ver el texto truncado",
        ["COV-002"],
        expected='El usuario ve "..." al final del texto',
    )
    fake = MagicMock()
    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.json.return_value = {"choices": [{"message": {"content": json.dumps({"candidates": [first]})}}]}
    resp2 = MagicMock()
    resp2.status_code = 200
    resp2.json.return_value = {
        "choices": [{"message": {"content": json.dumps({"candidates": [second]})}}]
    }
    fake.post.side_effect = [resp1, resp2]
    proposal = _generate(fake)
    assert fake.post.call_count == 2
    second_body = fake.post.call_args_list[1].kwargs["json"]
    user = json.loads(second_body["messages"][1]["content"])
    ids = [item["coverage_id"] for item in user["coverage_inventory"]]
    assert ids == ["COV-002"]
    assert "COV-001" not in ids
    system = second_body["messages"][0]["content"]
    assert system == _ENGINE_RULES + "\n" + _JSON_INSTRUCTIONS
    llm_covers = {cid for row in proposal.candidates if row.generation_origin == "llm" for cid in (row.covers or [])}
    assert llm_covers >= {"COV-001", "COV-002"}


def test_cross_batch_dedupe_uses_functional_equivalence_not_expected_only() -> None:
    fake = MagicMock()

    def _resp(item: dict) -> MagicMock:
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"candidates": [item]})}}]
        }
        return response

    fake.post.side_effect = [
        _resp(
            _llm_item(
                "Ver el ticket actualizado",
                ["COV-001"],
                related_jira="STORY-1",
                action="El usuario abre la pantalla de Ticket",
                expected="El usuario ve el Ticket en pantalla",
            )
        ),
        _resp(
            _llm_item(
                "Ver el ticket otra historia",
                ["COV-002"],
                related_jira="STORY-2",
                action="El usuario abre la pantalla de Ticket",
                expected="El usuario ve el Ticket en pantalla",
            )
        ),
    ]
    proposal = _generate_stories(fake, _two_story_artifacts())
    llm = [row for row in proposal.candidates if row.generation_origin == "llm"]
    merged = apply_qc_rules(llm)
    assert len(merged) == 1
    assert set(merged[0].covers) == {"COV-001", "COV-002"}


def test_no_cross_epc_merge_after_batches() -> None:
    artifacts = [
        _epic("EPIC-1", [_story("STORY-1", "Uno", "se muestra A")]),
        _epic("EPIC-2", [_story("STORY-2", "Dos", "se muestra A")]),
    ]

    def _resp(item: dict) -> MagicMock:
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"candidates": [item]})}}]
        }
        return response

    fake = MagicMock()
    fake.post.side_effect = [
        _resp(
            _llm_item(
                "Caso A",
                ["COV-001"],
                related_functionality="EPIC-1",
                related_jira="STORY-1",
                expected="Se muestra pantalla PIN",
            )
        ),
        _resp(
            _llm_item(
                "Caso B",
                ["COV-002"],
                related_functionality="EPIC-2",
                related_jira="STORY-2",
                expected="Se muestra pantalla PIN",
            )
        ),
    ]
    proposal = _generate_stories(
        fake,
        artifacts,
        tickets={"functionality": [("EPIC-1", "e1"), ("EPIC-2", "e2")]},
    )
    llm = [row for row in proposal.candidates if row.generation_origin == "llm"]
    epcs = {(row.related_functionality or "").split("|")[0].strip() for row in llm}
    assert "EPIC-1" in epcs and "EPIC-2" in epcs
    merged = apply_qc_rules(llm)
    epcs_merged = {(row.related_functionality or "").split("|")[0].strip() for row in merged}
    assert epcs_merged >= {"EPIC-1", "EPIC-2"}
    assert not any("|" in (row.related_functionality or "") and "EPIC-1" in (row.related_functionality or "") and "EPIC-2" in (row.related_functionality or "") for row in merged)


def test_reconcile_states() -> None:
    units = [
        _unit("COV-001", "a"),
        _unit("COV-002", "b"),
        _unit("COV-003", "c"),
        _unit("COV-004", "d"),
    ]
    from tests.test_llm_candidate_keep import _candidate

    covered = _candidate(name="one", covers=["COV-001"])
    merged = _candidate(name="two", covers=["COV-002", "COV-003"])
    covered.generation_origin = "llm"
    merged.generation_origin = "llm"
    status = reconcile_llm_coverage(units, [covered, merged], failed_ids={"COV-004"})
    assert status == {
        "COV-001": "llm_covered",
        "COV-002": "llm_merged",
        "COV-003": "llm_merged",
        "COV-004": "llm_failed",
    }
