"""Per-scenario LLM rewrite on top of deterministic FASE 7 structure."""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx

from app.config import settings
from app.schemas.case_generation import CandidateStep, CoverageUnit, GeneratedCaseCandidate
from app.services.case_composer import _QUOTED

logger = logging.getLogger(__name__)

_GENERIC = re.compile(
    r"se observa el comportamiento|comportamiento (definido|esperado)|se verifica que\s*$",
    re.I,
)
_INFINITIVE = re.compile(r"^\s*(el usuario\s+)?[a-záéíóúñ]+(ar|er|ir)\b", re.I)
_API = re.compile(r'"/[a-z]|/v\d/|status code|"\d{3}"|[A-Z][a-z]+_[A-Z][A-Za-z]+_', re.I)

_REWRITE_SYSTEM = """Eres analista QC. Recibes un escenario de Jira ya estructurado.
Redacta UN caso ejecutable. No decidas cobertura: no elimines el escenario.
Pasos en infinitivo. Navegación del Background: "Ingresar a A > B" si varios pasos no tienen resultado propio.
Cada paso tiene resultado observable y específico. Prohibido "Se observa el comportamiento…", "Se verifica que…" de relleno.
Textos de UI entre comillas: cópialos literalmente.
Sin APIs, endpoints, status ni nombres de llave en pasos o resultados (van en technical_reference).
Datos de prueba solo de ESTE escenario. No inventes pantallas ni botones que no estén en el Gherkin o su Feature.
Responde JSON: {"name": "...", "precondition": "...", "test_data": "...", "steps": [{"action": "...", "expected_result": "..."}]}
"""


def llm_case_is_valid(
    base: GeneratedCaseCandidate,
    llm: GeneratedCaseCandidate,
    gherkin: str,
    sibling_data: list[str],
) -> bool:
    if not llm.steps:
        return False
    for step in llm.steps:
        if not _INFINITIVE.match(step.action or ""):
            return False
        if _GENERIC.search(step.expected_result or ""):
            return False
        if _API.search(step.expected_result or ""):
            return False
    blob = " ".join(
        [llm.name or "", llm.precondition or "", llm.test_data or ""]
        + [f"{step.action} {step.expected_result}" for step in llm.steps]
    )
    source_blob = " ".join(
        [base.name or ""] + [f"{step.action} {step.expected_result}" for step in base.steps]
    )
    quotes = _QUOTED.findall(source_blob) or _QUOTED.findall((gherkin or "")[:800])
    for quote in quotes:
        if quote.lower() not in blob.lower():
            return False
    own = (base.test_data or "").lower()
    llm_data = (llm.test_data or "").lower()
    for other in sibling_data:
        token = (other or "").strip().lower()
        if len(token) < 4 or token in own:
            continue
        if token in llm_data:
            return False
    return True


def _parse_rewrite(raw: str, base: GeneratedCaseCandidate) -> GeneratedCaseCandidate | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict) and "cases" in payload and payload["cases"]:
        payload = payload["cases"][0]
    if not isinstance(payload, dict):
        return None
    steps: list[CandidateStep] = []
    for index, row in enumerate(payload.get("steps") or [], start=1):
        if not isinstance(row, dict):
            continue
        steps.append(
            CandidateStep(
                step_number=index,
                action=str(row.get("action") or "").strip(),
                expected_result=str(row.get("expected_result") or row.get("expected") or "").strip(),
                covered_unit_ids=list(base.covers or []),
            )
        )
    copy = base.model_copy(deep=True)
    copy.name = str(payload.get("name") or base.name)[:120]
    copy.precondition = str(payload.get("precondition") or base.precondition or "") or None
    copy.test_data = str(payload.get("test_data") or base.test_data or "") or None
    copy.steps = steps
    copy.generation_origin = "llm"
    copy.covers = list(base.covers or [])
    copy.covered_unit_ids = list(base.covers or [])
    copy.technical_reference = base.technical_reference
    copy.variant_table = base.variant_table
    copy.applicability = base.applicability
    copy.related_functionality = base.related_functionality
    copy.related_jira = base.related_jira
    return copy


