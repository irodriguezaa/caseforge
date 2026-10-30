"""Orquestación v2-B: recolección v2 → filtro QC → A → filtro escenarios → B overlay → C → consolidación."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from app.schemas.case_generation import (
    GenerateCasesResponse,
    GeneratedCaseCandidate,
    GenerationStats,
)
from app.services.qc_v2.collect import EpicBundle, JiraReader, collect_epic
from app.services.qc_v2.context import DeviceContext, device_context
from app.services.qc_v2.engine import EpicRun, _ledger, _to_candidate
from app.services.qc_v2.llm import QuotaExhausted, chat_json
from app.services.qc_v2.stages import (
    ChatFn,
    StageAResult,
    run_stage_a_by_stories,
    run_stage_b,
    run_stage_c,
)
from app.services.qc_v2b import ENGINE_TAG
from app.services.qc_v2b.eligibility import (
    classify_scenario,
    classify_text,
    expected_has_technical_leak,
    filter_bundle,
)
from app.services.qc_v2b.pack import consolidate

logger = logging.getLogger(__name__)
_OVERLAY = (Path(__file__).parent / "prompts" / "etapa_b_overlay.md").read_text(encoding="utf-8")


def _dedupe_ledger(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (row.get("epic"), row.get("story"), row.get("scenario"))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _with_overlay(chat: ChatFn) -> ChatFn:
    def wrapped(messages, **kwargs):
        msgs = list(messages)
        if msgs and msgs[0].get("role") == "system":
            system = msgs[0].get("content") or ""
            if "REGLA DEL BUG" in system and "REGLAS EXTRA DEL PAQUETE QC" not in system:
                msgs[0] = {"role": "system", "content": system + "\n\n" + _OVERLAY}
        return chat(msgs, **kwargs)

    return wrapped


def _stamp_v2b(candidate: GeneratedCaseCandidate, display_priority: str | None) -> GeneratedCaseCandidate:
    rules = list(candidate.applied_rules or [])
    rules.append("qc-v2b:paquete")
    if display_priority:
        rules.append(f"qc-v2b:prioridad={display_priority}")
        candidate.priority_reason = "Major: conformidad visual"
    optional = 0
    table = candidate.variant_table or ""
    optional = table.lower().count("opcional:")
    if optional:
        rules.append(f"qc-v2b:variantes-opcionales={optional}")
    candidate.applied_rules = rules
    candidate.generation_origin = ENGINE_TAG
    if candidate.justification:
        candidate.justification = candidate.justification.replace("QcPulse v2 ·", "QcPulse v2-B ·", 1)
    return candidate


def _hours_skip_optional(candidate: GeneratedCaseCandidate) -> bool:
    """Variantes opcionales no generan casos extra; el caso del paquete sí cuenta."""
    return "qc-v2b:fuera" in (candidate.applied_rules or [])


def _is_fallback(candidate: GeneratedCaseCandidate) -> bool:
    return candidate.generation_origin == "fallback" or "qc-v2b:fallback" in (candidate.applied_rules or [])


def _sanitize_candidate(candidate: GeneratedCaseCandidate) -> GeneratedCaseCandidate | None:
    leaks = [step for step in candidate.steps if expected_has_technical_leak(step.expected_result or "")]
    if leaks:
        tech = "; ".join((step.expected_result or "").strip() for step in leaks)
        candidate.technical_reference = "; ".join(
            part for part in (candidate.technical_reference or "", tech) if part
        )
        return None
    blob = f"{candidate.name}\n{candidate.description or ''}"
    decision = classify_text(candidate.name, blob)
    if not decision.eligible:
        return None
    return candidate


def _fallback_story_candidates(bundle: EpicBundle, story, ctx: DeviceContext) -> list[GeneratedCaseCandidate]:
    from app.schemas.case_generation import GenerationStats
    from app.services.gherkin_coverage import candidates_from_jira_artifacts

    body = (story.context or "") + "\n" + "\n\n".join(
        f"Scenario: {item.title}\n{item.text}" for item in story.scenarios
    )
    artifacts = [
        {
            "key": bundle.key,
            "summary": bundle.summary,
            "children": [
                {
                    "key": story.key,
                    "summary": story.summary,
                    "description": body,
                    "acceptance_criteria": "",
                }
            ],
        }
    ]
    stats = GenerationStats()
    raw = candidates_from_jira_artifacts(artifacts, "", [], lambda *_a: None, stats=stats)
    kept: list[GeneratedCaseCandidate] = []
    for candidate in raw:
        candidate.related_functionality = bundle.key
        candidate.generation_origin = "fallback"
        candidate.source_type = "fallback"
        candidate.applied_rules = list(candidate.applied_rules or []) + ["qc-v2b:fallback"]
        if candidate.justification and not candidate.justification.lower().startswith("fallback"):
            candidate.justification = f"fallback · {candidate.justification}"
        else:
            candidate.justification = candidate.justification or "fallback"
        cleaned = _sanitize_candidate(candidate)
        if cleaned is None:
            continue
        kept.append(cleaned)
    return kept


def run_epic(bundle: EpicBundle, ctx: DeviceContext, chat: ChatFn = chat_json) -> EpicRun:
    started = time.monotonic()
    run = EpicRun(bundle=bundle)
    if not bundle.covs and not bundle.crns:
        run.error = "sin contenido en Jira para generar"
        run.ledger = _ledger(run)
        return run

    filtered, pre_discarded = filter_bundle(bundle)
    extra_ledger = list(pre_discarded)
    if not filtered.covs and not filtered.crns:
        run.error = None
        run.ms = int((time.monotonic() - started) * 1000)
        run.ledger = extra_ledger + _ledger(run)
        logger.info("qc_v2b %s (sin ítems elegibles)", run.summary())
        return run

    chat_b = _with_overlay(chat)
    run.stage_a = run_stage_a_by_stories(filtered, ctx, chat=chat)
    failed_keys = {
        row.split(":", 1)[0].strip()
        for row in (run.stage_a.story_errors if run.stage_a else [])
        if ":" in row
    }
    if run.stage_a and run.stage_a.error and not run.stage_a.scenarios:
        failed_keys = {story.key for story in filtered.technical_stories}
        run.error = None
    for story in filtered.technical_stories:
        if story.key not in failed_keys:
            continue
        for candidate in _fallback_story_candidates(filtered, story, ctx):
            run.candidates.append(candidate)
        extra_ledger.append(
            {
                "story": story.key,
                "epic": bundle.key,
                "scenario": "Fallback",
                "estado": "fallback",
                "case_id": "",
                "motivo": "; ".join(run.stage_a.story_errors or [run.stage_a.error or "etapa A"]),
            }
        )
    if run.stage_a and run.stage_a.scenarios:
        kept_scenarios = []
        for scenario in run.stage_a.scenarios:
            decision = classify_scenario(scenario)
            if decision.eligible:
                kept_scenarios.append(scenario)
            else:
                extra_ledger.append(
                    {
                        "story": bundle.key,
                        "epic": bundle.key,
                        "scenario": f"{scenario.id} {scenario.titulo}"[:300],
                        "estado": decision.estado,
                        "case_id": "",
                        "motivo": decision.motivo,
                    }
                )
        run.stage_a = StageAResult(
            resumen=run.stage_a.resumen,
            scenarios=kept_scenarios,
            excluded=run.stage_a.excluded,
            missing=run.stage_a.missing,
            metas=run.stage_a.metas,
            error=None,
            story_errors=run.stage_a.story_errors,
        )
        if kept_scenarios:
            run.stage_b = run_stage_b(filtered, ctx, run.stage_a, chat=chat_b)
            run_stage_c(run.stage_b)
            by_id = {s.id: s for s in kept_scenarios}
            designed = [case for result in run.stage_b for case in result.cases]
            packed, post_discarded = consolidate(designed, filtered, kept_scenarios)
            extra_ledger.extend(post_discarded)
            packed_by_scenario: dict[str, list] = {}
            for case in packed:
                packed_by_scenario.setdefault(case.scenario_id, []).append(case)
            for result in run.stage_b:
                result.cases = packed_by_scenario.get(result.scenario_id, [])
            for case in packed:
                scenario = by_id.get(case.scenario_id)
                if scenario is None:
                    continue
                display = "MAJOR" if case.tipo == "ERG" or (case.riesgo or "").startswith("Major") else None
                candidate = _to_candidate(case, scenario, bundle, ctx)
                stamped = _sanitize_candidate(_stamp_v2b(candidate, display))
                if stamped is not None:
                    run.candidates.append(stamped)
            run.candidates = [c for c in run.candidates if not _hours_skip_optional(c)]

    metas = list((run.stage_a.metas if run.stage_a else [])) + [m for r in run.stage_b for m in r.metas]
    run.llm_calls = len(metas)
    run.prompt_tokens = sum(m.prompt_tokens for m in metas)
    run.completion_tokens = sum(m.completion_tokens for m in metas)
    run.ms = int((time.monotonic() - started) * 1000)
    run.ledger = _dedupe_ledger(extra_ledger + _ledger(run))
    logger.info("qc_v2b %s", run.summary())
    return run


def run_epics(
    epic_keys: list[str],
    platform: str | None,
    region: str | None = None,
    reader: JiraReader | None = None,
    chat: ChatFn = chat_json,
) -> list[EpicRun]:
    ctx = device_context(platform, region)
    runs: list[EpicRun] = []
    if reader is None:
        from app.services.jira_client import _client

        with _client(timeout=60.0) as client:
            bundles = [collect_epic(JiraReader(client), key) for key in epic_keys]
    else:
        bundles = [collect_epic(reader, key) for key in epic_keys]
    for bundle in bundles:
        try:
            runs.append(run_epic(bundle, ctx, chat=chat))
        except QuotaExhausted as exc:
            run = EpicRun(bundle=bundle, error=f"corrida detenida: {exc}")
            run.ledger = _ledger(run)
            runs.append(run)
            break
    return runs


def generate_release_v2b(
    *,
    release_id: int,
    release_name: str,
    validation_type: str | None,
    analysis_present: bool,
    release_context: dict[str, Any],
    functionality_keys: list[str],
    stats: GenerationStats,
) -> GenerateCasesResponse:
    """Punto de entrada desde ai_case_engine cuando QC_ENGINE=v2b."""
    platform = release_context.get("platform") or (release_context.get("analysis") or {}).get("detected_platform")
    runs = run_epics(functionality_keys, platform)
    candidates = [c for run in runs for c in run.candidates]
    stats.scenario_ledger = [row for run in runs for row in run.ledger]
    details = [run.summary() for run in runs]
    details += [f"{run.bundle.key} aviso: {w}" for run in runs for w in run.bundle.warnings]
    quota_stop = any((run.error or "").startswith("corrida detenida") for run in runs)
    run_errors = [f"{run.bundle.key}: {run.error}" for run in runs if run.error]
    if quota_stop:
        message = (
            "La corrida se detuvo: OpenAI no tiene créditos. Recarga saldo y vuelve a generar."
            + (f" ({run_errors[0]})" if run_errors else "")
        )
        candidates = []
    elif candidates:
        message = f"QcPulse v2-B propuso {len(candidates)} caso(s) del paquete QC. La IA propone; QC decide."
    else:
        message = "QcPulse v2-B no generó casos de paquete; revisa los avisos en Escenarios de Jira."
        if run_errors:
            message += " " + "; ".join(run_errors)
    covered = sorted({f"{c.related_functionality}:{cid}" for c in candidates for cid in c.covers})
    required = [f"{run.bundle.key}:{item.id}" for run in runs for item in run.bundle.crns + run.bundle.covs]
    return GenerateCasesResponse(
        status="PROPOSED" if candidates else "EMPTY",
        message=message,
        release_id=release_id,
        release_name=release_name,
        validation_type=validation_type,
        has_analysis=analysis_present,
        engine=ENGINE_TAG,
        candidates=candidates,
        persisted=False,
        generation_stats=stats,
        analysis_details=details,
        coverage_unit_count=len(required),
        covered_coverage_ids=covered,
        uncovered_coverage_ids=[cid for cid in required if cid not in set(covered)],
        rn_scope_coverage={
            "scenario_ledger": list(stats.scenario_ledger),
            "story_to_epic": {
                story.key: run.bundle.key for run in runs for story in run.bundle.technical_stories
            },
        },
        functionality_keys=list(functionality_keys),
    )
