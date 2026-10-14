"""Cliente OpenAI para la v2: JSON estricto, reintentos acotados y corte ante falta de créditos."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class QuotaExhausted(Exception):
    """La cuenta de OpenAI no tiene créditos: la corrida debe detenerse."""


class LlmError(Exception):
    pass


@dataclass
class LlmMeta:
    model: str
    ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attempts: int = 0


_QUOTA_MARKERS = ("insufficient_quota", "no credits", "credit balance", "exceeded your current quota")


def _is_quota(body: str) -> bool:
    lowered = (body or "").lower()
    return any(marker in lowered for marker in _QUOTA_MARKERS)


def chat_json(
    messages: list[dict[str, str]],
    *,
    model: str,
    temperature: float | None = None,
    timeout: float | None = None,
    max_retries: int = 3,
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[str, Any], LlmMeta]:
    """Llama a /chat/completions pidiendo un objeto JSON. Lanza QuotaExhausted o LlmError."""
    if not (settings.openai_api_key or "").strip():
        raise LlmError("OPENAI_API_KEY no configurada")
    meta = LlmMeta(model=model)
    use_temperature = temperature
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    started = time.monotonic()
    last_error = ""
    attempt = 0
    with httpx.Client(timeout=timeout or settings.qc_v2_timeout, transport=transport) as client:
        while attempt <= max_retries:
            attempt += 1
            meta.attempts = attempt
            payload = dict(body)
            if use_temperature is not None:
                payload["temperature"] = use_temperature
            try:
                response = client.post(url, json=payload, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"red: {exc.__class__.__name__}"
                time.sleep(min(2**attempt, 20))
                continue
            text = response.text
            if response.status_code == 400 and use_temperature is not None and "temperature" in text:
                use_temperature = None  # modelos de razonamiento no aceptan temperature
                attempt -= 1
                continue
            if response.status_code == 429:
                if _is_quota(text):
                    raise QuotaExhausted("OpenAI sin créditos (insufficient_quota)")
                last_error = "rate limit"
                time.sleep(min(2**attempt, 30))
                continue
            if response.status_code in (401, 403):
                raise LlmError(f"OpenAI rechazó la llave ({response.status_code})")
            if response.status_code >= 500:
                last_error = f"HTTP {response.status_code}"
                time.sleep(min(2**attempt, 20))
                continue
            if response.status_code != 200:
                raise LlmError(f"HTTP {response.status_code}: {text[:300]}")
            data = response.json()
            usage = data.get("usage") or {}
            meta.prompt_tokens += int(usage.get("prompt_tokens") or 0)
            meta.completion_tokens += int(usage.get("completion_tokens") or 0)
            content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            meta.ms = int((time.monotonic() - started) * 1000)
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError as exc:
                raise LlmError(f"respuesta no es JSON válido: {exc}") from exc
            if not isinstance(parsed, dict):
                raise LlmError("la respuesta JSON no es un objeto")
            return parsed, meta
    meta.ms = int((time.monotonic() - started) * 1000)
    raise LlmError(f"sin respuesta tras {max_retries} reintentos ({last_error})")
