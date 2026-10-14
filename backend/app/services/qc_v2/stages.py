"""Etapas A (modelado), B (diseño de casos) y C (validación estructural + complejidad)."""

from __future__ import annotations

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.config import settings
from app.services.qc_v2.collect import EpicBundle
from app.services.qc_v2.context import DeviceContext
from app.services.qc_v2.llm import LlmError, LlmMeta, QuotaExhausted, chat_json

logger = logging.getLogger(__name__)

_PROMPTS = Path(__file__).parent / "prompts"
EXCLUSION_REASONS = {"telemetria", "tecnico_interno", "accion_desarrollo", "medicion_tecnica", "no_reproducible"}
BRECHAS = {"ninguna", "sin_tecnico", "sin_negocio", "implicito"}
TIPOS = {"HPP", "HPA", "TTF", "ERG", "E2E"}

ChatFn = Callable[..., tuple[dict[str, Any], LlmMeta]]


def load_prompt(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8")


def _temperature() -> float | None:
    return settings.qc_v2_temperature


def _reasoning(stage: str) -> dict[str, str]:
    """Esfuerzo de razonamiento por etapa (low/medium/high). Vacío = no se envía."""
    value = settings.qc_v2_reasoning_a if stage == "a" else settings.qc_v2_reasoning_b
    return {"reasoning_effort": value} if value else {}


# ================================================================ Etapa A


@dataclass
class Scenario:
    id: str
    titulo: str
    descripcion: str
    condiciones: list[str]
    cubre_negocio: list[str]
    cubre_tecnico: list[str]
    brecha: str
    es_no_afectacion: bool = False


@dataclass
class StageAResult:
    resumen: str = ""
    scenarios: list[Scenario] = field(default_factory=list)
    excluded: dict[str, tuple[str, str]] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    metas: list[LlmMeta] = field(default_factory=list)
    error: str | None = None


def stage_a_user_prompt(bundle: EpicBundle, ctx: DeviceContext) -> str:
    lines = [f"ÉPICA TÉCNICA: {bundle.key} — {bundle.summary}", ctx.as_text(), "", "=== USER STORIES ==="]
    if not bundle.user_stories:
        lines.append("Sin User Story: trabaja solo con las Technical Stories (no hay CRN).")
    for story in bundle.user_stories:
        lines.append(f"--- {story.key} — {story.summary}")
        header = " · ".join(
            part
            for part in (
                f"Yo como: {story.yo_como}" if story.yo_como else "",
                f"Quiero: {story.quiero}" if story.quiero else "",
                f"Para: {story.para}" if story.para else "",
                f"Tipo de usuario: {story.tipo_usuario}" if story.tipo_usuario else "",
            )
            if part
        )
        if header:
            lines.append(header)
        if story.exito:
            lines.append(f"Criterios de éxito: {story.exito}")
        for item in story.criteria:
            lines.append(f"{item.id} | {item.text}")
        lines.append("")
    lines.append("=== TECHNICAL STORIES ===")
    for story in bundle.technical_stories:
        lines.append(f"--- {story.key} — {story.summary}")
        if story.context:
            lines.append(f"[Contexto / Background]\n{story.context}")
        for item in story.scenarios:
            lines.append(f"{item.id} | {item.title}\n{item.text}")
        lines.append("")
    return "\n".join(lines)


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def parse_stage_a(payload: dict[str, Any], bundle: EpicBundle) -> StageAResult:
    valid_ids = {item.id for item in bundle.crns + bundle.covs}
    result = StageAResult(resumen=str(payload.get("resumen_funcionalidad") or "").strip())
    seen_ids: set[str] = set()
    for index, raw in enumerate(payload.get("escenarios") or [], start=1):
        if not isinstance(raw, dict):
            continue
        titulo = str(raw.get("titulo") or "").strip()
        if not titulo:
            continue
        sid = str(raw.get("id") or "").strip() or f"ESC-{index:02d}"
        if sid in seen_ids:
            sid = f"ESC-{index:02d}"
        seen_ids.add(sid)
        crn = [i for i in _str_list(raw.get("cubre_negocio")) if i in valid_ids and i.startswith("CRN")]
        cov = [i for i in _str_list(raw.get("cubre_tecnico")) if i in valid_ids and i.startswith("COV")]
        brecha = str(raw.get("brecha") or "").strip().lower()
        if brecha not in BRECHAS:
            brecha = "ninguna" if crn and cov else ("sin_tecnico" if crn else ("sin_negocio" if cov else "implicito"))
        result.scenarios.append(
            Scenario(
                id=sid,
                titulo=titulo,
                descripcion=str(raw.get("descripcion") or "").strip(),
                condiciones=_str_list(raw.get("condiciones")),
                cubre_negocio=crn,
                cubre_tecnico=cov,
                brecha=brecha,
                es_no_afectacion=bool(raw.get("es_no_afectacion")),
            )
        )
    for raw in payload.get("excluidos") or []:
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id") or "").strip()
        motivo = str(raw.get("motivo") or "").strip().lower()
        if item_id in valid_ids:
            result.excluded[item_id] = (
                motivo if motivo in EXCLUSION_REASONS else "no_reproducible",
                str(raw.get("explicacion") or "").strip(),
            )
    covered = {i for s in result.scenarios for i in s.cubre_negocio + s.cubre_tecnico}
    result.missing = sorted(valid_ids - covered - set(result.excluded))
    return result


def run_stage_a(bundle: EpicBundle, ctx: DeviceContext, chat: ChatFn = chat_json) -> StageAResult:
    messages = [
        {"role": "system", "content": load_prompt("etapa_a.md")},
        {"role": "user", "content": stage_a_user_prompt(bundle, ctx)},
    ]
    model = settings.qc_v2_model_a
    try:
        payload, meta = chat(messages, model=model, temperature=_temperature(), **_reasoning("a"))
    except LlmError as exc:
        return StageAResult(error=str(exc))
    result = parse_stage_a(payload, bundle)
    result.metas.append(meta)
    if result.missing:
        retry = messages + [
            {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
            {
                "role": "user",
                "content": (
                    "Faltan estos IDs en cubre_negocio/cubre_tecnico o en excluidos: "
                    + ", ".join(result.missing)
                    + ". Devuelve el JSON completo corregido, sin perder lo anterior."
                ),
            },
        ]
        try:
            payload2, meta2 = chat(retry, model=model, temperature=_temperature(), **_reasoning("a"))
            second = parse_stage_a(payload2, bundle)
            second.metas = result.metas + [meta2]
            if len(second.missing) <= len(result.missing) and second.scenarios:
                result = second
            else:
                result.metas.append(meta2)
        except LlmError as exc:
            logger.warning("qc_v2 etapa A reintento falló: %s", exc)
    return result


# ================================================================ Etapa B


@dataclass
class DesignedCase:
    scenario_id: str
    titulo: str
    tipo: str
    prioridad: str
    precondiciones: list[str]
    pasos: list[dict[str, str]]
    variantes: list[dict[str, str]]
    referencia_tecnica: str | None
    riesgo: str
    confianza: str
    review_reasons: list[str] = field(default_factory=list)
    complejidad: str = "MEDIA"


@dataclass
class StageBResult:
    scenario_id: str
    cases: list[DesignedCase] = field(default_factory=list)
    metas: list[LlmMeta] = field(default_factory=list)
    error: str | None = None


def stage_b_user_prompt(
    bundle: EpicBundle,
    ctx: DeviceContext,
    scenario: Scenario,
    all_scenarios: list[Scenario],
    resumen: str,
) -> str:
    lines = [
        f"ÉPICA TÉCNICA: {bundle.key} — {bundle.summary}",
        f"QUÉ CAMBIA PARA EL USUARIO: {resumen}" if resumen else "",
        ctx.as_text(),
        "",
        f"=== ESCENARIO A DISEÑAR: {scenario.id} — {scenario.titulo} ===",
        scenario.descripcion,
    ]
    if scenario.condiciones:
        lines.append("Condiciones: " + "; ".join(scenario.condiciones))
    if scenario.es_no_afectacion:
        lines.append("Es un escenario de NO AFECTACIÓN del componente tocado.")
    us_headers: dict[str, str] = {}
    for story in bundle.user_stories:
        us_headers[story.key] = f"{story.key}: Yo como {story.yo_como} · Quiero {story.quiero} · Para {story.para}"
    for item_id in scenario.cubre_negocio + scenario.cubre_tecnico:
        item = bundle.item(item_id)
        if item is None:
            continue
        origin = us_headers.get(item.source_key, item.source_key)
        lines.append(f"\n[{item.id} · {origin}]\n{item.text}")
    contexts = {
        story.key: story.context
        for story in bundle.technical_stories
        if story.context and any(i.source_key == story.key for i in (bundle.item(c) for c in scenario.cubre_tecnico) if i)
    }
    for key, context in contexts.items():
        lines.append(f"\n[Contexto de {key}]\n{context}")
    others = [f"- {s.id}: {s.titulo}" for s in all_scenarios if s.id != scenario.id]
    if others:
        lines.append("\n=== OTROS ESCENARIOS DE LA ÉPICA (no los dupliques) ===")
        lines.extend(others)
    return "\n".join(line for line in lines if line is not None)


def parse_stage_b(payload: dict[str, Any], scenario_id: str) -> list[DesignedCase]:
    cases: list[DesignedCase] = []
    for raw in payload.get("casos") or []:
        if not isinstance(raw, dict):
            continue
        titulo = str(raw.get("titulo") or "").strip()
        pasos = [
            {
                "accion": str(step.get("accion") or "").strip(),
                "resultado_esperado": str(step.get("resultado_esperado") or "").strip(),
            }
            for step in raw.get("pasos") or []
            if isinstance(step, dict)
        ]
        pasos = [step for step in pasos if step["accion"] or step["resultado_esperado"]]
        if not titulo or not pasos:
            continue
        tipo = str(raw.get("tipo") or "").strip().upper()
        prioridad = str(raw.get("prioridad") or "").strip().lower()
        variantes = [
            {
                "condicion": str(v.get("condicion") or "").strip(),
                "resultado_esperado": str(v.get("resultado_esperado") or "").strip(),
            }
            for v in raw.get("variantes") or []
            if isinstance(v, dict) and str(v.get("condicion") or "").strip()
        ]
        referencia = raw.get("referencia_tecnica")
        cases.append(
            DesignedCase(
                scenario_id=scenario_id,
                titulo=titulo,
                tipo=tipo if tipo in TIPOS else "HPP",
                prioridad="BLOCKER" if prioridad.startswith("block") else "CRITICAL",
                precondiciones=_str_list(raw.get("precondiciones")),
                pasos=pasos,
                variantes=variantes,
                referencia_tecnica=str(referencia).strip() if referencia else None,
                riesgo=str(raw.get("riesgo") or "").strip(),
                confianza=str(raw.get("confianza") or "media").strip().lower(),
            )
        )
    return cases


def _design_one(
    bundle: EpicBundle,
    ctx: DeviceContext,
    scenario: Scenario,
    all_scenarios: list[Scenario],
    resumen: str,
    chat: ChatFn,
) -> StageBResult:
    messages = [
        {"role": "system", "content": load_prompt("etapa_b.md")},
        {"role": "user", "content": stage_b_user_prompt(bundle, ctx, scenario, all_scenarios, resumen)},
    ]
    result = StageBResult(scenario_id=scenario.id)
    for attempt in range(2):
        try:
            payload, meta = chat(messages, model=settings.qc_v2_model_b, temperature=_temperature(), **_reasoning("b"))
        except LlmError as exc:
            result.error = str(exc)
            continue
        result.metas.append(meta)
        cases = parse_stage_b(payload, scenario.id)
        if cases:
            result.cases = cases
            result.error = None
            return result
        result.error = "la respuesta no trajo casos válidos"
    return result


def run_stage_b(
    bundle: EpicBundle,
    ctx: DeviceContext,
    stage_a: StageAResult,
    chat: ChatFn = chat_json,
) -> list[StageBResult]:
    scenarios = stage_a.scenarios
    if not scenarios:
        return []
    workers = max(1, min(settings.qc_v2_concurrency, len(scenarios)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_design_one, bundle, ctx, s, scenarios, stage_a.resumen, chat) for s in scenarios
        ]
        results: list[StageBResult] = []
        quota: QuotaExhausted | None = None
        for future in futures:
            try:
                results.append(future.result())
            except QuotaExhausted as exc:
                quota = exc
        if quota is not None:
            raise quota
    return results


# ================================================================ Etapa C

_EMPTY_QUOTES = re.compile(r"[\"“”«]\s*[\"“”»]|<\s*>")


def complexity(case: DesignedCase) -> str:
    steps = len(case.pasos)
    if case.tipo == "E2E" or steps >= 5 or len(case.variantes) > 3:
        return "ALTA"
    if steps <= 3 and not case.variantes and len(case.precondiciones) <= 3:
        return "BAJA"
    return "MEDIA"


def validate_case(case: DesignedCase) -> list[str]:
    reasons: list[str] = []
    if not 3 <= len(case.pasos) <= 6:
        reasons.append(f"{len(case.pasos)} pasos (esperado 3 a 6)")
    if any(not s["accion"] or not s["resultado_esperado"] for s in case.pasos):
        reasons.append("paso sin acción o sin resultado esperado")
    if not case.precondiciones:
        reasons.append("sin precondiciones")
    texts = [case.titulo] + [s["accion"] + " " + s["resultado_esperado"] for s in case.pasos]
    if any(_EMPTY_QUOTES.search(text) for text in texts):
        reasons.append("texto entre comillas vacío")
    return reasons


def run_stage_c(results: list[StageBResult]) -> None:
    for result in results:
        for case in result.cases:
            case.review_reasons = validate_case(case)
            case.complejidad = complexity(case)
