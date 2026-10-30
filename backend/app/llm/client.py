"""Cliente HTTP compatible con OpenAI para todos los proveedores configurados en .env."""

from __future__ import annotations

import json
import logging
import random
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

PROVIDER_URLS = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://localhost:11434/v1",
}

_JSON_ONLY = "Responde únicamente un objeto JSON válido, sin markdown ni texto alrededor."
_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_QUOTA_MARKERS = ("insufficient_quota", "no credits", "credit balance", "exceeded your current quota")
_JSON_REJECT = ("response_format", "json_object", "unknown parameter", "unsupported")
_SIZE_RETRY = ("too large", "request too large", "tpm")
_VALIDATE_RETRY = ("json_validate_failed", "max completion", "max_tokens", "max completion tokens")

def open_client(**kwargs):
    """Hook for tests. Production uses httpx.Client."""
    return httpx.Client(**kwargs)


_gate: threading.BoundedSemaphore | None = None
_gate_n: int = 0
_gate_lock = threading.Lock()


class QuotaExhausted(Exception):
    """El proveedor no tiene créditos o cuota de facturación."""


class LlmError(Exception):
    pass


@dataclass
class LlmResult:
    text: str
    model: str
    provider: str
    ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attempts: int = 0
    json_mode: bool = False
    ok: bool = True


def provider_name() -> str:
    raw = (getattr(settings, "llm_provider", None) or "").strip().lower()
    if raw:
        return raw
    if (getattr(settings, "openai_api_key", None) or "").strip():
        return "openai"
    return "none"


def resolved_model() -> str:
    return (
        (getattr(settings, "llm_model", None) or "").strip()
        or (getattr(settings, "openai_model", None) or "").strip()
        or "gpt-4o-mini"
    )


def resolved_base_url() -> str:
    explicit = (getattr(settings, "llm_base_url", None) or "").strip()
    if explicit:
        return explicit.rstrip("/")
    provider = provider_name()
    if provider == "openai":
        previous = (getattr(settings, "openai_base_url", None) or "").strip()
        if previous:
            return previous.rstrip("/")
    return (PROVIDER_URLS.get(provider) or PROVIDER_URLS["openai"]).rstrip("/")


def resolved_api_key() -> str:
    key = (
        (getattr(settings, "llm_api_key", None) or "").strip()
        or (getattr(settings, "openai_api_key", None) or "").strip()
    )
    if not key and provider_name() == "ollama":
        return "ollama"
    return key


def is_configured() -> bool:
    provider = provider_name()
    if provider in {"", "none"}:
        return False
    if provider == "ollama":
        return True
    return bool(resolved_api_key())


def _semaphore() -> threading.BoundedSemaphore:
    global _gate, _gate_n
    n = max(1, int(getattr(settings, "llm_max_concurrency", 2) or 2))
    with _gate_lock:
        if _gate is None or _gate_n != n:
            _gate = threading.BoundedSemaphore(n)
            _gate_n = n
        return _gate


def _redact(value: object) -> str:
    text = str(value) if value is not None else ""
    for key in (resolved_api_key(), getattr(settings, "openai_api_key", "") or ""):
        if key:
            text = text.replace(key, "[redacted]")
    text = re.sub(r"(?i)(authorization\s*[:=]\s*)(\S+)", r"\1[redacted]", text)
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", text)
    return text[:300]


def _is_quota(body: str) -> bool:
    lowered = (body or "").lower()
    return any(marker in lowered for marker in _QUOTA_MARKERS)


