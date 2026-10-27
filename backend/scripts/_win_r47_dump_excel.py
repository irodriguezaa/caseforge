"""One-shot: dump WINCL-609/619/636 and Excel of the 27 WIN R47 EPCs. Not a product entrypoint."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.schemas.case_generation import GenerationStats
from app.services.case_persistence import (
    _join_test_data,
    _persist_applicability,
    _scenario_origin,
    next_test_case_id,
)
from app.services.gherkin_coverage import candidates_from_jira_artifacts, extract_gherkin_blocks
from app.services import jira_generation as jira_generation
from app.services.jira_generation import fetch_artifacts_for_keys

jira_generation._GENERATION_TIMEOUT = 90.0
from app.services.qc_effort import classify_complexity, estimate_case_hours
from app.services.qc_eligibility import evaluate_scenario, result_clauses
from app.services.test_case_export import build_test_cases_workbook

WIN_EPCS = [
    "WINCL-2272",
    "WINCL-2281",
    "WINCL-2306",
    "WINCL-568",
    "WINCL-570",
    "WINCL-587",
    "WINCL-607",
    "WINCL-609",
    "WINCL-619",
    "WINCL-630",
    "WINCL-632",
    "WINCL-636",
    "WINCL-640",
    "WINCL-643",
    "WINCL-646",
    "WINCL-650",
    "WINCL-661",
    "WINCL-672",
    "WINCL-677",
    "WINCL-681",
    "WINCL-687",
    "WINCL-693",
    "WINCL-697",
    "WINCL-704",
    "WINCL-708",
    "WINCL-717",
    "WINCL-757",
]
DUMP_KEYS = ("WINCL-609", "WINCL-619", "WINCL-636")
DUMP_PATH = Path(__file__).resolve().parents[1] / "tests/golden/jira_win_release47.json"
EXCEL_PATH = Path.home() / "Downloads/CaseForge_Estimación_WINCL_Sprint_Release47_TestCases.xlsx"
TABLE_PATH = Path.home() / "Downloads/WINCL_609_619_636_pendiente_QC.json"


def _dump_shape(artifact: dict) -> dict:
    children = []
    for child in artifact.get("children") or []:
        children.append(
            {
                "key": child.get("key"),
                "issuetype": child.get("issuetype") or "",
                "summary": child.get("summary") or "",
                "description": child.get("description") or "",
                "acceptance_criteria": child.get("acceptance_criteria") or "",
            }
        )
    return {
        "key": artifact.get("key"),
        "issuetype": artifact.get("issuetype") or "",
        "summary": artifact.get("summary") or "",
        "description": artifact.get("description") or "",
        "acceptance_criteria": artifact.get("acceptance_criteria") or "",
        "children": children,
    }


def _matrix_cases(used_ids: list[str]) -> list:
    try:
        from app.db import SessionLocal
        from app.services.qc_matrix_selection import select_matrix_cases
    except Exception as exc:
        print("matrix import skip", exc, flush=True)
        return []
    db = SessionLocal()
    try:
        preview = select_matrix_cases(
            db,
            platform="WIN/XBOX",
            validation_type="Regresión completa",
            touched_modules=None,
            template_values=None,
            raw_analysis=None,
            pinned_version_id=None,
        )
    except Exception as exc:
        print("matrix query skip", exc, flush=True)
        return []
    finally:
        db.close()
    rows = list(preview.get("cases") or [])
    print("matrix", preview.get("note") or "", "count", len(rows), flush=True)
    out = []
    used = list(used_ids)
    for index, item in enumerate(rows, start=1):
        actions = [ln.strip() for ln in str(item.get("steps") or "").splitlines() if ln.strip()]
        expecteds = [ln.strip() for ln in str(item.get("expected") or "").splitlines() if ln.strip()]
        if not actions:
            continue
        if len(expecteds) < len(actions):
            expecteds = expecteds + [expecteds[-1] if expecteds else ""] * (len(actions) - len(expecteds))
        label = f"RC-{index:03d}"
        while label in used:
            index += 1
            label = f"RC-{index:03d}"
        used.append(label)
        out.append(
            SimpleNamespace(
                test_case_id=label,
                test_case_name=item.get("title") or label,
                component="WINCL",
                technical_epic="WINCL",
                hn_source=None,
                status="UNEXECUTED",
                estimation_hours=0.2,
                priority="HIGH",
                test_type="FUNCTIONAL",
                source_type="qc_matrix",
                user_type=None,
                test_data=None,
                evidence="",
                justification="Matriz regresiva según alcance Regresión completa",
                technical_story=item.get("base_id"),
                scenario_origin=item.get("module_key"),
                confidence=None,
                complexity="MEDIA",
                description=item.get("title"),
                device="WIN/XBOX",
                applicability_reason=None,
                steps=[
                    SimpleNamespace(
                        step_number=n,
                        test_step=action,
                        expected_result=expecteds[n - 1] if n - 1 < len(expecteds) else "",
                    )
                    for n, action in enumerate(actions, start=1)
                ],
            )
        )
    return out


def _cases_from_candidates(candidates, ledger):
    used: list[str] = []
    cases = []
    name_to_id: dict[str, str] = {}
    for candidate in candidates:
        if not candidate.steps and (candidate.applicability or "") != "na_ambiente":
            continue
        label = next_test_case_id(used)
        used.append(label)
        name_to_id[candidate.name] = label
        complexity = classify_complexity(candidate)
        priority = candidate.priority or "CRITICAL"
        cases.append(
            SimpleNamespace(
                test_case_id=label,
                test_case_name=candidate.name,
                component=(candidate.related_functionality or "")[:150],
                technical_epic=candidate.related_functionality,
                hn_source=None,
                status="UNEXECUTED",
                estimation_hours=estimate_case_hours(priority, complexity),
                priority=priority,
                test_type="FUNCTIONAL",
                source_type=candidate.source_type or "functionality",
                user_type=candidate.user_type,
                test_data=_join_test_data(candidate),
                evidence=candidate.evidence,
                justification=candidate.justification,
                technical_story=candidate.related_jira,
                scenario_origin=_scenario_origin(candidate),
                confidence=candidate.confidence,
                complexity=complexity,
                description=candidate.description,
                device=candidate.device,
                applicability_reason=_persist_applicability(candidate),
                steps=[
                    SimpleNamespace(
                        step_number=step.step_number,
                        test_step=step.action,
                        expected_result=step.expected_result,
                    )
                    for step in candidate.steps
                ],
            )
        )
    for row in ledger:
        ref = str(row.get("case_id") or "").split(";")[0].strip()
        if ref in name_to_id:
            row["case_id"] = name_to_id[ref]
    return cases, ledger


def _then_for(artifacts, story: str, scenario: str) -> str:
    for epic in artifacts:
        rows = [epic, *(epic.get("children") or [])]
        for item in rows:
            if item.get("key") != story:
                continue
            for block in extract_gherkin_blocks(
                item.get("description") or "", item.get("acceptance_criteria") or ""
            ):
                if (block.get("title") or "").strip() == (scenario or "").strip():
                    return " // ".join(result_clauses(block.get("body") or ""))
    return ""


def _doubt_why(elig, motivo: str) -> str:
    parts: list[str] = []
    if elig.actor_ok is None:
        parts.append("actor en duda (When/título no nombra usuario ni rol técnico)")
    elif elig.actor_ok is False:
        parts.append("actor no es usuario final")
    if elig.surface_ok is None:
        parts.append("superficie en duda (Then no nombra pantalla/flujo reconocible ni resultado visible)")
    elif elig.surface_ok is False:
        parts.append("superficie no visible")
    if elig.device_ok is None:
        parts.append(
            "verificación en duda (Then no es observable en dispositivo ni claramente técnico)"
        )
    elif elig.device_ok is False:
        parts.append("resultado no verificable en dispositivo")
    if "sin acción de usuario" in (motivo or "").lower():
        parts.append("pasó el filtro de visibilidad pero Jira no trae acción de tester conjugable")
    if not parts:
        parts.append(motivo or "duda: no hay actor de usuario, superficie y verificación de dispositivo a la vez")
    return "; ".join(parts)


def main() -> None:
    print("fetch", len(WIN_EPCS), "epics…", flush=True)
    artifacts = fetch_artifacts_for_keys(WIN_EPCS)
    got = [row.get("key") for row in artifacts]
    missing = [key for key in WIN_EPCS if key not in got]
    print("fetched", len(artifacts), "missing", missing, flush=True)

    dump = [_dump_shape(row) for row in artifacts if row.get("key") in DUMP_KEYS]
    dump.sort(key=lambda row: DUMP_KEYS.index(row["key"]))
    DUMP_PATH.write_text(json.dumps(dump, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("dump", DUMP_PATH, "bytes", DUMP_PATH.stat().st_size, flush=True)

    stats = GenerationStats()
    candidates = candidates_from_jira_artifacts(
        artifacts, "WINCL Release 47.pdf", [], lambda *_a: None, stats=stats
    )
    cases, ledger = _cases_from_candidates(candidates, stats.scenario_ledger)
    cases.extend(_matrix_cases(used_ids=[c.test_case_id for c in cases]))
    payload = build_test_cases_workbook(
        cases,
        scope_keys=list(WIN_EPCS),
        scenario_ledger=ledger,
    )
    EXCEL_PATH.write_bytes(payload)
    print("excel", EXCEL_PATH, "cases", len(cases), "bytes", len(payload), flush=True)

    three = [row for row in artifacts if row.get("key") in DUMP_KEYS]
    pending = []
    for row in ledger:
        if str(row.get("estado") or "") != "pendiente de revisión QC":
            continue
        if str(row.get("epic") or "") not in DUMP_KEYS and str(row.get("story") or "") not in {
            child.get("key") for epic in three for child in (epic.get("children") or [])
        } | set(DUMP_KEYS):
            continue
        story = str(row.get("story") or "")
        scenario = str(row.get("scenario") or "")
        then = _then_for(three, story, scenario)
        body = ""
        summary = ""
        for epic in three:
            for item in [epic, *(epic.get("children") or [])]:
                if item.get("key") == story:
                    summary = item.get("summary") or ""
                    for block in extract_gherkin_blocks(
                        item.get("description") or "", item.get("acceptance_criteria") or ""
                    ):
                        if (block.get("title") or "").strip() == scenario.strip():
                            body = block.get("body") or ""
                            break
        elig = evaluate_scenario(scenario, body, summary)
        pending.append(
            {
                "historia": story,
                "escenario": scenario,
                "then": then,
                "criterio": _doubt_why(elig, str(row.get("motivo") or "")),
                "motivo_ledger": row.get("motivo") or "",
                "actor_ok": elig.actor_ok,
                "surface_ok": elig.surface_ok,
                "device_ok": elig.device_ok,
            }
        )
    TABLE_PATH.write_text(json.dumps(pending, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("pending", len(pending), TABLE_PATH, flush=True)


if __name__ == "__main__":
    main()
