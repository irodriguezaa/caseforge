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


def fallback_model() -> str:
    return (os.getenv("QC_LLM_FALLBACK_MODEL") or getattr(settings, "qc_llm_fallback_model", "") or "").strip()


def _groq_key() -> str:
    own = (os.getenv("GROQ_API_KEY") or getattr(settings, "groq_api_key", "") or "").strip()
    if own:
        return own
    if (getattr(settings, "llm_provider", "") or "").strip().lower() == "groq":
        return (getattr(settings, "llm_api_key", "") or "").strip()
    return ""


def _cache_path() -> Path:
    raw = (os.getenv("QC_LLM_CACHE") or "").strip()
    if raw:
        return Path(raw)
    preferred = Path("/app/data/polish_cache.json")
    try:
        preferred.parent.mkdir(parents=True, exist_ok=True)
        return preferred
    except OSError:
        return Path("/tmp/qcpulse_polish_cache.json")


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


def _hash(payload: dict[str, Any], model: str | None = None) -> str:
    blob = json.dumps(
        {"model": model or polish_model(), "entrada": payload},
        ensure_ascii=False,
        sort_keys=True,
    )
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


class GroqDailyLimit(Exception):
    """Groq cortó por el cupo del día. No se reintenta en bucle."""

    def __init__(self, retry_after: float, model: str) -> None:
        self.retry_after = retry_after
        self.model = model
        super().__init__(f"límite diario de Groq ({model})")


def _retry_after_seconds(response: httpx.Response, *, cap: float) -> float:
    raw = (response.headers.get("Retry-After") or "").strip()
    if not raw:
        return 2.0
    try:
        value = float(raw)
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime

            moment = parsedate_to_datetime(raw)
            value = moment.timestamp() - time.time()
        except (TypeError, ValueError, OSError):
            value = 2.0
    return min(max(value, 0.2), cap)


def _is_daily_limit(response: httpx.Response) -> bool:
    if response.status_code != 429:
        return False
    retry = (response.headers.get("x-should-retry") or "").strip().lower()
    if retry == "false":
        return True
    text = (response.text or "").lower()
    return "tokens per day" in text or "tpd" in text


def _log_groq(response: httpx.Response, model: str) -> None:
    if response.status_code == 429 and _is_daily_limit(response):
        kind = "TPD"
    elif response.status_code == 429:
        kind = "TPM"
    else:
        kind = "-"
    logger.warning(
        "groq HTTP %s modelo=%s limite=%s retry_after=%s",
        response.status_code,
        model,
        kind,
        response.headers.get("Retry-After") or "-",
    )


