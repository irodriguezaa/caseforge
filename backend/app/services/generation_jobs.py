"""In-process Regenerar casos job. One uvicorn worker on QC4 is enough to run keys sequentially."""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.db import SessionLocal
from app.schemas.case_generation import GenerateCasesResponse

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_jobs: dict[int, dict[str, Any]] = {}


def get_job(release_id: int) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(release_id)
        return dict(job) if job else None


def job_to_response(release_id: int, job: dict[str, Any]) -> GenerateCasesResponse:
    return GenerateCasesResponse(
        status=str(job.get("status") or "IDLE"),
        message=str(job.get("message") or ""),
        release_id=release_id,
        release_name=str(job.get("release_name") or ""),
        has_analysis=True,
        engine="background",
        test_case_count=int(job.get("test_case_count") or 0),
        functionality_keys=list(job.get("keys") or []),
        chunk_key=job.get("chunk_key"),
        persisted=str(job.get("status")) == "DONE",
    )


def _set_job(release_id: int, **fields: Any) -> dict[str, Any]:
    with _lock:
        current = _jobs.get(release_id) or {}
        current.update(fields)
        _jobs[release_id] = current
        return dict(current)


def start_generation(release_id: int, regenerate: bool) -> dict[str, Any]:
    with _lock:
        current = _jobs.get(release_id)
        if current and current.get("status") == "RUNNING":
            return dict(current)
        _jobs[release_id] = {
            "status": "RUNNING",
            "message": "Generación en segundo plano…",
            "test_case_count": 0,
            "keys": [],
            "chunk_key": None,
            "release_name": "",
        }
    threading.Thread(
        target=_run,
        args=(release_id, regenerate),
        daemon=True,
        name=f"generate-cases-{release_id}",
    ).start()
    return get_job(release_id) or {}


def _run(release_id: int, regenerate: bool) -> None:
    from app.routers.releases import _generate_cases_from_rn

    db = SessionLocal()
    try:
        plan = _generate_cases_from_rn(release_id, regenerate, db, chunked=True)
        _set_job(
            release_id,
            release_name=plan.release_name,
            keys=list(plan.functionality_keys or []),
        )
        if plan.status == "ALREADY_GENERATED":
            _set_job(
                release_id,
                status="DONE",
                message=plan.message,
                test_case_count=plan.test_case_count,
            )
            return
        keys = list(plan.functionality_keys or [])
    except Exception:
        logger.exception("background generate-cases crashed release_id=%s", release_id)
        _set_job(
            release_id,
            status="ERROR",
            message="Regenerar casos se cayó en segundo plano. Revisa logs de qcpulse-backend-1.",
        )
        return
    finally:
        db.close()

    try:
        persisted = 0
        empty: list[str] = []
        failed: list[str] = []
        for index, key in enumerate(keys, start=1):
            _set_job(
                release_id,
                message=f"Generando {index}/{len(keys)}: {key}",
                chunk_key=key,
                test_case_count=persisted,
            )
            chunk_db = SessionLocal()
            try:
                chunk = _generate_cases_from_rn(
                    release_id,
                    False,
                    chunk_db,
                    chunked=True,
                    functionality_key=key,
                )
                n = chunk.test_case_count or 0
                persisted += n
                if not chunk.persisted or n == 0:
                    empty.append(key)
            except Exception:
                logger.exception("background generate-cases failed release_id=%s key=%s", release_id, key)
                failed.append(key)
            finally:
                chunk_db.close()
        message = (
            f"Procesadas {len(keys) - len(failed)}/{len(keys)} funcionalidades del RN. "
            f"Test Cases persistidos: {persisted}."
        )
        if empty:
            message += f" Sin casos: {', '.join(empty)}."
        if failed:
            message += f" Error: {', '.join(failed)}."
        _set_job(
            release_id,
            status="ERROR" if keys and len(failed) == len(keys) else "DONE",
            message=message,
            test_case_count=persisted,
            chunk_key=None,
        )
    except Exception:
        logger.exception("background generate-cases crashed release_id=%s", release_id)
        _set_job(
            release_id,
            status="ERROR",
            message="Regenerar casos se cayó en segundo plano. Revisa logs de qcpulse-backend-1.",
        )
