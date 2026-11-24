"""La redacción no cambia la decisión de Legacy."""

import json
from types import SimpleNamespace

import httpx
import pytest

from app.config import settings
from app.schemas.case_generation import CandidateStep, CoverageUnit, GeneratedCaseCandidate, GenerationStats
from app.services.legacy_polish import (
    _label,
    collect_polish_work,
    polish_legacy_cases,
    polish_status,
    schedule_persisted_polish,
)
from app.services.test_case_export import build_test_cases_workbook


def _case() -> GeneratedCaseCandidate:
    return GeneratedCaseCandidate(
        name="Navegación al Selector de Planes",
        description="d",
        evidence="e",
        justification="j",
        precondition="El usuario está en el Home.",
        covers=["COV-1"],
        steps=[
            CandidateStep(
                step_number=1,
                action="Seleccionar el botón «Ver planes»",
                expected_result="Se redirige al usuario al Selector de Planes.",
            )
        ],
    )


def _unit() -> CoverageUnit:
    return CoverageUnit(
        coverage_id="COV-1",
        role="A",
        behavior="Navegación al Selector de Planes",
        scenario="Navegación al Selector de Planes",
        evidence="e",
        body=(
            'When el usuario selecciona el botón "Ver planes"\n'
            "Then se redirige al usuario al Selector de Planes"
        ),
    )


def _body(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _ok(title: str = "Usuario externo selecciona Ver planes y llega al Selector.") -> str:
    return _body(
        {
            "titulo": title,
            "precondicion": "El usuario está en el Home.",
            "pasos": [
                {
                    "accion": "Seleccionar el botón «Ver planes»",
                    "resultado": "Se redirige al usuario al Selector de Planes.",
                }
            ],
            "variantes": "",
        }
    )


def _response(content: str, status: int = 200, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10},
        },
        headers=headers or {},
    )


def _set(name: str, value: object) -> None:
    object.__setattr__(settings, name, value)


@pytest.fixture(autouse=True)
def _restore_polish():
    previous = (
        settings.qc_llm_polish,
        settings.qc_llm_polish_retries,
        settings.groq_api_key,
        settings.qc_llm_tpm_limit,
    )
    yield
    _set("qc_llm_polish", previous[0])
    _set("qc_llm_polish_retries", previous[1])
    _set("groq_api_key", previous[2])
    _set("qc_llm_tpm_limit", previous[3])


