"""Excel export of persisted Test Cases: QC sheet + Zephyr-flat sheet."""

from __future__ import annotations

import io
import json
import re

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.formatting.rule import DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select

from app.models.test_case import TestCase


def _display_case_name(case: TestCase) -> str:
    name = case.test_case_name or ""
    device = (case.device or "").strip()
    if not device:
        return name
    for sep in (f" · {device}", f" - {device}", f" | {device}"):
        if name.endswith(sep):
            return name[: -len(sep)].rstrip()
    return name


_PRE_PREFIX = re.compile(r"^Precondición:\s*", re.IGNORECASE)
_MDP_PREFIX = re.compile(r"^MDP:\s*", re.IGNORECASE)
_JSON_OBJECT = re.compile(r"\{[^{}]+\}")
_SOURCE_LABEL = {
    "functionality": "Funcionalidad",
    "nco": "NCO",
    "tri": "TRI",
    "qa_bug": "QA Bug",
    "qc_bug": "QC Bug",
    "qa_qc": "QA/QC Bug",
}


def _source_label(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    return _SOURCE_LABEL.get(text, text)


def split_stored_test_data(raw: str | None) -> tuple[str, str, str]:
    """Split the persisted test_data blob the same way the case page does."""
    text = (raw or "").strip()
    if not text:
        return "", "", ""
    precondition = ""
    rows: list[tuple[str, str]] = []
    notes: list[str] = []
    seen: set[str] = set()

    def add_row(label: str, value: str) -> None:
        key = f"{label}\0{value}"
        if not label or key in seen:
            return
        seen.add(key)
        rows.append((label, value))

    def rows_from_json(blob: str) -> None:
        try:
            parsed = json.loads(blob)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            for label, value in parsed.items():
                add_row(str(label), "" if value is None else json.dumps(value) if not isinstance(value, str) else value)
            return
        for match in re.finditer(
            r"""["']([A-Za-z_][\w]*)["']\s*:\s*("[^"]*"|'[^']*'|true|false|null|-?\d+(?:\.\d+)?)""",
            blob,
        ):
            add_row(match.group(1), match.group(2).strip("\"'"))

    for block in (part.strip() for part in text.splitlines() if part.strip()):
        if not precondition and _PRE_PREFIX.match(block):
            precondition = _PRE_PREFIX.sub("", block).strip()
            continue
        if _MDP_PREFIX.match(block):
            value = _MDP_PREFIX.sub("", block).strip()
            if value:
                add_row("MDP", value)
            continue
        notes.append(block)
        for blob in _JSON_OBJECT.findall(block):
            rows_from_json(blob)

    compact = "\n".join(f"{label} = {value}" for label, value in rows)
    return precondition, compact, "\n".join(notes)


def primary_epic_key(case: TestCase) -> str:
    raw = ((case.component or case.technical_epic or case.hn_source or "Sin EPC").strip() or "Sin EPC")
    return (raw.split("|")[0] or "").strip() or "Sin EPC"


def _case_hours(case: TestCase) -> float:
    if case.estimation_hours is not None:
        return float(case.estimation_hours)
    return 0.0


def _is_executed(case: TestCase) -> bool:
    return _enum_value(case.status) != "UNEXECUTED"


def epic_progress_rows(cases: list[TestCase]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, float]] = {}
    for case in cases:
        key = primary_epic_key(case)
        row = grouped.setdefault(key, {"total": 0, "executed": 0, "hours": 0.0})
        row["total"] += 1
        if _is_executed(case):
            row["executed"] += 1
        row["hours"] += _case_hours(case)
    out: list[dict[str, object]] = []
    for key, stats in grouped.items():
        total = int(stats["total"])
        executed = int(stats["executed"])
        percent = 0.0 if total == 0 else round(executed * 1000 / total) / 10
        out.append(
            {
                "key": key,
                "total": total,
                "executed": executed,
                "percent": percent,
                "hours": round(stats["hours"] * 10) / 10,
            }
        )
    out.sort(key=lambda item: (-float(item["hours"]), str(item["key"])))
    return out


AVANCE_HEADERS = ["EPC", "Casos", "Ejecutados", "%", "Horas"]

QC_HEADERS = [
    "ID",
    "Nombre",
    "Componente",
    "Prioridad",
    "Origen",
    "Estado",
    "Test Steps",
    "Resultado Esperado",
    "Precondición",
    "Datos de prueba",
    "Evidencia",
    "Justificación",
    "Technical Epic",
    "Technical Story",
    "Scenario / origen",
    "Confianza IA",
    "Complejidad",
    "Esfuerzo QC (h)",
]

# Matches the FLAT Zephyr layout that CaseForge already imports (see services/imports.py).
ZEPHYR_HEADERS = [
    "Test Case ID",
    "Component",
    "Test Case Name",
    "Description",
    "User Type",
    "Step",
    "Test Step",
    "Expected Result",
    "Priority",
    "Test Type",
    "Status",
]

_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_HEADER_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
_CELL_FONT = Font(name="Calibri", size=11)
_THIN = Border(
    left=Side(style="thin", color="BFBFBF"),
    right=Side(style="thin", color="BFBFBF"),
    top=Side(style="thin", color="BFBFBF"),
    bottom=Side(style="thin", color="BFBFBF"),
)


_EXCEL_MAX_CELL = 32767


