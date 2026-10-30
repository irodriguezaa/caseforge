"""Cliente LLM compartido: proveedores, JSON y reintentos."""

from __future__ import annotations

import json

import httpx
import pytest

from app.llm.client import (
    PROVIDER_URLS,
    QuotaExhausted,
    extract_json_object,
    generate,
    ping,
    provider_name,
    resolved_base_url,
)


def _transport(responses, seen):
    queue = list(responses)

    def handler(request):
        seen.append(json.loads(request.content))
        status, body = queue.pop(0)
        headers = {}
        if isinstance(body, dict) and body.get("_retry_after"):
            headers["Retry-After"] = str(body.pop("_retry_after"))
        return httpx.Response(status, json=body, headers=headers)

    return httpx.MockTransport(handler)


def test_extract_json_strips_fences():
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_object('nota\n{"b": 2}\nfin') == {"b": 2}


def test_provider_urls():
    assert PROVIDER_URLS["gemini"].startswith("https://generativelanguage.googleapis.com")
    assert PROVIDER_URLS["groq"].endswith("/openai/v1")
    assert PROVIDER_URLS["ollama"].startswith("http://localhost:11434")


def test_generate_json_and_retry_after(monkeypatch):
    from app.llm import client as llm

    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "provider_name", lambda: "groq")
    monkeypatch.setattr(llm, "resolved_api_key", lambda: "g")
    monkeypatch.setattr(llm, "resolved_base_url", lambda: "https://api.groq.com/openai/v1")
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    ok = {"choices": [{"message": {"content": json.dumps({"ok": True})}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}
    seen: list[dict] = []
    transport = _transport(
        [
            (429, {"error": {"message": "rate"}, "_retry_after": "0"}),
            (200, ok),
        ],
        seen,
    )
    text = generate(
        [{"role": "user", "content": "json"}],
        json_mode=True,
        model="m",
        transport=transport,
        api_key="g",
        base_url="https://api.groq.com/openai/v1",
    )
    assert json.loads(text) == {"ok": True}
    assert seen[0].get("response_format") == {"type": "json_object"}


def test_quota_raises(monkeypatch):
    from app.llm import client as llm

    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    transport = _transport(
        [(429, {"error": {"code": "insufficient_quota", "message": "You have no credits remaining"}})],
        [],
    )
    with pytest.raises(QuotaExhausted):
        generate([{"role": "user", "content": "x"}], json_mode=False, transport=transport, api_key="k")


def test_health_endpoint(client):
    response = client.get("/api/v1/llm/health")
    assert response.status_code == 200
    body = response.json()
    assert "provider" in body and "model" in body and "status" in body
    assert "api_key" not in json.dumps(body).lower()


def test_ping_disabled(monkeypatch):
    from app.llm import client as llm

    monkeypatch.setattr(llm, "is_configured", lambda: False)
    monkeypatch.setattr(llm, "provider_name", lambda: "none")
    body = ping()
    assert body["status"] == "disabled"
    assert body["configured"] is False
    assert "api_key" not in json.dumps(body).lower()