def _call(messages: list[dict[str, str]], key: str, model: str | None = None) -> tuple[str, int]:
    """Una llamada. 429 TPM espera y sigue. 429 TPD no entra al bucle."""
    model = (model or polish_model()).strip()
    estimate = max(200, sum(len(item.get("content") or "") for item in messages) // 3)
    use_temp = True
    use_json = True
    use_reasoning = "gpt-oss" in model
    completion_cap = 1500
    last = "sin respuesta"
    for _attempt in range(6):
        _wait_tokens(estimate)
        body: dict[str, Any] = {"model": model, "messages": messages, "max_completion_tokens": completion_cap}
        if use_temp:
            body["temperature"] = 0
        if use_json:
            body["response_format"] = {"type": "json_object"}
        if use_reasoning:
            body["reasoning_effort"] = "low"
        try:
            response = _post(body, key)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last = exc.__class__.__name__
            logger.warning("groq HTTP transporte modelo=%s limite=- retry_after=- error=%s", model, exc.__class__.__name__)
            time.sleep(1.5)
            continue
        if response.status_code != 200:
            _log_groq(response, model)
        if _is_daily_limit(response):
            raise GroqDailyLimit(_retry_after_seconds(response, cap=86400), model)
        if response.status_code == 400 and use_temp and "temperature" in response.text.lower():
            use_temp = False
            continue
        if response.status_code == 400 and use_json and "response_format" in response.text.lower():
            use_json = False
            continue
        if response.status_code == 400 and use_reasoning and "reasoning" in response.text.lower():
            use_reasoning = False
            continue
        if response.status_code in (413, 429) or response.status_code >= 500:
            time.sleep(_retry_after_seconds(response, cap=60))
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


def _is_transient(reason: str) -> bool:
    text = (reason or "").lower()
    markers = (
        "429",
        "tpd",
        "tpm",
        "tokens per day",
        "tokens per minute",
        "timeout",
        "timed out",
        "http 5",
        "http 413",
        "http 408",
        "transport",
        "connect",
        "network",
        "remoteprotocol",
        "sin groq_api_key",
        "sin respuesta",
        "límite diario",
    )
    return any(marker in text for marker in markers)


def _polish_one(
    case: GeneratedCaseCandidate,
    payload: dict[str, Any],
    bodies: str,
    scenario: str,
    stats: GenerationStats,
    *,
    key: str,
    retries: int,
    cache: dict[str, Any],
    model: str | None = None,
    case_id: str = "",
    release_id: str | None = None,
) -> str:
    """Reescribe un caso. Devuelve el modelo que respondió. GroqDailyLimit se propaga."""
    current = (model or polish_model()).strip()
    original_name = case.name or ""
    label = case_id or original_name
    switched: set[str] = set()
    while True:
        digest = _hash(payload, current)
        cached = cache.get(digest)
        if isinstance(cached, dict) and cached.get("status") in {"ia", "fallback"}:
            _finish_cached(case, cached, original_name, stats)
            if cached.get("status") == "ia":
                logger.info("polish ia %s", label)
            else:
                logger.info("polish fallback %s: %s", label, _short_reason(str(cached.get("reason") or "")))
            return current
        if not key:
            _fallback(case, stats, "sin GROQ_API_KEY", original_name, digest, cache, None, label=label)
            return current
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ]
        reason = ""
        rewritten: dict[str, Any] | None = None
        spent = 0
        try:
            for attempt in range(retries + 1):
                try:
                    content, tokens = _call(messages, key, current)
                except GroqDailyLimit:
                    raise
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
        except GroqDailyLimit as exc:
            alt = fallback_model()
            if alt and alt != current and alt not in switched:
                switched.add(current)
                logger.warning("groq límite diario modelo=%s; sigue con %s", current, alt)
                if release_id is not None:
                    _set_job_model(release_id, alt)
                current = alt
                continue
            raise exc
        stats.polish_tokens += spent
        if reason or rewritten is None:
            _fallback(
                case,
                stats,
                reason or "respuesta inválida",
                original_name,
                digest,
                cache,
                spent,
                label=label,
            )
            return current
        before = payload["caso"]
        _apply(case, rewritten, original_name)
        _retarget(stats, original_name, case.name)
        stats.polish_ia += 1
        stats.polish_comparison.extend(_diffs(case.name, before, rewritten))
        cache[digest] = {"status": "ia", "case": rewritten, "before": before, "tokens": spent}
        _store_cache(cache)
        logger.info("polish ia %s", label)
        return current


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
        scenario = next(
            (
                unit.scenario
                for cid in (case.covers or [])
                if (unit := by_id.get(cid)) is not None and unit.scenario
            ),
            case.name or "",
        )
        _polish_one(
            case,
            payload,
            bodies,
            scenario,
            stats,
            key=key,
            retries=retries,
            cache=cache,
            model=polish_model(),
            case_id=case.name or "",
        )


def collect_polish_work(cases: list[GeneratedCaseCandidate], inventory: list) -> list[dict[str, Any]]:
    """Arma la cola sin llamar al modelo. Un ítem por candidato, en el mismo orden."""
    if not polish_enabled():
        return []
    by_id = {unit.coverage_id: unit for unit in inventory}
    work: list[dict[str, Any]] = []
    for case in cases:
        if not case.steps:
            work.append({"skip": True})
            continue
        gherkin = _gherkin(case, by_id)
        scenario = next(
            (
                unit.scenario
                for cid in (case.covers or [])
                if (unit := by_id.get(cid)) is not None and unit.scenario
            ),
            case.name or "",
        )
        work.append(
            {
                "skip": False,
                "epic": (case.related_functionality or "")[:250],
                "original_name": case.name or "",
                "payload": _payload(case, gherkin),
                "bodies": _bodies(case, by_id),
                "scenario": scenario,
            }
        )
    return work


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
    *,
    label: str = "",
) -> None:
    short = _short_reason(reason)
    case.redaccion = f"Legacy (fallback: {short})"
    stats.polish_fallback += 1
    stats.polish_comparison.append(
        {"id": original_name, "campo": "Fallback", "legacy": original_name, "ia": short}
    )
    logger.info("polish fallback %s: %s", label or original_name, short)
    if _is_transient(reason):
        return
    cache[digest] = {"status": "fallback", "reason": short, "tokens": tokens or 0}
    _store_cache(cache)


