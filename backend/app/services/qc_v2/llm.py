"""Etapa A/B de v2: JSON estricto sobre el cliente LLM compartido."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.llm.client import (
    LlmError,
    QuotaExhausted,
    complete,
    extract_json_object,
    is_configured,
)

logger = __import__("logging").getLogger(__name__)


@dataclass
class LlmMeta:
    model: str
    ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attempts: int = 0


def chat_json(
    messages: list[dict[str, str]],
    *,
    model: str,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    timeout: float | None = None,
    max_retries: int = 3,
    transport: httpx.BaseTransport | None = None,
) -> tuple[dict[str, Any], LlmMeta]:
    if not is_configured():
        raise LlmError("LLM no configurado")
    result = complete(
        messages,
        json_mode=True,
        temperature=temperature,
        model=model,
        timeout=timeout,
        reasoning_effort=reasoning_effort,
        max_retries=max_retries,
        transport=transport,
    )
    parsed = extract_json_object(result.text)
    meta = LlmMeta(
        model=result.model,
        ms=result.ms,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        attempts=result.attempts,
    )
    return parsed, meta
