"""Redacción opcional del texto que ya armó Legacy.

Legacy decide el caso, el estado y el número de pasos. Esta capa solo reescribe
el texto si QC_LLM_POLISH=groq y el resultado pasa el mismo chequeo. Si no, el
caso de Legacy se conserva.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.llm.client import LlmError, extract_json_object
from app.schemas.case_generation import GeneratedCaseCandidate, GenerationStats
from app.services.legacy_excel_check import audit_cases

_SYSTEM = (
    "Eres analista QC de Claro video. Reescribe el caso para que un tester lo ejecute "
    "sin dudas, en español, tercera persona, desde la perspectiva del usuario final.\n"
    "Reglas: conserva exactamente el número y el orden de los pasos; no agregues ni quites "
    "botones, pantallas, textos entre «» ni tipos de usuario; no menciones APIs, parámetros, "
    "llaves ni códigos; cada resultado debe describir lo que se ve en pantalla; el título debe "
    "ser 'tipo de usuario + acción + resultado' en máximo 90 caracteres; no inventes datos. "
    "Responde solo el JSON."
)
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_QUOTED = re.compile(r"«([^»]*)»")
logger = logging.getLogger(__name__)
_TPM_LOCK = threading.Lock()
_WINDOW: list[tuple[float, int]] = []


def polish_enabled() -> bool:
    return (getattr(settings, "qc_llm_polish", "off") or "off").strip().lower() == "groq"


def polish_model() -> str:
    return (os.getenv("QC_LLM_MODEL") or getattr(settings, "llm_model", "") or "openai/gpt-oss-20b").strip() or (
        "openai/gpt-oss-20b"
    )


def _groq_key() -> str:
    own = (os.getenv("GROQ_API_KEY") or getattr(settings, "groq_api_key", "") or "").strip()
    if own:
        return own
    if (getattr(settings, "llm_provider", "") or "").strip().lower() == "groq":
        return (getattr(settings, "llm_api_key", "") or "").strip()
    return ""


def _cache_path() -> Path:
    raw = (os.getenv("QC_LLM_CACHE") or "/tmp/qcpulse_polish_cache.json").strip()
    return Path(raw)


def _load_cache() -> dict[str, Any]:
    path = _cache_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _store_cache(cache: dict[str, Any]) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _wait_tokens(estimate: int) -> None:
    limit = max(1, int(getattr(settings, "qc_llm_tpm_limit", 7000) or 7000))
    need = max(1, estimate)
    while True:
        now = time.monotonic()
        with _TPM_LOCK:
            fresh = [(stamp, count) for stamp, count in _WINDOW if now - stamp < 60]
            _WINDOW[:] = fresh
            used = sum(count for _, count in fresh)
            if used + need <= limit or not fresh:
                return
            wait = 60 - (now - fresh[0][0]) + 0.05
        time.sleep(max(wait, 0.2))


def _note_tokens(count: int) -> None:
    if count <= 0:
        return
    with _TPM_LOCK:
        _WINDOW.append((time.monotonic(), count))


def _payload(case: GeneratedCaseCandidate, gherkin: str) -> dict[str, Any]:
    return {
        "caso": {
            "titulo": case.name or "",
            "precondicion": case.precondition or "",
            "pasos": [
                {"accion": step.action or "", "resultado": step.expected_result or ""}
                for step in case.steps
            ],
            "variantes": case.variant_table or "",
        },
        "gherkin": gherkin,
    }


def _bodies(case: GeneratedCaseCandidate, by_id: dict) -> str:
    """El mismo texto que el chequeo compara contra los pasos: el cuerpo del escenario."""
    return "\n".join(
        (by_id[cid].body or "") for cid in (case.covers or []) if cid in by_id
    )


def _gherkin(case: GeneratedCaseCandidate, by_id: dict) -> str:
    parts: list[str] = []
    for cid in case.covers or []:
        unit = by_id.get(cid)
        if unit is None:
            continue
        for piece in (unit.scenario, unit.feature_background, unit.body):
            text = (piece or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts)[:12000]


def _hash(payload: dict[str, Any]) -> str:
    blob = json.dumps({"model": polish_model(), "entrada": payload}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _quotes(text: str) -> list[str]:
    return _QUOTED.findall(text or "")


def _variant_lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _left(line: str) -> str:
    return line.split("|", 1)[0].strip().lower()


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _parse_case(raw: dict[str, Any]) -> dict[str, Any]:
    body = raw.get("caso") if isinstance(raw.get("caso"), dict) else raw
    if not isinstance(body, dict):
        raise ValueError("el JSON no trae el caso")
    title = body.get("titulo")
    steps = body.get("pasos")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("falta el título")
    if not isinstance(steps, list):
        raise ValueError("faltan los pasos")
    parsed: list[dict[str, str]] = []
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("un paso no es un objeto")
        action = step.get("accion", step.get("acción"))
        result = step.get("resultado")
        if not isinstance(action, str) or not isinstance(result, str):
            raise ValueError("un paso no trae acción y resultado")
        parsed.append({"accion": action.strip(), "resultado": result.strip()})
    return {
        "titulo": title.strip(),
        "precondicion": _as_text(body.get("precondicion")),
        "pasos": parsed,
        "variantes": _as_text(body.get("variantes")),
    }


def _validate(
    original: dict[str, Any],
    rewritten: dict[str, Any],
    gherkin: str,
    *,
    legacy_name: str,
    scenario: str,
) -> str:
    caso = original["caso"]
    if len(rewritten["pasos"]) != len(caso["pasos"]):
        return "cambió el número de pasos"
    if len(rewritten["titulo"]) > 90:
        return "el título supera 90 caracteres"
    old_lines = _variant_lines(caso["variantes"])
    new_lines = _variant_lines(rewritten["variantes"])
    if len(old_lines) != len(new_lines):
        return "cambiaron las variantes"
    for old, new in zip(old_lines, new_lines):
        if _left(old) != _left(new):
            return "cambió un tipo de usuario en las variantes"
    source = json.dumps(original, ensure_ascii=False)
    for quote in _quotes(
        " ".join(
            [
                rewritten["titulo"],
                rewritten["precondicion"],
                rewritten["variantes"],
                *(step["accion"] for step in rewritten["pasos"]),
                *(step["resultado"] for step in rewritten["pasos"]),
            ]
        )
    ):
        if f"«{quote}»" not in source:
            return f"el texto «{quote}» no está en la entrada"
    steps = "\n".join(f"{index}. {step['accion']}" for index, step in enumerate(rewritten["pasos"], start=1))
    results = "\n".join(f"{index}. {step['resultado']}" for index, step in enumerate(rewritten["pasos"], start=1))
    row = {
        "name": rewritten["titulo"],
        "legacy_name": legacy_name,
        "steps": steps,
        "results": results,
        "precondition": rewritten["precondicion"],
        "scenario": scenario,
        "variants": rewritten["variantes"],
    }
    issues = audit_cases([row], {rewritten["titulo"]: gherkin, legacy_name: gherkin})
    for key, found in issues.items():
        if found:
            return found[0] if key == "then_no_reflejado" else key.replace("_", " ")
    return ""


def _post(payload: dict[str, Any], key: str) -> httpx.Response:
    timeout = float(getattr(settings, "llm_timeout_seconds", 60) or 60)
    with httpx.Client(timeout=timeout) as client:
        return client.post(
            _GROQ_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )


def _retry_after(response: httpx.Response) -> float:
    raw = response.headers.get("Retry-After")
    if not raw:
        return 2.0
    try:
        return min(max(float(raw), 0.2), 60.0)
    except ValueError:
        return 2.0


def _call(messages: list[dict[str, str]], key: str) -> tuple[str, int]:
    """Una llamada. Ante 429/413 espera y reintenta. No aborta la corrida."""
    model = polish_model()
    estimate = max(200, sum(len(item.get("content") or "") for item in messages) // 3)
    use_temp = True
    use_json = True
    completion_cap = int(getattr(settings, "qc_v2_max_completion_tokens", 4096) or 4096)
    last = "sin respuesta"
    for _attempt in range(6):
        _wait_tokens(estimate)
        body: dict[str, Any] = {"model": model, "messages": messages, "max_completion_tokens": completion_cap}
        if use_temp:
            body["temperature"] = 0
        if use_json:
            body["response_format"] = {"type": "json_object"}
        try:
            response = _post(body, key)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last = exc.__class__.__name__
            time.sleep(1.5)
            continue
        if response.status_code == 400 and use_temp and "temperature" in response.text.lower():
            use_temp = False
            continue
        if response.status_code == 400 and use_json and "response_format" in response.text.lower():
            use_json = False
            continue
        if response.status_code == 400 and "json_validate_failed" in response.text.lower() and completion_cap < 8192:
            completion_cap = 8192
            continue
        if response.status_code in (413, 429) or response.status_code >= 500:
            time.sleep(_retry_after(response))
            last = f"HTTP {response.status_code}"
            continue
        if response.status_code != 200:
            detail = response.text[:300]
            if key:
                detail = detail.replace(key, "[redacted]")
            raise RuntimeError(f"HTTP {response.status_code}: {detail}")
        try:
            data = response.json()
        except json.JSONDecodeError:
            return "", 0
        usage = data.get("usage") or {}
        tokens = int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)
        _note_tokens(tokens or estimate)
        content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        return content, tokens
    raise TimeoutError(last)


def _apply(case: GeneratedCaseCandidate, rewritten: dict[str, Any], original_name: str) -> None:
    case.legacy_name = original_name
    case.name = rewritten["titulo"]
    case.precondition = rewritten["precondicion"] or None
    case.variant_table = rewritten["variantes"] or None
    for step, item in zip(case.steps, rewritten["pasos"]):
        step.action = item["accion"]
        step.expected_result = item["resultado"]
    case.redaccion = "IA"


def _retarget(stats: GenerationStats, old: str, new: str) -> None:
    if not old or old == new:
        return
    for row in stats.scenario_ledger:
        if str(row.get("case_id") or "") == old:
            row["case_id"] = new


def _diffs(case_id: str, before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pairs = [
        ("Título", before["titulo"], after["titulo"]),
        ("Precondición", before["precondicion"], after["precondicion"]),
        ("Variantes", before["variantes"], after["variantes"]),
    ]
    for index, (old, new) in enumerate(zip(before["pasos"], after["pasos"]), start=1):
        pairs.append((f"Paso {index} acción", old["accion"], new["accion"]))
        pairs.append((f"Paso {index} resultado", old["resultado"], new["resultado"]))
    for field, old, new in pairs:
        if (old or "") != (new or ""):
            rows.append({"id": case_id, "campo": field, "legacy": old or "", "ia": new or ""})
    return rows


def polish_legacy_cases(
    cases: list[GeneratedCaseCandidate],
    inventory: list,
    stats: GenerationStats | None = None,
) -> None:
    """Reescribe el texto. No cambia la cobertura ni el número de pasos."""
    if not polish_enabled():
        return
    stats = stats or GenerationStats()
    key = _groq_key()
    by_id = {unit.coverage_id: unit for unit in inventory}
    retries = max(0, int(getattr(settings, "qc_llm_polish_retries", 1) or 1))
    cache = _load_cache()
    for case in cases:
        if not case.steps:
            continue
        gherkin = _gherkin(case, by_id)
        bodies = _bodies(case, by_id)
        payload = _payload(case, gherkin)
        digest = _hash(payload)
        original_name = case.name or ""
        scenario = next(
            (
                unit.scenario
                for cid in (case.covers or [])
                if (unit := by_id.get(cid)) is not None and unit.scenario
            ),
            original_name,
        )
        cached = cache.get(digest)
        if isinstance(cached, dict) and cached.get("status") in {"ia", "fallback"}:
            _finish_cached(case, cached, original_name, stats)
            logger.info("polish cache %s %s", cached.get("status"), original_name[:80])
            continue
        if not key:
            _fallback(case, stats, "sin GROQ_API_KEY", original_name, digest, cache, None)
            continue
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        reason = ""
        rewritten: dict[str, Any] | None = None
        spent = 0
        for attempt in range(retries + 1):
            try:
                content, tokens = _call(messages, key)
            except Exception as exc:
                reason = str(exc) or exc.__class__.__name__
                break
            spent += tokens
            if not content:
                reason = "sin respuesta del modelo"
                break
            try:
                parsed = extract_json_object(content)
                rewritten = _parse_case(parsed)
                reason = _validate(
                    payload, rewritten, bodies, legacy_name=original_name, scenario=scenario
                )
            except (LlmError, ValueError) as exc:
                rewritten = None
                reason = str(exc)
            if not reason and rewritten is not None:
                break
            if attempt >= retries:
                rewritten = None
                break
            messages = [
                *messages,
                {"role": "assistant", "content": content[:4000]},
                {
                    "role": "user",
                    "content": (
                        f"El JSON no pasó la validación: {reason}. "
                        "Corrige solo el texto y responde el JSON, con los mismos pasos y variantes."
                    ),
                },
            ]
        stats.polish_tokens += spent
        logger.info("polish %s %s", "ia" if not reason and rewritten else f"fallback: {reason}", original_name[:80])
        if reason or rewritten is None:
            _fallback(case, stats, reason or "respuesta inválida", original_name, digest, cache, spent)
            continue
        before = payload["caso"]
        _apply(case, rewritten, original_name)
        _retarget(stats, original_name, case.name)
        stats.polish_ia += 1
        stats.polish_comparison.extend(_diffs(case.name, before, rewritten))
        cache[digest] = {"status": "ia", "case": rewritten, "before": before, "tokens": spent}
        _store_cache(cache)


def _finish_cached(
    case: GeneratedCaseCandidate,
    cached: dict[str, Any],
    original_name: str,
    stats: GenerationStats,
) -> None:
    if cached.get("status") == "ia" and isinstance(cached.get("case"), dict):
        _apply(case, cached["case"], original_name)
        _retarget(stats, original_name, case.name)
        stats.polish_ia += 1
        before = cached.get("before")
        if isinstance(before, dict):
            stats.polish_comparison.extend(_diffs(case.name, before, cached["case"]))
        return
    case.redaccion = f"Legacy (fallback: {_short_reason(str(cached.get('reason') or ''))})"
    stats.polish_fallback += 1
    stats.polish_comparison.append(
        {
            "id": original_name,
            "campo": "Fallback",
            "legacy": original_name,
            "ia": _short_reason(str(cached.get("reason") or "")),
        }
    )


def _short_reason(reason: str) -> str:
    text = " ".join((reason or "respuesta inválida").split())
    if "json_validate_failed" in text:
        return "el modelo no devolvió JSON válido"
    return text[:180]


def _fallback(
    case: GeneratedCaseCandidate,
    stats: GenerationStats,
    reason: str,
    original_name: str,
    digest: str,
    cache: dict[str, Any],
    tokens: int | None,
) -> None:
    short = _short_reason(reason)
    case.redaccion = f"Legacy (fallback: {short})"
    stats.polish_fallback += 1
    stats.polish_comparison.append(
        {"id": original_name, "campo": "Fallback", "legacy": original_name, "ia": short}
    )
    cache[digest] = {"status": "fallback", "reason": short, "tokens": tokens or 0}
    _store_cache(cache)