_JOB_LOCK = threading.Condition()
_THREAD: threading.Thread | None = None
_CANCELLED: set[str] = set()
_EPOCH: dict[str, int] = {}
_REDACCION_LINE = re.compile(r"\n?Redacción:.*\Z", re.IGNORECASE | re.DOTALL)


def _jobs_path() -> Path:
    return _cache_path().with_name("polish_jobs.json")


def _load_jobs() -> dict[str, Any]:
    path = _jobs_path()
    if not path.exists():
        return {"releases": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"releases": {}}
    if not isinstance(data, dict):
        return {"releases": {}}
    data.setdefault("releases", {})
    return data


def _store_jobs(data: dict[str, Any]) -> None:
    path = _jobs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def clear_polish_job(release_id: int) -> None:
    key = str(release_id)
    with _JOB_LOCK:
        _CANCELLED.add(key)
        _EPOCH[key] = _EPOCH.get(key, 0) + 1
        data = _load_jobs()
        data.get("releases", {}).pop(key, None)
        _store_jobs(data)


def _counts(items: list[dict[str, Any]]) -> tuple[int, int, int]:
    done = sum(1 for item in items if item.get("done"))
    fallbacks = sum(1 for item in items if item.get("fallback"))
    return done, len(items), fallbacks


def _pause_label(paused_until: float | None) -> str:
    moment = float(paused_until or 0)
    if moment <= time.time():
        return ""
    hhmm = time.strftime("%H:%M", time.localtime(moment))
    return f"pausada – límite diario de Groq (reanuda {hhmm})"


def _label(items: list[dict[str, Any]], running: bool, paused_until: float | None = None) -> str:
    done, total, fallbacks = _counts(items)
    if total == 0:
        return ""
    if done < total:
        paused = _pause_label(paused_until)
        if paused:
            return paused
        return f"en curso ({done}/{total})" if running else "pendiente"
    if fallbacks:
        return "con fallbacks"
    return "lista"


def polish_status(release_id: int) -> dict[str, Any]:
    data = _load_jobs()
    job = (data.get("releases") or {}).get(str(release_id)) or {}
    items = list(job.get("items") or [])
    done, total, fallbacks = _counts(items)
    paused_until = job.get("paused_until")
    running = bool(job.get("running")) and done < total
    epics: dict[str, str] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(str(item.get("epic") or "—"), []).append(item)
    for epic, rows in grouped.items():
        epic_pending = any(not row.get("done") for row in rows)
        epic_running = running and epic_pending
        epics[epic] = _label(rows, epic_running, paused_until if epic_pending else None)
    models = [str(model) for model in (job.get("models") or []) if model]
    return {
        "enabled": polish_enabled(),
        "label": _label(items, running, paused_until) if polish_enabled() or items else "",
        "model": ", ".join(models),
        "done": done,
        "total": total,
        "fallbacks": fallbacks,
        "ia": sum(1 for item in items if item.get("done") and not item.get("fallback")),
        "tokens": int(job.get("tokens") or 0),
        "epics": epics,
    }


