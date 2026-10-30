"""Proveedor LLM único (API compatible con OpenAI). Independiente del motor QC."""

from app.llm.client import (
    LlmError,
    QuotaExhausted,
    extract_json_object,
    generate,
    is_configured,
    ping,
    provider_name,
    resolved_base_url,
    resolved_model,
)

__all__ = [
    "LlmError",
    "QuotaExhausted",
    "extract_json_object",
    "generate",
    "is_configured",
    "ping",
    "provider_name",
    "resolved_base_url",
    "resolved_model",
]