def _backoff(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return min(max(float(retry_after), 0.1), 60.0)
        except ValueError:
            pass
    return min((2**attempt) + random.random(), 30.0)


def extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    fence = _FENCE.search(raw)
    if fence:
        raw = fence.group(1).strip()
    candidates = [raw]
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        candidates.append(raw[start : end + 1])
    for blob in candidates:
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise LlmError("respuesta no es JSON válido")


def _log(event: str, *, provider: str, model: str, ms: int, ok: bool, tokens: int | None = None) -> None:
    logger.info(
        "llm %s provider=%s model=%s ms=%s ok=%s tokens=%s",
        event,
        provider,
        model,
        ms,
        ok,
        tokens if tokens is not None else "-",
    )


def generate(
    messages: list[dict[str, str]],
    *,
    json_mode: bool = False,
    temperature: float | None = None,
    model: str | None = None,
    timeout: float | None = None,
    reasoning_effort: str | None = None,
    max_retries: int | None = None,
    transport: httpx.BaseTransport | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    max_tokens: int | None = None,
) -> str:
    """Una completions call. Devuelve el texto del asistente. No loguea prompts ni keys."""
    return complete(
        messages,
        json_mode=json_mode,
        temperature=temperature,
        model=model,
        timeout=timeout,
        reasoning_effort=reasoning_effort,
        max_retries=max_retries,
        transport=transport,
        repair=json_mode,
        api_key=api_key,
        base_url=base_url,
        max_tokens=max_tokens,
    ).text


def complete(
    messages: list[dict[str, str]],
    *,
    json_mode: bool = False,
    temperature: float | None = None,
    model: str | None = None,
    timeout: float | None = None,
    reasoning_effort: str | None = None,
    max_retries: int | None = None,
    transport: httpx.BaseTransport | None = None,
    repair: bool | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    max_tokens: int | None = None,
) -> LlmResult:
    return _complete(
        messages,
        json_mode=json_mode,
        temperature=temperature,
        model=model,
        timeout=timeout,
        reasoning_effort=reasoning_effort,
        max_retries=max_retries,
        transport=transport,
        repair=json_mode if repair is None else repair,
        api_key=api_key,
        base_url=base_url,
        max_tokens=max_tokens,
    )


def _complete(
    messages: list[dict[str, str]],
    *,
    json_mode: bool,
    temperature: float | None,
    model: str | None,
    timeout: float | None,
    reasoning_effort: str | None,
    max_retries: int | None,
    transport: httpx.BaseTransport | None,
    repair: bool,
    api_key: str | None = None,
    base_url: str | None = None,
    max_tokens: int | None = None,
) -> LlmResult:
    key = (api_key or resolved_api_key()).strip()
    provider = provider_name()
    if provider == "none":
        if not key:
            raise LlmError("LLM no configurado")
        provider = "openai"
    elif provider != "ollama" and not key:
        raise LlmError("LLM no configurado")
    use_model = (model or resolved_model()).strip()
    use_temp = settings.llm_temperature if temperature is None else temperature
    use_reasoning = (reasoning_effort or "").strip().lower() or None
    retries = int(max_retries if max_retries is not None else getattr(settings, "llm_max_retries", 3) or 3)
    wait = timeout if timeout is not None else float(getattr(settings, "llm_timeout_seconds", 60) or 60)
    url = (base_url or resolved_base_url()).rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    use_json_format = json_mode
    msgs = list(messages)
    if json_mode:
        msgs = _ensure_json_instruction(msgs)
    started = time.monotonic()
    last_error = ""
    attempt = 0
    prompt_tokens = 0
    completion_tokens = 0
    _semaphore().acquire()
    try:
        with open_client(timeout=wait, transport=transport) as client:
            while attempt <= retries:
                attempt += 1
                payload: dict[str, Any] = {"model": use_model, "messages": msgs}
                if use_temp is not None:
                    payload["temperature"] = use_temp
                if use_json_format:
                    payload["response_format"] = {"type": "json_object"}
                if use_reasoning:
                    payload["reasoning_effort"] = use_reasoning
                tokens = max_tokens
                if tokens is None:
                    tokens = int(getattr(settings, "qc_v2_max_completion_tokens", 0) or 0) or None
                if tokens:
                    payload["max_tokens"] = int(tokens)
                try:
                    response = client.post(url, json=payload, headers=headers)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_error = f"red: {exc.__class__.__name__}"
                    time.sleep(_backoff(attempt, None))
                    continue
                raw_body = response.text
                text = raw_body if isinstance(raw_body, str) else ""
                if response.status_code == 400 and use_temp is not None and "temperature" in text.lower():
                    use_temp = None
                    attempt -= 1
                    continue
                if response.status_code == 400 and use_reasoning and "reasoning" in text.lower():
                    use_reasoning = None
                    attempt -= 1
                    continue
                if (
                    response.status_code == 400
                    and use_json_format
                    and any(token in text.lower() for token in _JSON_REJECT)
                ):
                    use_json_format = False
                    attempt -= 1
                    continue
                lowered = text.lower()
                if response.status_code in (413, 429) or (
                    response.status_code == 400 and any(token in lowered for token in _SIZE_RETRY)
                ):
                    if response.status_code == 429 and _is_quota(text):
                        raise QuotaExhausted("proveedor sin créditos (insufficient_quota)")
                    last_error = f"HTTP {response.status_code}"
                    time.sleep(_backoff(attempt, response.headers.get("Retry-After")))
                    continue
                if response.status_code == 400 and any(token in lowered for token in _VALIDATE_RETRY):
                    last_error = "json_validate_failed"
                    current = int(tokens or getattr(settings, "qc_v2_max_completion_tokens", 4096) or 4096)
                    max_tokens = min(max(current * 2, 4096), 8192)
                    time.sleep(_backoff(attempt, response.headers.get("Retry-After")))
                    continue
                if response.status_code in (401, 403):
                    raise LlmError(f"el proveedor rechazó la llave ({response.status_code})")
                if response.status_code >= 500:
                    last_error = f"HTTP {response.status_code}"
                    time.sleep(_backoff(attempt, response.headers.get("Retry-After")))
                    continue
                if response.status_code != 200:
                    raise LlmError(f"HTTP {response.status_code}: {_redact(text)}")
                data = response.json()
                usage = data.get("usage") or {}
                prompt_tokens += int(usage.get("prompt_tokens") or 0)
                completion_tokens += int(usage.get("completion_tokens") or 0)
                content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                ms = int((time.monotonic() - started) * 1000)
                if json_mode:
                    try:
                        extract_json_object(content)
                    except LlmError:
                        if repair:
                            repair = False
                            msgs = msgs + [
                                {"role": "assistant", "content": content[:2000]},
                                {
                                    "role": "user",
                                    "content": "El JSON no es válido. Devuelve solo un objeto JSON corregido, sin markdown.",
                                },
                            ]
                            last_error = "json inválido"
                            continue
                        raise
                _log(
                    "ok",
                    provider=provider,
                    model=use_model,
                    ms=ms,
                    ok=True,
                    tokens=prompt_tokens + completion_tokens,
                )
                return LlmResult(
                    text=content,
                    model=use_model,
                    provider=provider,
                    ms=ms,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    attempts=attempt,
                    json_mode=use_json_format,
                )
    finally:
        _semaphore().release()
    ms = int((time.monotonic() - started) * 1000)
    _log("fail", provider=provider, model=use_model, ms=ms, ok=False)
    raise LlmError(f"sin respuesta tras {retries} reintentos ({last_error})")


def _ensure_json_instruction(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    blob = " ".join(m.get("content") or "" for m in messages)
    if "JSON" in blob or "json" in blob:
        return list(messages)
    extra = {"role": "system", "content": _JSON_ONLY}
    if messages and messages[0].get("role") == "system":
        first = dict(messages[0])
        first["content"] = (first.get("content") or "") + "\n" + _JSON_ONLY
        return [first, *messages[1:]]
    return [extra, *messages]


def ping() -> dict[str, Any]:
    """Llamada mínima para /health. No incluye la API key."""
    provider = provider_name()
    model = resolved_model()
    if not is_configured():
        return {
            "status": "disabled",
            "provider": provider,
            "model": model,
            "latency_ms": 0,
            "configured": False,
        }
    started = time.monotonic()
    try:
        generate(
            [{"role": "user", "content": "Responde con la palabra ok."}],
            json_mode=False,
            temperature=0,
            timeout=min(20.0, float(getattr(settings, "llm_timeout_seconds", 60) or 60)),
            max_retries=1,
        )
        ms = int((time.monotonic() - started) * 1000)
        return {
            "status": "ok",
            "provider": provider,
            "model": model,
            "latency_ms": ms,
            "configured": True,
        }
    except QuotaExhausted as exc:
        return {
            "status": "error",
            "provider": provider,
            "model": model,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "configured": True,
            "message": str(exc),
        }
    except Exception as exc:
        return {
            "status": "error",
            "provider": provider,
            "model": model,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "configured": True,
            "message": _redact(exc),
        }