def polish_export_overlay(release_id: int, coverage: dict[str, Any] | None) -> dict[str, Any] | None:
    """El Excel usa lo ya guardado y, si el job ya reescribió algo, la comparación de ese momento."""
    data = _load_jobs()
    job = (data.get("releases") or {}).get(str(release_id)) or {}
    items = [item for item in (job.get("items") or []) if item.get("done")]
    rows: list[dict[str, str]] = []
    for item in items:
        for row in item.get("rows") or []:
            if isinstance(row, dict):
                rows.append(
                    {
                        "id": str(row.get("id") or item.get("label") or ""),
                        "campo": str(row.get("campo") or ""),
                        "legacy": str(row.get("legacy") or ""),
                        "ia": str(row.get("ia") or ""),
                    }
                )
    if not items and not rows:
        return coverage
    ia = sum(1 for item in items if not item.get("fallback"))
    fallbacks = sum(1 for item in items if item.get("fallback"))
    tokens = int(job.get("tokens") or 0)
    finished = ia + fallbacks
    models = [str(model) for model in (job.get("models") or []) if model]
    merged = dict(coverage or {})
    merged["llm_polish"] = {
        "ia": ia,
        "fallbacks": fallbacks,
        "tokens": tokens,
        "model": ", ".join(models),
        "average_tokens": round(tokens / finished) if finished else 0,
        "rows": rows,
    }
    return merged


def schedule_persisted_polish(release_id: int, rows: list, work: list[dict[str, Any]] | None) -> None:
    if not polish_enabled() or not work or not rows:
        return
    if len(work) != len(rows):
        logger.warning("polish: %s ítems para %s casos; no se encola", len(work), len(rows))
        return
    queued: list[dict[str, Any]] = []
    for row, item in zip(rows, work):
        if item.get("skip"):
            continue
        queued.append(
            {
                "db_id": int(row.id),
                "label": str(getattr(row, "test_case_id", "") or ""),
                "epic": item.get("epic") or (getattr(row, "technical_epic", "") or ""),
                "done": False,
                "fallback": False,
                "tokens": 0,
                "rows": [],
                "original_name": item.get("original_name") or "",
                "payload": item.get("payload") or {},
                "bodies": item.get("bodies") or "",
                "scenario": item.get("scenario") or "",
            }
        )
    if not queued:
        return
    key = str(release_id)
    with _JOB_LOCK:
        _CANCELLED.discard(key)
        epoch = _EPOCH.get(key, 0)
        data = _load_jobs()
        releases = data.setdefault("releases", {})
        current = releases.get(key) or {
            "items": [],
            "tokens": 0,
            "running": False,
            "started": None,
            "finished": None,
            "epoch": epoch,
            "models": [],
        }
        current.setdefault("items", [])
        current.setdefault("models", [])
        current["epoch"] = current.get("epoch", epoch)
        for item in queued:
            item["epoch"] = current["epoch"]
        current["items"].extend(queued)
        current["finished"] = None
        current["paused_until"] = None
        current["running"] = True
        releases[key] = current
        _store_jobs(data)
        logger.info("polish encolados %s para release %s", len(queued), release_id)
        _JOB_LOCK.notify()
        _ensure_thread_locked()


def resume_interrupted_jobs() -> None:
    data = _load_jobs()
    pending = False
    for job in (data.get("releases") or {}).values():
        for item in job.get("items") or []:
            if not item.get("done"):
                item["claimed"] = False
                pending = True
        if pending:
            job["running"] = False
    if pending:
        _store_jobs(data)
        _ensure_thread()


def _ensure_thread_locked() -> None:
    """El llamador ya tiene _JOB_LOCK."""
    global _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        return
    _THREAD = threading.Thread(target=_run_jobs, name="polish-legacy", daemon=True)
    _THREAD.start()


def _ensure_thread() -> None:
    with _JOB_LOCK:
        _ensure_thread_locked()


def _take_locked() -> tuple[str, dict[str, Any]] | None:
    data = _load_jobs()
    releases = data.get("releases") or {}
    for key, job in releases.items():
        for item in job.get("items") or []:
            if not item.get("done") and not item.get("claimed"):
                item["claimed"] = True
                job["running"] = True
                job["started"] = job.get("started") or time.time()
                _store_jobs(data)
                logger.info(
                    "polish hilo tomó caso %s (release %s)",
                    item.get("label") or item.get("db_id"),
                    key,
                )
                return key, item
    changed = False
    for job in releases.values():
        items = job.get("items") or []
        if job.get("running") and items and all(item.get("done") for item in items):
            job["running"] = False
            job["finished"] = time.time()
            changed = True
    if changed:
        _store_jobs(data)
    return None


