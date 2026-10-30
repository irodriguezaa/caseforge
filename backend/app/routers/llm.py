"""Diagnóstico del proveedor LLM. No expone la API key."""

from fastapi import APIRouter

from app.llm.client import ping

router = APIRouter(tags=["llm"])


@router.get("/api/v1/llm/health")
@router.get("/api/llm/health")
def llm_health() -> dict:
    return ping()
