"""Genera el Excel de Legacy y marca lo que se pierde.

Uso (desde backend/):
    python scripts/check_legacy_excel.py /tmp/qcpulse_web_epics.json
Sale con código 1 si algún contador es mayor que 0.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from openpyxl import Workbook, load_workbook

from app.schemas.case_generation import GenerationStats
from app.services.gherkin_coverage import build_coverage_inventory, candidates_from_jira_artifacts
from app.services.legacy_excel_check import audit_cases
from app.services.legacy_qc import fold

OUT = Path("/tmp/qcpulse_legacy_check.xlsx")
REVIEW = (
    "usuario anonimo con contenido no contratado",
    "identificar contenido bloqueado",
    "eliminacion del metodo de pago telcel con suscripciones",
    "navegacion al selector de planes",
    "ajustar distancia entre el menu",
)


def _cell(value: str) -> str:
    return (value or "")[:32000]


def main() -> int:
    source = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/qcpulse_web_epics.json")
    artifacts = json.loads(source.read_text(encoding="utf-8"))
    stats = GenerationStats()
    units = build_coverage_inventory(artifacts, "web.json")
    cases = candidates_from_jira_artifacts(artifacts, "web.json", [], lambda *_args: None, stats=stats)
    by_id = {unit.coverage_id: unit for unit in units}
    origins: dict[str, str] = {}
    book = Workbook()
    sheet = book.active
    sheet.title = "Test Cases"
    sheet.append(
        [
            "Nombre",
            "Test Steps",
            "Resultado Esperado",
            "Precondición",
            "Technical Story",
            "Scenario / origen",
            "Variantes",
        ]
    )
    rows = []
    for case in cases:
        covered = [by_id[cid] for cid in (case.covers or []) if cid in by_id]
        scenario = covered[0].scenario if covered else ""
        body = "\n".join(unit.body or "" for unit in covered)
        steps = "\n".join(f"{step.step_number}. {step.action}" for step in case.steps)
        results = "\n".join(
            f"{step.step_number}. {step.expected_result or ''}" for step in case.steps
        )
        sheet.append(
            [
                _cell(case.name or ""),
                _cell(steps),
                _cell(results),
                _cell(case.precondition or ""),
                _cell(covered[0].story_key if covered else ""),
                _cell(scenario or ""),
                _cell(case.variant_table or ""),
            ]
        )
        origins[case.name or ""] = body
        rows.append(
            {
                "name": case.name or "",
                "steps": steps,
                "results": results,
                "precondition": case.precondition or "",
                "scenario": scenario or "",
            }
        )
    ledger = book.create_sheet("Escenarios de Jira")
    ledger.append(["Historia", "Escenario", "Estado", "ID del caso", "Motivo"])
    for item in stats.scenario_ledger:
        ledger.append(
            [
                item.get("story") or "",
                item.get("scenario") or "",
                item.get("estado") or "",
                item.get("case_id") or "",
                _cell(str(item.get("motivo") or "")),
            ]
        )
    book.save(OUT)
    loaded = load_workbook(OUT, read_only=True)
    read_rows = []
    for record in loaded["Test Cases"].iter_rows(min_row=2, values_only=True):
        read_rows.append(
            {
                "name": record[0] or "",
                "steps": record[1] or "",
                "results": record[2] or "",
                "precondition": record[3] or "",
                "scenario": record[5] or "",
                "variants": record[6] or "",
            }
        )
    issues = audit_cases(read_rows, origins)
    errors = [
        str(item[4])
        for item in loaded["Escenarios de Jira"].iter_rows(min_row=2, values_only=True)
        if item and str(item[2] or "") == "error"
    ]
    loaded.close()
    labels = {
        "then_no_reflejado": "Then no reflejado",
        "resultado_vacio": "resultado vacío",
        "entrada_duplicada": "pasos de entrada duplicados",
        "titulo_ajeno": "títulos que no vienen del escenario",
        "palabra_tecnica": "palabras técnicas",
        "primera_persona": "primera persona",
        "texto_cortado": "texto cortado",
        "resultado_eco": "resultado eco",
        "verificar_repetido": "pasos Verificar el resultado repetidos",
        "acciones_sin_resultado": "acciones seguidas sin resultado intermedio",
        "llave_o_codigo_en_pre": "llave o código de error en precondición",
        "precondicion_vacia": "precondición Y. o vacía",
    }
    print(f"casos={len(read_rows)} excel={OUT}")
    failed = 0
    for key, label in labels.items():
        found = issues[key]
        print(f"{label}: {len(found)}")
        for sample in found[:8]:
            print(f"  - {sample}")
        failed += len(found)
    print(f"error en Escenarios de Jira: {len(errors)}")
    for sample in errors[:8]:
        print(f"  - {sample}")
    failed += len(errors)
    print("--- revisión ---")
    for record in read_rows:
        folded = fold(str(record["name"]))
        if not any(title in folded for title in REVIEW):
            continue
        print(record["name"])
        print("PRE:", record["precondition"])
        print("VAR:", record.get("variants") or "")
        print(record["steps"])
        print(record["results"])
        print()
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
