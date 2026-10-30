"""Orquestación v2: recolección → Etapa A → Etapa B (paralelo) → Etapa C → candidatos + ledger."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.schemas.case_generation import (
    CandidateStep,
    GenerateCasesResponse,
    GeneratedCaseCandidate,
    GenerationStats,
)
from app.services.qc_v2 import ENGINE_TAG
from app.services.qc_eligibility import evaluate_scenario, select_qc_gherkin
from app.services.qc_v2.collect import EpicBundle, Item, JiraReader, collect_epic
from app.services.qc_v2.context import DeviceContext, device_context
from app.services.qc_v2.llm import QuotaExhausted, chat_json
from app.services.qc_v2.stages import (
    ChatFn,
    DesignedCase,
    Scenario,
    StageAResult,
    StageBResult,
    run_stage_a,
    run_stage_b,
    run_stage_c,
)

logger = logging.getLogger(__name__)

_CONFIDENCE = {"alta": "high", "media": "medium", "baja": "low"}
_SITUACION = {
    "ninguna": "cruce",
    "sin_tecnico": "solo negocio",
    "sin_negocio": "solo técnico",
    "implicito": "implícito",
}


def apply_positive_filter(bundle: EpicBundle) -> tuple[list[dict], list[tuple[str, str, str]]]:
    """Keep only QC-eligible Gherkin/CRN (and impact units). Shared rules live in qc_eligibility."""
    ledger: list[dict] = []
    aliases: list[tuple[str, str, str]] = []
    for story in bundle.technical_stories:
        rows = [(story.key, item.title, item.text, story.summary) for item in story.scenarios]
        kept, dropped = select_qc_gherkin(bundle.key, rows)
        ledger.extend(dropped)
        by_title = {item.title: item for item in story.scenarios}
        used: set[str] = set()
        new_items: list[Item] = []
        for selected in kept:
            item = by_title.get(selected.title)
            if item is None:
                continue
            if selected.group in used:
                ledger.append(
                    {
                        "story": selected.story_key,
                        "epic": bundle.key,
                        "scenario": selected.title,
                        "estado": "verificación técnica",
                        "motivo": "cubierto por el caso de la misma superficie y condición de entrada",
                        "case_id": "",
                    }
                )
                aliases.append((selected.story_key, selected.title, new_items[-1].id if new_items else item.id))
                continue
            used.add(selected.group)
            text = selected.body
            new_items.append(Item(item.id, item.title, text, item.source_key))
            aliases.append((selected.story_key, selected.title, item.id))
        story.scenarios = new_items
    for story in bundle.user_stories:
        kept_crn: list[Item] = []
        for item in story.criteria:
            elig = evaluate_scenario(item.title, item.text, story.summary)
            if elig.ok:
                kept_crn.append(item)
                aliases.append((story.key, item.title, item.id))
            else:
                ledger.append(
                    {
                        "story": story.key,
                        "epic": bundle.key,
                        "scenario": item.title,
                        "estado": elig.ledger_estado,
                        "motivo": elig.ledger_motivo,
                        "case_id": "",
                    }
                )
        story.criteria = kept_crn
    return ledger, aliases


@dataclass
class EpicRun:
    bundle: EpicBundle
    stage_a: StageAResult | None = None
    stage_b: list[StageBResult] = field(default_factory=list)
    candidates: list[GeneratedCaseCandidate] = field(default_factory=list)
    ledger: list[dict[str, Any]] = field(default_factory=list)
    qc_aliases: list[tuple[str, str, str]] = field(default_factory=list)
    ms: int = 0
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str | None = None

    def summary(self) -> str:
        cases = len(self.candidates)
        scenarios = len(self.stage_a.scenarios) if self.stage_a else 0
        return (
            f"{self.bundle.key}: CRN={len(self.bundle.crns)} COV={len(self.bundle.covs)} "
            f"escenarios={scenarios} casos={cases} llamadas={self.llm_calls} "
            f"tokens={self.prompt_tokens}+{self.completion_tokens} tiempo={self.ms / 1000:.0f}s"
            + (f" ERROR={self.error}" if self.error else "")
        )


def _variant_table(case: DesignedCase) -> str | None:
    if not case.variantes:
        return None
    rows = ["Condición | Resultado esperado"]
    rows += [f"{v['condicion']} | {v['resultado_esperado']}" for v in case.variantes]
    return "\n".join(rows)


def _to_candidate(
    case: DesignedCase, scenario: Scenario, bundle: EpicBundle, ctx: DeviceContext
) -> GeneratedCaseCandidate:
    covers = scenario.cubre_negocio + scenario.cubre_tecnico
    stories = []
    for item_id in covers:
        item = bundle.item(item_id)
        if item and item.source_key not in stories:
            stories.append(item.source_key)
    evidence_lines = [f"{scenario.id} · {scenario.titulo}"]
    for item_id in covers:
        item = bundle.item(item_id)
        if item:
            evidence_lines.append(f"{item.id} ({item.source_key}): {item.title}")
    justification = (
        f"QcPulse v2 · {scenario.id} · tipo={case.tipo} · brecha={scenario.brecha} · "
        f"complejidad={case.complejidad}" + (f" · riesgo: {case.riesgo}" if case.riesgo else "")
    )
    rules = [
        f"qc-v2:tipo={case.tipo}",
        f"qc-v2:brecha={scenario.brecha}",
        f"qc-v2:complejidad={case.complejidad}",
        f"qc-v2:escenario={scenario.id}",
    ]
    if case.review_reasons:
        rules.append("qc-v2:requiere-revision")
    return GeneratedCaseCandidate(
        name=case.titulo,
        description=f"{scenario.titulo}. {scenario.descripcion}".strip(),
        precondition="; ".join(case.precondiciones) or None,
        steps=[
            CandidateStep(step_number=i, action=s["accion"], expected_result=s["resultado_esperado"])
            for i, s in enumerate(case.pasos, start=1)
        ],
        related_functionality=bundle.key,
        related_jira=", ".join(stories) or bundle.key,
        evidence="\n".join(evidence_lines),
        justification=justification,
        confidence=_CONFIDENCE.get(case.confianza, "medium"),
        review_required=bool(case.review_reasons),
        priority="BLOCKER" if case.prioridad == "BLOCKER" else "CRITICAL",
        component=bundle.key,
        applied_rules=rules,
        generation_origin=ENGINE_TAG,
        covers=covers,
        covered_unit_ids=covers,
        technical_reference=case.referencia_tecnica,
        variant_table=_variant_table(case),
        applicability="ejecutable",
        applicability_reason=("requiere revisión: " + "; ".join(case.review_reasons)) if case.review_reasons else None,
        device=ctx.dispositivo,
        device_source="contexto de la Release",
    )


def _ledger(run: EpicRun) -> list[dict[str, Any]]:
    bundle, stage_a = run.bundle, run.stage_a
    rows: list[dict[str, Any]] = list(run.ledger)
    names_by_id: dict[str, list[str]] = {}
    for candidate in run.candidates:
        for cid in candidate.covers or []:
            names_by_id.setdefault(cid, []).append(candidate.name)
    seen_jira: set[tuple[str, str]] = {
        (str(row.get("story") or ""), str(row.get("scenario") or "")) for row in rows
    }
    for story, title, cov_id in run.qc_aliases:
        key = (story, title)
        names = names_by_id.get(cov_id) or []
        if names:
            if key in seen_jira:
                for row in rows:
                    if row.get("story") == story and row.get("scenario") == title:
                        row["estado"] = "caso ejecutable"
                        row["case_id"] = "; ".join(names)
                        row["motivo"] = ""
                continue
            rows.append(
                {
                    "story": story,
                    "epic": bundle.key,
                    "scenario": title,
                    "estado": "caso ejecutable",
                    "case_id": "; ".join(names),
                    "motivo": "",
                }
            )
            seen_jira.add(key)
    for warning in bundle.warnings:
        rows.append({"story": bundle.key, "epic": bundle.key, "scenario": "Aviso", "estado": "aviso", "case_id": "", "motivo": warning})
    if run.error:
        rows.append({"story": bundle.key, "epic": bundle.key, "scenario": "Corrida", "estado": "error", "case_id": "", "motivo": run.error})
    names_by_scenario: dict[str, list[str]] = {}
    for candidate in run.candidates:
        sid = next((r.split("=", 1)[1] for r in candidate.applied_rules if r.startswith("qc-v2:escenario=")), "")
        names_by_scenario.setdefault(sid, []).append(candidate.name)
    errors_by_scenario = {r.scenario_id: r.error for r in run.stage_b if r.error and not r.cases}
    for item in bundle.crns + bundle.covs:
        scenario = None
        if stage_a:
            scenario = next(
                (s for s in stage_a.scenarios if item.id in s.cubre_negocio + s.cubre_tecnico), None
            )
        label = f"{item.id} {item.title}"[:300]
        if stage_a and item.id in stage_a.excluded:
            motivo, explicacion = stage_a.excluded[item.id]
            rows.append({"story": item.source_key, "epic": bundle.key, "scenario": label, "estado": f"excluido: {motivo}", "case_id": "", "motivo": explicacion})
        elif scenario is None:
            rows.append({"story": item.source_key, "epic": bundle.key, "scenario": label, "estado": "pendiente de revisión QC", "case_id": "", "motivo": "sin cobertura en v2 (revisar)"})
        elif scenario.id in errors_by_scenario:
            err = str(errors_by_scenario[scenario.id] or "")
            ia_fail = "error de IA" in err
            rows.append(
                {
                    "story": item.source_key,
                    "epic": bundle.key,
                    "scenario": label,
                    "estado": "no evaluado por error de IA" if ia_fail else "error",
                    "case_id": "",
                    "motivo": "no evaluado por error de IA" if ia_fail else f"{scenario.id}: {err}",
                }
            )
        else:
            rows.append({
                "story": item.source_key,
                "epic": bundle.key,
                "scenario": label,
                "estado": _SITUACION.get(scenario.brecha, "cruce"),
                "case_id": "; ".join(names_by_scenario.get(scenario.id, [])),
                "motivo": f"{scenario.id} · {scenario.titulo}",
            })
    if stage_a:
        for scenario in stage_a.scenarios:
            if scenario.cubre_negocio or scenario.cubre_tecnico:
                continue
            rows.append({
                "story": bundle.key,
                "epic": bundle.key,
                "scenario": f"{scenario.id} {scenario.titulo}",
                "estado": "no afectación" if scenario.es_no_afectacion else _SITUACION.get(scenario.brecha, "implícito"),
                "case_id": "; ".join(names_by_scenario.get(scenario.id, [])),
                "motivo": scenario.descripcion[:300],
            })
    return rows


def run_epic(bundle: EpicBundle, ctx: DeviceContext, chat: ChatFn = chat_json) -> EpicRun:
    started = time.monotonic()
    run = EpicRun(bundle=bundle)
    run.ledger, run.qc_aliases = apply_positive_filter(bundle)
    if not bundle.covs and not bundle.crns:
        run.error = "sin contenido en Jira para generar"
        run.ledger = _ledger(run)
        return run
    try:
        run.stage_a = run_stage_a(bundle, ctx, chat=chat)
    except QuotaExhausted:
        run.ledger.append(
            {
                "story": bundle.key,
                "epic": bundle.key,
                "scenario": "IA",
                "estado": "no evaluado por error de IA",
                "motivo": "no evaluado por error de IA",
                "case_id": "",
            }
        )
        run.ms = int((time.monotonic() - started) * 1000)
        run.ledger = _ledger(run)
        return run
    if (run.stage_a.error or "") == "no evaluado por error de IA":
        run.ledger.append(
            {
                "story": bundle.key,
                "epic": bundle.key,
                "scenario": "IA",
                "estado": "no evaluado por error de IA",
                "motivo": "no evaluado por error de IA",
                "case_id": "",
            }
        )
    elif run.stage_a.error:
        run.error = f"Etapa A: {run.stage_a.error}"
    else:
        run.stage_b = run_stage_b(bundle, ctx, run.stage_a, chat=chat)
        if any((row.error or "") == "no evaluado por error de IA" for row in run.stage_b):
            run.ledger.append(
                {
                    "story": bundle.key,
                    "epic": bundle.key,
                    "scenario": "IA",
                    "estado": "no evaluado por error de IA",
                    "motivo": "no evaluado por error de IA",
                    "case_id": "",
                }
            )
        run_stage_c(run.stage_b)
        by_id = {s.id: s for s in run.stage_a.scenarios}
        for result in run.stage_b:
            scenario = by_id.get(result.scenario_id)
            if scenario is None:
                continue
            run.candidates.extend(_to_candidate(case, scenario, bundle, ctx) for case in result.cases)
        run.candidates = list(run.candidates)
    metas = list(run.stage_a.metas) + [m for r in run.stage_b for m in r.metas]
    run.llm_calls = len(metas)
    run.prompt_tokens = sum(m.prompt_tokens for m in metas)
    run.completion_tokens = sum(m.completion_tokens for m in metas)
    run.ms = int((time.monotonic() - started) * 1000)
    run.ledger = _ledger(run)
    logger.info("qc_v2 %s", run.summary())
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
        except QuotaExhausted:
            run = EpicRun(bundle=bundle)
            run.ledger = [
                {
                    "story": bundle.key,
                    "epic": bundle.key,
                    "scenario": "IA",
                    "estado": "no evaluado por error de IA",
                    "case_id": "",
                    "motivo": "no evaluado por error de IA",
                }
            ]
            runs.append(run)
    return runs


def generate_release_v2(
    *,
    release_id: int,
    release_name: str,
    validation_type: str | None,
    analysis_present: bool,
    release_context: dict[str, Any],
    functionality_keys: list[str],
    stats: GenerationStats,
) -> GenerateCasesResponse:
    """Punto de entrada desde ai_case_engine cuando QC_ENGINE=v2."""
    platform = release_context.get("platform") or (release_context.get("analysis") or {}).get("detected_platform")
    runs = run_epics(functionality_keys, platform)
    candidates = [c for run in runs for c in run.candidates]
    stats.scenario_ledger = [row for run in runs for row in run.ledger]
    details = [run.summary() for run in runs]
    details += [f"{run.bundle.key} aviso: {w}" for run in runs for w in run.bundle.warnings]
    quota_stop = any(
        row.get("estado") == "no evaluado por error de IA"
        for run in runs
        for row in run.ledger
    )
    if quota_stop:
        message = "La IA no evaluó algunos escenarios (error de IA). Se conservan los casos deterministas."
    elif candidates:
        message = f"QcPulse v2 propuso {len(candidates)} caso(s). La IA propone; QC decide."
    else:
        message = "QcPulse v2 no generó casos; revisa los avisos en Escenarios de Jira."
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