def _pending_locked() -> bool:
    data = _load_jobs()
    for job in (data.get("releases") or {}).values():
        if any(not item.get("done") and not item.get("claimed") for item in job.get("items") or []):
            return True
    return False


def _run_jobs() -> None:
    global _THREAD
    while True:
        with _JOB_LOCK:
            while not _pending_locked():
                woke = _JOB_LOCK.wait(timeout=2.0)
                if not woke and not _pending_locked():
                    _THREAD = None
                    return
            claimed = _take_locked()
        if claimed is None:
            continue
        release_id, item = claimed
        try:
            _process_item(int(release_id), item)
        except GroqDailyLimit as exc:
            _pause_for_daily_limit(release_id, item, exc)
        except Exception:
            logger.exception("polish job release=%s caso=%s", release_id, item.get("db_id"))
            _mark(release_id, item, fallback=True, tokens=0, rows=[], redaccion="error interno", model="")


def _same_generation(release_id: str, epoch: int | None) -> bool:
    if release_id in _CANCELLED:
        return False
    data = _load_jobs()
    job = (data.get("releases") or {}).get(release_id)
    return bool(job) and job.get("epoch") == epoch


def _active_model(release_id: str) -> str:
    data = _load_jobs()
    job = (data.get("releases") or {}).get(release_id) or {}
    return str(job.get("model") or polish_model())


def _set_job_model(release_id: str, model: str) -> None:
    with _JOB_LOCK:
        data = _load_jobs()
        job = (data.get("releases") or {}).get(str(release_id))
        if not job:
            return
        job["model"] = model
        _store_jobs(data)


def _pause_for_daily_limit(release_id: str, item: dict[str, Any], exc: GroqDailyLimit) -> None:
    wait = max(float(exc.retry_after or 1), 1.0)
    until = time.time() + wait
    with _JOB_LOCK:
        data = _load_jobs()
        job = (data.get("releases") or {}).get(release_id)
        if job:
            for current in job.get("items") or []:
                if current.get("db_id") == item.get("db_id") and not current.get("done"):
                    current["claimed"] = False
            job["paused_until"] = until
            job["running"] = True
            job.pop("model", None)
            _store_jobs(data)
    logger.warning(
        "polish pausada release=%s reanuda=%s",
        release_id,
        time.strftime("%H:%M", time.localtime(until)),
    )
    time.sleep(wait)
    with _JOB_LOCK:
        data = _load_jobs()
        job = (data.get("releases") or {}).get(release_id)
        if job and job.get("paused_until"):
            job["paused_until"] = None
            job["running"] = True
            _store_jobs(data)


def _process_item(release_id: int, item: dict[str, Any]) -> None:
    key = str(release_id)
    if not _same_generation(key, item.get("epoch")):
        return
    stored = _stored_redaccion(int(item["db_id"]))
    if stored:
        _mark(
            str(release_id),
            item,
            fallback=stored.lower().startswith("legacy"),
            tokens=0,
            rows=[],
            redaccion=stored,
        )
        return
    from app.schemas.case_generation import CandidateStep

    caso = (item.get("payload") or {}).get("caso") or {}
    steps = [
        CandidateStep(step_number=index, action=step.get("accion") or "", expected_result=step.get("resultado") or "")
        for index, step in enumerate(caso.get("pasos") or [], start=1)
        if isinstance(step, dict)
    ]
    case = GeneratedCaseCandidate(
        name=caso.get("titulo") or item.get("original_name") or "Caso",
        description="Redacción IA",
        evidence=item.get("scenario") or "Redacción IA",
        justification="Redacción IA",
        precondition=caso.get("precondicion") or None,
        variant_table=caso.get("variantes") or None,
        steps=steps,
    )
    stats = GenerationStats()
    model = _polish_one(
        case,
        item.get("payload") or {},
        item.get("bodies") or "",
        item.get("scenario") or "",
        stats,
        key=_groq_key(),
        retries=max(0, int(getattr(settings, "qc_llm_polish_retries", 1) or 1)),
        cache=_load_cache(),
        model=_active_model(key),
        case_id=str(item.get("label") or ""),
        release_id=key,
    )
    if not _same_generation(key, item.get("epoch")):
        return
    _apply_saved(int(item["db_id"]), case)
    _mark(
        key,
        item,
        fallback=not (case.redaccion == "IA"),
        tokens=stats.polish_tokens,
        rows=list(stats.polish_comparison),
        redaccion=case.redaccion or "",
        model=model,
    )