def _call_llm(user_payload: dict[str, Any], timeout: float) -> str:
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": settings.openai_model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _REWRITE_SYSTEM},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
    if response.status_code != 200:
        raise RuntimeError(f"LLM HTTP {response.status_code}: {response.text[:400]}")
    return response.json()["choices"][0]["message"]["content"]


def _rewrite_one(
    base: GeneratedCaseCandidate,
    unit: CoverageUnit | None,
    story_summary: str,
    background: str,
    sibling_data: list[str],
    timeout: float,
) -> tuple[GeneratedCaseCandidate, dict[str, Any]]:
    gherkin = (unit.body if unit else "") or (base.evidence or "")
    payload = {
        "story_title": story_summary,
        "background": background,
        "gherkin": gherkin[:4000],
        "tables": unit.extra_test_data if unit else base.test_data,
        "template": {
            "name": base.name,
            "precondition": base.precondition,
            "steps": [{"action": step.action, "expected_result": step.expected_result} for step in base.steps],
            "test_data": base.test_data,
            "technical_reference": base.technical_reference,
        },
    }
    meta = {"covers": list(base.covers or []), "attempts": 0, "ok": False, "error": None, "ms": 0}
    started = time.perf_counter()
    last_error = None
    for attempt in range(3):
        meta["attempts"] = attempt + 1
        try:
            raw = _call_llm(payload, timeout)
            llm = _parse_rewrite(raw, base)
            if llm and llm_case_is_valid(base, llm, gherkin, sibling_data):
                meta["ok"] = True
                meta["ms"] = int((time.perf_counter() - started) * 1000)
                return llm, meta
            last_error = "validator"
        except Exception as exc:
            last_error = str(exc)[:200]
            logger.warning("scenario LLM rewrite failed attempt=%s error=%s", attempt + 1, last_error)
    fallback = base.model_copy(deep=True)
    fallback.review_required = True
    if not fallback.steps:
        fallback.applied_rules = list(dict.fromkeys([*(fallback.applied_rules or []), "pendiente-qc:llm"]))
        fallback.applicability_reason = fallback.applicability_reason or "LLM no redactó un caso válido"
    meta["error"] = last_error
    meta["ms"] = int((time.perf_counter() - started) * 1000)
    return fallback, meta


def rewrite_scenario_candidates(
    candidates: list[GeneratedCaseCandidate],
    inventory: list[CoverageUnit],
) -> tuple[list[GeneratedCaseCandidate], list[dict[str, Any]]]:
    if not (settings.openai_api_key or "").strip() or not candidates:
        return candidates, []
    by_id = {unit.coverage_id: unit for unit in inventory}
    by_story: dict[str, list[str]] = {}
    for unit in inventory:
        key = unit.story_key or ""
        if unit.extra_test_data:
            by_story.setdefault(key, []).append(unit.extra_test_data)
    concurrency = max(1, int(getattr(settings, "llm_scenario_concurrency", 8) or 8))
    timeout = float(getattr(settings, "llm_scenario_timeout", 45) or 45)
    rows: list[dict[str, Any]] = []
    out: list[GeneratedCaseCandidate | None] = [None] * len(candidates)

    def work(index: int, candidate: GeneratedCaseCandidate) -> tuple[int, GeneratedCaseCandidate, dict[str, Any]]:
        unit = by_id.get((candidate.covers or [None])[0] or "")
        story = (unit.story_key if unit else "") or (candidate.related_jira or "")
        siblings = [item for item in by_story.get(story, []) if item != (unit.extra_test_data if unit else "")]
        rewritten, meta = _rewrite_one(
            candidate,
            unit,
            (unit.story_summary if unit else "") or (candidate.use_case_title or ""),
            (unit.normal_precondition if unit else "") or (candidate.precondition or ""),
            siblings,
            timeout,
        )
        return index, rewritten, meta

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(work, index, candidate) for index, candidate in enumerate(candidates)]
        for future in as_completed(futures):
            index, rewritten, meta = future.result()
            out[index] = rewritten
            rows.append(meta)
    return [item for item in out if item is not None], rows