def _enable(monkeypatch, tmp_path) -> None:
    _set("qc_llm_polish", "groq")
    _set("qc_llm_polish_retries", 1)
    _set("groq_api_key", "test-key")
    _set("qc_llm_tpm_limit", 7000)
    monkeypatch.setenv("QC_LLM_CACHE", str(tmp_path / "cache.json"))
    monkeypatch.setenv("QC_LLM_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setattr("app.services.legacy_polish.time.sleep", lambda *_a, **_k: None)


def test_off_leaves_the_legacy_text() -> None:
    _set("qc_llm_polish", "off")
    case = _case()
    polish_legacy_cases([case], [_unit()], GenerationStats())
    assert case.name == "Navegación al Selector de Planes"
    assert case.redaccion is None
    assert case.steps[0].action.startswith("Seleccionar")


def test_valid_rewrite_keeps_steps_and_quotes(monkeypatch, tmp_path) -> None:
    _enable(monkeypatch, tmp_path)
    monkeypatch.setattr("app.services.legacy_polish._post", lambda *_a, **_k: _response(_ok()))
    case = _case()
    stats = GenerationStats()
    stats.scenario_ledger.append(
        {"story": "ST", "scenario": "Navegación al Selector de Planes", "estado": "caso ejecutable", "case_id": case.name}
    )
    polish_legacy_cases([case], [_unit()], stats)
    assert case.redaccion == "IA"
    assert case.name.startswith("Usuario externo")
    assert len(case.steps) == 1
    assert "«Ver planes»" in case.steps[0].action
    assert stats.scenario_ledger[0]["estado"] == "caso ejecutable"
    assert stats.scenario_ledger[0]["case_id"] == case.name
    assert stats.polish_ia == 1
    assert stats.polish_fallback == 0
    assert stats.polish_tokens == 30


def test_unknown_quote_falls_back_to_legacy(monkeypatch, tmp_path) -> None:
    _enable(monkeypatch, tmp_path)
    bad = _ok().replace("«Ver planes»", "«Plan nuevo»")
    monkeypatch.setattr("app.services.legacy_polish._post", lambda *_a, **_k: _response(bad))
    case = _case()
    stats = GenerationStats()
    polish_legacy_cases([case], [_unit()], stats)
    assert case.name == "Navegación al Selector de Planes"
    assert case.steps[0].action == "Seleccionar el botón «Ver planes»"
    assert case.redaccion.startswith("Legacy (fallback:")
    assert stats.polish_fallback == 1
    assert stats.scenario_ledger == []


def test_retry_accepts_the_corrected_json(monkeypatch, tmp_path) -> None:
    _enable(monkeypatch, tmp_path)
    calls = {"n": 0}

    def post(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _response("{")
        return _response(_ok())

    monkeypatch.setattr("app.services.legacy_polish._post", post)
    case = _case()
    stats = GenerationStats()
    polish_legacy_cases([case], [_unit()], stats)
    assert calls["n"] == 2
    assert case.redaccion == "IA"


def test_cache_skips_the_second_call(monkeypatch, tmp_path) -> None:
    _enable(monkeypatch, tmp_path)
    calls = {"n": 0}

    def post(*_a, **_k):
        calls["n"] += 1
        return _response(_ok())

    monkeypatch.setattr("app.services.legacy_polish._post", post)
    polish_legacy_cases([_case()], [_unit()], GenerationStats())
    stats = GenerationStats()
    polish_legacy_cases([_case()], [_unit()], stats)
    assert calls["n"] == 1
    assert stats.polish_ia == 1
    assert stats.polish_tokens == 0


def test_rate_limit_retries_without_aborting(monkeypatch, tmp_path) -> None:
    _enable(monkeypatch, tmp_path)
    calls = {"n": 0}

    def post(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _response("", status=429, headers={"Retry-After": "0"})
        return _response(_ok())

    monkeypatch.setattr("app.services.legacy_polish._post", post)
    case = _case()
    polish_legacy_cases([case], [_unit()], GenerationStats())
    assert case.redaccion == "IA"
    assert calls["n"] == 2


def test_excel_marks_redaccion_and_comparison() -> None:
    case = SimpleNamespace(
        test_case_id="QC-001",
        test_case_name="Usuario externo selecciona Ver planes y llega al Selector.",
        component="EPC-1",
        technical_epic="EPC-1",
        hn_source=None,
        status="UNEXECUTED",
        estimation_hours=0.25,
        priority="CRITICAL",
        test_type="FUNCTIONAL",
        source_type="functionality",
        user_type=None,
        test_data="Precondición: El usuario está en el Home.\nRedacción: IA",
        evidence="",
        justification="",
        technical_story="ST-1",
        scenario_origin="Navegación al Selector de Planes",
        confidence=None,
        complexity="BAJA",
        description=None,
        device=None,
        applicability_reason=None,
        steps=[SimpleNamespace(step_number=1, test_step="Seleccionar el botón «Ver planes»", expected_result="Se redirige al Selector.")],
    )
    import io

    from openpyxl import load_workbook

    payload = build_test_cases_workbook(
        [case],
        coverage={
            "llm_polish": {
                "ia": 1,
                "fallbacks": 0,
                "tokens": 30,
                "rows": [
                    {
                        "id": case.test_case_name,
                        "campo": "Título",
                        "legacy": "Navegación al Selector de Planes",
                        "ia": case.test_case_name,
                    }
                ],
            }
        },
    )
    book = load_workbook(io.BytesIO(payload))
    header = [cell.value for cell in book["Test Cases"][1]]
    assert header[-1] == "Redacción"
    assert book["Test Cases"].cell(2, len(header)).value == "IA"
    assert book["Avance"]["H1"].value == "Redacción IA"
    assert book["Avance"]["I1"].value == 1
    assert book["Avance"]["I3"].value == 30
    assert book["Avance"]["H4"].value == "Modelo"
    assert book["Avance"]["I4"].value in ("", None)
    assert book["Avance"]["H5"].value == "Tokens promedio"
    assert book["Avance"]["I5"].value == 30
    assert book["Comparación IA"]["A2"].value == "QC-001"
    assert book["Comparación IA"]["B2"].value == "Título"
    assert "Escenarios de Jira" in book.sheetnames


def test_gpt_oss_sends_low_reasoning_and_1500_tokens(monkeypatch, tmp_path) -> None:
    _enable(monkeypatch, tmp_path)
    seen: dict = {}

    def post(payload, *_a, **_k):
        seen["body"] = payload
        return _response(_ok())

    monkeypatch.setattr("app.services.legacy_polish._post", post)
    polish_legacy_cases([_case()], [_unit()], GenerationStats())
    assert seen["body"]["max_completion_tokens"] == 1500
    assert seen["body"]["reasoning_effort"] == "low"
    assert "gpt-oss" in seen["body"]["model"]


def test_status_labels() -> None:
    assert _label([{"done": False}], False) == "pendiente"
    assert _label([{"done": False}, {"done": True}], True) == "en curso (1/2)"
    assert _label([{"done": True, "fallback": False}], True) == "lista"
    assert _label([{"done": True, "fallback": True}], False) == "con fallbacks"


def test_interrupted_job_reuses_the_cache(monkeypatch, tmp_path) -> None:
    from app.services import legacy_polish as polish

    _enable(monkeypatch, tmp_path)
    calls = {"n": 0}

    def post(*_a, **_k):
        calls["n"] += 1
        return _response(_ok())

    monkeypatch.setattr("app.services.legacy_polish._post", post)
    monkeypatch.setattr("app.services.legacy_polish._stored_redaccion", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.legacy_polish._apply_saved", lambda *_a, **_k: None)
    polish_legacy_cases([_case()], [_unit()], GenerationStats())
    work = collect_polish_work([_case()], [_unit()])
    item = {
        **work[0],
        "db_id": 9,
        "label": "QC-009",
        "done": False,
        "claimed": True,
        "fallback": False,
        "tokens": 0,
        "rows": [],
    }
    polish._store_jobs({"releases": {"9": {"items": [item], "tokens": 0, "running": False}}})
    polish._process_item(9, item)
    assert calls["n"] == 1
    assert polish_status(9)["label"] == "lista"
    assert polish_status(9)["tokens"] == 0
    polish.clear_polish_job(9)


def test_schedule_returns_before_the_model_answers(monkeypatch, tmp_path) -> None:
    import threading
    import time

    from app.services import legacy_polish as polish

    _enable(monkeypatch, tmp_path)
    started = threading.Event()
    release = threading.Event()

    def post(*_a, **_k):
        started.set()
        assert release.wait(2)
        return _response(_ok())

    monkeypatch.setattr("app.services.legacy_polish._post", post)
    monkeypatch.setattr("app.services.legacy_polish._stored_redaccion", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.legacy_polish._apply_saved", lambda *_a, **_k: None)
    case = _case()
    case.related_functionality = "WEBCL-1586"
    work = collect_polish_work([case], [_unit()])
    row = SimpleNamespace(id=41, test_case_id="QC-041", technical_epic="WEBCL-1586")
    started_at = time.monotonic()
    schedule_persisted_polish(41, [row], work)
    elapsed = time.monotonic() - started_at
    assert elapsed < 0.5
    assert polish_status(41)["label"] in {"pendiente", "en curso (0/1)"}
    assert started.wait(2)
    release.set()
    thread = polish._THREAD
    assert thread is not None
    thread.join(3)
    status = polish_status(41)
    assert status["label"] == "lista"
    assert status["epics"]["WEBCL-1586"] == "lista"
    polish.clear_polish_job(41)


def test_enqueue_clears_the_cancelled_release(monkeypatch, tmp_path) -> None:
    import threading

    from app.services import legacy_polish as polish

    _enable(monkeypatch, tmp_path)
    hold = threading.Event()

    def post(*_a, **_k):
        assert hold.wait(2)
        return _response(_ok())

    monkeypatch.setattr("app.services.legacy_polish._post", post)
    monkeypatch.setattr("app.services.legacy_polish._stored_redaccion", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.legacy_polish._apply_saved", lambda *_a, **_k: None)
    polish.clear_polish_job(77)
    assert "77" in polish._CANCELLED
    case = _case()
    case.related_functionality = "WEBCL-1586"
    row = SimpleNamespace(id=77, test_case_id="QC-077", technical_epic="WEBCL-1586")
    schedule_persisted_polish(77, [row], collect_polish_work([case], [_unit()]))
    assert "77" not in polish._CANCELLED
    assert polish_status(77)["label"].startswith("en curso")
    hold.set()
    assert polish._THREAD is not None
    polish._THREAD.join(3)
    assert polish_status(77)["label"] == "lista"
    polish.clear_polish_job(77)


def test_daily_limit_pauses_and_does_not_cache_the_rest(monkeypatch, tmp_path) -> None:
    import threading

    from app.services import legacy_polish as polish

    _enable(monkeypatch, tmp_path)
    gate = threading.Event()
    paused = threading.Event()
    state = {"tpd": True, "sleeps": 0}

    def sleep(*_a, **_k):
        state["sleeps"] += 1
        if state["sleeps"] == 1:
            paused.set()
            assert gate.wait(3)

    def post(*_a, **_k):
        if state["tpd"]:
            return httpx.Response(
                429,
                headers={"Retry-After": "30", "x-should-retry": "false"},
                json={"error": "tokens per day (TPD)"},
            )
        return _response(_ok())

    monkeypatch.setattr("app.services.legacy_polish.time.sleep", sleep)
    monkeypatch.setattr("app.services.legacy_polish._post", post)
    monkeypatch.setattr("app.services.legacy_polish._stored_redaccion", lambda *_a, **_k: None)
    monkeypatch.setattr("app.services.legacy_polish._apply_saved", lambda *_a, **_k: None)
    rows = [
        SimpleNamespace(id=81, test_case_id="QC-081", technical_epic="WEBCL-1"),
        SimpleNamespace(id=82, test_case_id="QC-082", technical_epic="WEBCL-1"),
    ]
    schedule_persisted_polish(81, rows, collect_polish_work([_case(), _case()], [_unit(), _unit()]))
    assert paused.wait(3)
    status = polish_status(81)
    assert status["label"].startswith("pausada – límite diario de Groq (reanuda ")
    assert status["done"] == 0
    cache_path = tmp_path / "cache.json"
    cached = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    assert all(item.get("status") != "fallback" for item in cached.values())
    state["tpd"] = False
    gate.set()
    assert polish._THREAD is not None
    polish._THREAD.join(4)
    done = polish_status(81)
    assert done["label"] == "lista"
    assert done["fallbacks"] == 0
    assert done["ia"] == 2
    cached = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cached
    assert all(item.get("status") == "ia" for item in cached.values())
    polish.clear_polish_job(81)


def test_fallback_model_takes_over_the_daily_limit(monkeypatch, tmp_path) -> None:
    _enable(monkeypatch, tmp_path)
    monkeypatch.setenv("QC_LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("QC_LLM_FALLBACK_MODEL", "openai/gpt-oss-20b")
    seen: list[str] = []

    def post(payload, *_a, **_k):
        seen.append(payload["model"])
        if payload["model"] == "openai/gpt-oss-120b":
            return httpx.Response(
                429,
                headers={"Retry-After": "10", "x-should-retry": "false"},
                json={"error": "tokens per day (TPD)"},
            )
        return _response(_ok())

    monkeypatch.setattr("app.services.legacy_polish._post", post)
    case = _case()
    polish_legacy_cases([case], [_unit()], GenerationStats())
    assert seen == ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    assert case.redaccion == "IA"


def test_server_error_is_not_cached(monkeypatch, tmp_path) -> None:
    _enable(monkeypatch, tmp_path)

    def post(*_a, **_k):
        return _response("", status=503)

    monkeypatch.setattr("app.services.legacy_polish._post", post)
    case = _case()
    polish_legacy_cases([case], [_unit()], GenerationStats())
    assert case.redaccion.startswith("Legacy (fallback:")
    cache_path = tmp_path / "cache.json"
    cached = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    assert cached == {}