def _mark(
    release_id: str,
    item: dict[str, Any],
    *,
    fallback: bool,
    tokens: int,
    rows: list[dict[str, str]],
    redaccion: str,
    model: str = "",
) -> None:
    with _JOB_LOCK:
        data = _load_jobs()
        job = (data.get("releases") or {}).get(release_id)
        if not job:
            return
        if item.get("epoch") is not None and job.get("epoch") != item.get("epoch"):
            return
        for current in job.get("items") or []:
            if current.get("db_id") == item.get("db_id") and current.get("claimed") and not current.get("done"):
                current["done"] = True
                current["claimed"] = False
                current["fallback"] = fallback
                current["tokens"] = tokens
                current["rows"] = rows
                current["redaccion"] = redaccion
                job["tokens"] = int(job.get("tokens") or 0) + int(tokens or 0)
                if model:
                    models = job.setdefault("models", [])
                    if model not in models:
                        models.append(model)
                break
        items = job.get("items") or []
        if items and all(row.get("done") for row in items):
            job["running"] = False
            job["finished"] = time.time()
        _store_jobs(data)


def _stored_redaccion(db_id: int) -> str | None:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models.test_case import TestCase

    db = SessionLocal()
    try:
        row = db.execute(select(TestCase).where(TestCase.id == db_id)).scalar_one_or_none()
        if row is None or not row.test_data:
            return None
        match = re.search(r"^Redacción:\s*(.+)$", row.test_data, re.MULTILINE | re.IGNORECASE)
        return match.group(1).strip() if match else None
    finally:
        db.close()


def _rewrite_test_data(raw: str | None, precondition: str | None, variants: str | None, redaccion: str) -> str | None:
    text = _REDACCION_LINE.sub("", raw or "").strip()
    if precondition is not None:
        line = f"Precondición: {precondition}" if precondition else ""
        if re.search(r"^Precondición:", text, re.MULTILINE | re.IGNORECASE):
            text = re.sub(
                r"^Precondición:.*$",
                line,
                text,
                count=1,
                flags=re.MULTILINE | re.IGNORECASE,
            ).strip()
        elif line:
            text = f"{line}\n{text}".strip()
    if variants is not None and variants:
        block = f"Variantes:\n{variants}"
        if re.search(r"^Variantes:", text, re.MULTILINE | re.IGNORECASE):
            text = re.sub(r"Variantes:\s*.*\Z", block, text, count=1, flags=re.IGNORECASE | re.DOTALL).strip()
        else:
            text = f"{text}\n{block}".strip()
    if redaccion and redaccion != "Legacy":
        text = f"{text}\nRedacción: {redaccion}".strip()
    return text or None


def _apply_saved(db_id: int, case: GeneratedCaseCandidate) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.db import SessionLocal
    from app.models.test_case import TestCase

    db = SessionLocal()
    try:
        row = db.execute(
            select(TestCase).where(TestCase.id == db_id).options(selectinload(TestCase.steps))
        ).scalar_one_or_none()
        if row is None:
            return
        redaccion = case.redaccion or ""
        if redaccion == "IA":
            row.test_case_name = (case.name or row.test_case_name)[:250]
            ordered = sorted(row.steps, key=lambda step: step.step_number)
            for step, item in zip(ordered, case.steps):
                step.test_step = item.action
                step.expected_result = item.expected_result
            row.test_data = _rewrite_test_data(
                row.test_data,
                case.precondition or "",
                case.variant_table or "",
                redaccion,
            )
        elif redaccion.startswith("Legacy (fallback"):
            row.test_data = _rewrite_test_data(row.test_data, None, None, redaccion)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