def _enum_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value or "")


def _excel_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    text = ILLEGAL_CHARACTERS_RE.sub("", str(value))
    if len(text) > _EXCEL_MAX_CELL:
        return text[: _EXCEL_MAX_CELL - 1]
    return text


def _steps_text(case: TestCase, expected: bool) -> str:
    lines = []
    for step in sorted(case.steps, key=lambda item: item.step_number):
        body = step.expected_result if expected else step.test_step
        lines.append(f"{step.step_number}. {body}")
    return "\n".join(lines)


def _style_header(sheet, headers: list[str], widths: list[int]) -> None:
    for index, header in enumerate(headers, start=1):
        cell = sheet.cell(1, index, header)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cell.border = _THIN
        sheet.column_dimensions[get_column_letter(index)].width = widths[index - 1]
    sheet.row_dimensions[1].height = 28
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"


def _style_cell(cell, wrap: bool = True) -> None:
    cell.font = _CELL_FONT
    cell.border = _THIN
    cell.alignment = Alignment(wrap_text=wrap, vertical="top")


def load_release_cases(db: Session, release_id: int) -> list[TestCase]:
    stmt = (
        select(TestCase)
        .where(TestCase.release_id == release_id)
        .options(selectinload(TestCase.steps))
        .order_by(TestCase.test_case_id)
    )
    return list(db.execute(stmt).scalars().all())


def build_test_cases_workbook(cases: list[TestCase]) -> bytes:
    workbook = Workbook()
    ordered = sorted(cases, key=lambda case: (primary_epic_key(case).lower(), case.test_case_id or ""))
    avance = workbook.active
    avance.title = "Avance"
    _style_header(avance, AVANCE_HEADERS, [18, 12, 14, 22, 12])
    progress = epic_progress_rows(ordered)
    total_cases = 0
    total_executed = 0
    total_hours = 0.0
    percent_format = '0.0"%"'
    for row_index, row in enumerate(progress, start=2):
        total_cases += int(row["total"])
        total_executed += int(row["executed"])
        total_hours += float(row["hours"])
        values = [row["key"], row["total"], row["executed"], float(row["percent"]), row["hours"]]
        for col, value in enumerate(values, start=1):
            cell = avance.cell(row_index, col, _excel_value(value))
            _style_cell(cell, wrap=False)
            if col == 4:
                cell.number_format = percent_format
    if progress:
        total_percent = 0.0 if total_cases == 0 else round(total_executed * 1000 / total_cases) / 10
        footer = ["Total", total_cases, total_executed, total_percent, round(total_hours * 10) / 10]
        footer_row = len(progress) + 2
        for col, value in enumerate(footer, start=1):
            cell = avance.cell(footer_row, col, _excel_value(value))
            _style_cell(cell, wrap=False)
            cell.font = Font(name="Calibri", size=11, bold=True)
            if col == 4:
                cell.number_format = percent_format
        avance.conditional_formatting.add(
            f"D2:D{footer_row}",
            DataBarRule(
                start_type="num",
                start_value=0,
                end_type="num",
                end_value=100,
                color="0D8B7D",
                showValue=True,
            ),
        )

    qc = workbook.create_sheet("Test Cases")
    _style_header(
        qc,
        QC_HEADERS,
        [10, 42, 16, 12, 16, 14, 40, 40, 28, 22, 28, 32, 16, 18, 28, 12, 14, 14],
    )
    for row_index, case in enumerate(ordered, start=2):
        precondition, compact_data, _notes = split_stored_test_data(case.test_data)
        values = [
            case.test_case_id,
            _display_case_name(case),
            case.component,
            _enum_value(case.priority),
            _source_label(case.source_type),
            _enum_value(case.status),
            _steps_text(case, expected=False),
            _steps_text(case, expected=True),
            precondition,
            compact_data,
            case.evidence or "",
            case.justification or "",
            case.technical_epic or "",
            case.technical_story or "",
            case.scenario_origin or "",
            case.confidence or "",
            case.complexity or "",
            "" if case.estimation_hours is None else float(case.estimation_hours),
        ]
        for col, value in enumerate(values, start=1):
            cell = qc.cell(row_index, col, _excel_value(value))
            _style_cell(cell)

    zephyr = workbook.create_sheet("Zephyr")
    _style_header(
        zephyr,
        ZEPHYR_HEADERS,
        [14, 18, 42, 28, 16, 8, 40, 40, 12, 14, 14],
    )
    zephyr_row = 2
    for case in ordered:
        steps = sorted(case.steps, key=lambda item: item.step_number)
        if not steps:
            steps = [None]
        description_parts = [part for part in (case.description, case.test_data) if part]
        description = "\n".join(description_parts)
        for step in steps:
            values = [
                case.test_case_id,
                case.component,
                _display_case_name(case),
                description,
                case.user_type or "",
                getattr(step, "step_number", 1) if step is not None else 1,
                getattr(step, "test_step", "") if step is not None else "",
                getattr(step, "expected_result", "") if step is not None else "",
                _enum_value(case.priority),
                _enum_value(case.test_type),
                _enum_value(case.status),
            ]
            for col, value in enumerate(values, start=1):
                cell = zephyr.cell(zephyr_row, col, _excel_value(value))
                _style_cell(cell)
            zephyr_row += 1

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
