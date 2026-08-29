"""Parsing and validation for the Test Case bulk-import pipeline.

Scope (Import -> Validate -> Preview stages only; Persist reuses the existing bulk-create
endpoint unchanged):

Two source layouts are supported, auto-detected from the header row:

- FLAT ("one row per Step", e.g. a Zephyr export): repeated Test Case-level columns on every
  step row, plus Step / Test Step / Expected Result columns that vary per row. Rows are grouped
  by Test Case ID (in order of first appearance).
- EMBEDDED ("one row per Test Case", e.g. the QC team's working "Casos de Prueba" sheet): Test
  Steps and Resultado Esperado are each a single cell containing a numbered list. Steps are
  split out of each cell independently. When both cells split into the SAME number of lines,
  they are paired positionally into real per-line Steps. When they don't match (verified on real
  data: happens in roughly a third of cases), pairing would be a guess -- so instead the whole
  Test Case imports as a single Step carrying the full original text of both cells verbatim, and
  a non-blocking warning is attached so the mismatch is visible in the preview rather than
  silently resolved.

Neither branch invents data: FLAT requires an exact column match; EMBEDDED never invents a
step/result pairing that isn't structurally supported by matching line counts.

"Datos de Prueba" (test data), if present, is appended to Description rather than dropped, since
it has no dedicated field on TestCase. Columns outside the CaseForge TestCase model (e.g.
Technical Epic, Technical Story, Día, Responsable, Evidencia/Notas) are ignored -- out of scope
for Sprint 2 (no Jira/scheduling integration yet).

Does not touch the database; duplicate-against-existing-release-data detection happens in the
router, since it needs a DB session.
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field

import openpyxl
from pydantic import ValidationError

from app.models.test_case import TestCasePriority, TestCaseType
from app.schemas.imports import ImportRowError
from app.schemas.test_case import TestCaseCreate
from app.schemas.test_step import TestStepCreate

_REQUIRED_FLAT_FIELDS = [
    "test_case_id",
    "component",
    "test_case_name",
    "user_type",
    "step",
    "test_step",
    "expected_result",
    "priority",
    "test_type",
    "status",
]

_REQUIRED_EMBEDDED_FIELDS = [
    "test_case_id",
    "component",
    "test_case_name",
    "user_type",
    "test_steps_embedded",
    "expected_result_embedded",
    "priority",
    "test_type",
    "status",
]

_HEADER_ALIASES = {
    "id": "test_case_id",
    "test case id": "test_case_id",
    "component": "component",
    "grupo funcional": "component",
    "test case name": "test_case_name",
    "caso de prueba": "test_case_name",
    "description": "description",
    "descripcion": "description",
    "user type": "user_type",
    "tipo de usuario": "user_type",
    "step": "step",
    "test step": "test_step",
    "test steps": "test_steps_embedded",
    "expected result": "expected_result",
    "resultado esperado": "expected_result_embedded",
    "datos de prueba": "test_data",
    "test data": "test_data",
    "priority": "priority",
    "prioridad": "priority",
    "test type": "test_type",
    "status": "status",
    "estado": "status",
}

_STATUS_ALIASES = {
    "UNEXECUTED": "UNEXECUTED",
    "PENDIENTE": "UNEXECUTED",
    "PENDING": "UNEXECUTED",
    "NO EJECUTADO": "UNEXECUTED",
    "PASS": "PASS",
    "PASA": "PASS",
    "APROBADO": "PASS",
    "APROBADA": "PASS",
    "FAIL": "FAIL",
    "FALLA": "FAIL",
    "FALLIDO": "FAIL",
    "FALLIDA": "FAIL",
    "BLOCKED": "BLOCKED",
    "BLOQUEADO": "BLOCKED",
    "BLOQUEADA": "BLOCKED",
    "N_A": "N_A",
    "N/A": "N_A",
    "NA": "N_A",
}

_PRIORITY_ALIASES = {member.value: member.value for member in TestCasePriority}
_TEST_TYPE_ALIASES = {member.value: member.value for member in TestCaseType}

_SHEET_NAME_PREFERENCE = ["casos de prueba", "zephyr export"]

_NUMBERED_LINE_SPLIT_RE = re.compile(r"\n(?=\s*\d+[.\)]\s*)")
_NUMBERED_PREFIX_RE = re.compile(r"^\s*\d+[.\)]\s*")


class ImportStructureError(Exception):
    """Raised when the file itself is unusable: wrong format, unknown columns, or bad sheet."""

    def __init__(self, messages: list[str]) -> None:
        super().__init__("; ".join(messages))
        self.messages = messages


@dataclass
class _RawRow:
    row_number: int  # 1-based, matches what a person would see if they opened the file
    values: dict[str, str]


@dataclass
class _CandidateGroup:
    test_case_id: str
    rows: list[_RawRow] = field(default_factory=list)


def _fold_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_header(raw_header: str) -> str | None:
    key = _fold_accents(str(raw_header)).strip().lower()
    key = " ".join(key.split())
    return _HEADER_ALIASES.get(key)


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _canonical_fields_from_header(header_row: list[object]) -> dict[int, str]:
    canonical_by_index: dict[int, str] = {}
    for index, raw_header in enumerate(header_row):
        if raw_header is None:
            continue
        canonical = _normalize_header(str(raw_header))
        if canonical is not None:
            canonical_by_index[index] = canonical
    return canonical_by_index


def _detect_format(fields: set[str]) -> str:
    flat_ok = all(f in fields for f in _REQUIRED_FLAT_FIELDS)
    embedded_ok = all(f in fields for f in _REQUIRED_EMBEDDED_FIELDS)
    if embedded_ok and not flat_ok:
        return "EMBEDDED"
    if flat_ok:
        return "FLAT"
    return "UNKNOWN"


def _missing_fields_message(fields: set[str]) -> str:
    missing_flat = [f for f in _REQUIRED_FLAT_FIELDS if f not in fields]
    missing_embedded = [f for f in _REQUIRED_EMBEDDED_FIELDS if f not in fields]
    closest = missing_flat if len(missing_flat) <= len(missing_embedded) else missing_embedded
    return f"Faltan columnas obligatorias en el archivo: {', '.join(closest)}."


def _read_csv_grid(content: bytes) -> list[list[object]]:
    text = content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def _read_xlsx_grid(content: bytes, sheet_name: str) -> list[list[object]]:
    workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    sheet = workbook[sheet_name]
    return [list(row) for row in sheet.iter_rows(values_only=True)]


def list_sheets(filename: str, content: bytes) -> list[dict]:
    """Inspect a file's sheet(s) and report the detected format of each, without parsing rows."""
    lower_name = filename.lower()
    if lower_name.endswith(".csv"):
        grid = _read_csv_grid(content)
        header = grid[0] if grid else []
        fmt = _detect_format(set(_canonical_fields_from_header(header).values()))
        return [{"name": "CSV", "format": fmt}]
    if lower_name.endswith((".xlsx", ".xlsm")):
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        results = []
        for sheet in workbook.worksheets:
            first_row = next(sheet.iter_rows(max_row=1, values_only=True), [])
            fmt = _detect_format(set(_canonical_fields_from_header(list(first_row)).values()))
            results.append({"name": sheet.title, "format": fmt})
        return results
    raise ImportStructureError(
        ["Formato de archivo no soportado. Solo se aceptan archivos .csv o .xlsx."]
    )


def _pick_sheet_name(available: list[dict], requested: str | None) -> str:
    if requested is not None:
        for entry in available:
            if entry["name"] == requested:
                return requested
        raise ImportStructureError([f"La hoja '{requested}' no existe en el archivo."])

    by_name = {entry["name"].strip().lower(): entry for entry in available}
    for preferred in _SHEET_NAME_PREFERENCE:
        if preferred in by_name and by_name[preferred]["format"] != "UNKNOWN":
            return by_name[preferred]["name"]
    for entry in available:
        if entry["format"] != "UNKNOWN":
            return entry["name"]
    return available[0]["name"]


def list_sheets_with_recommendation(filename: str, content: bytes) -> tuple[list[dict], str | None]:
    available = list_sheets(filename, content)
    try:
        recommended = _pick_sheet_name(available, None)
    except ImportStructureError:
        recommended = None
    return available, recommended


def _rows_from_grid(grid: list[list[object]]) -> tuple[str, list[_RawRow]]:
    if not grid:
        raise ImportStructureError(["El archivo/hoja está vacío."])

    header_row = grid[0]
    canonical_by_index = _canonical_fields_from_header(header_row)
    found_fields = set(canonical_by_index.values())
    fmt = _detect_format(found_fields)
    if fmt == "UNKNOWN":
        raise ImportStructureError([_missing_fields_message(found_fields)])

    raw_rows: list[_RawRow] = []
    for offset, data_row in enumerate(grid[1:], start=2):
        if all(cell is None or _clean(cell) == "" for cell in data_row):
            continue  # skip fully blank rows
        values: dict[str, str] = {}
        for index, canonical in canonical_by_index.items():
            cell_value = data_row[index] if index < len(data_row) else None
            values[canonical] = _clean(cell_value)
        raw_rows.append(_RawRow(row_number=offset, values=values))

    if not raw_rows:
        raise ImportStructureError(["El archivo/hoja no contiene filas de datos."])

    return fmt, raw_rows


def parse_file(
    filename: str, content: bytes, sheet_name: str | None = None
) -> tuple[str, list[_RawRow], str]:
    """Returns (detected_format, rows, resolved_sheet_name)."""
    lower_name = filename.lower()
    if lower_name.endswith(".csv"):
        grid = _read_csv_grid(content)
        fmt, rows = _rows_from_grid(grid)
        return fmt, rows, "CSV"
    if lower_name.endswith((".xlsx", ".xlsm")):
        available = list_sheets(filename, content)
        resolved_name = _pick_sheet_name(available, sheet_name)
        grid = _read_xlsx_grid(content, resolved_name)
        fmt, rows = _rows_from_grid(grid)
        return fmt, rows, resolved_name
    raise ImportStructureError(
        ["Formato de archivo no soportado. Solo se aceptan archivos .csv o .xlsx."]
    )


def _build_description(values: dict[str, str]) -> str | None:
    description = values.get("description", "")
    test_data = values.get("test_data", "")
    parts = [part for part in (description, test_data and f"Datos de prueba: {test_data}") if part]
    return "\n".join(parts) if parts else None


def _resolve_priority(raw: str) -> str | None:
    return _PRIORITY_ALIASES.get(raw.strip().upper())


def _resolve_test_type(raw: str) -> str | None:
    raw = raw.strip().upper()
    if raw == "":
        return TestCaseType.FUNCTIONAL.value
    return _TEST_TYPE_ALIASES.get(raw)


def _resolve_status(raw: str) -> str | None:
    return _STATUS_ALIASES.get(raw.strip().upper())


def _split_numbered_cell(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    parts = _NUMBERED_LINE_SPLIT_RE.split(text)
    return [_NUMBERED_PREFIX_RE.sub("", p).strip() for p in parts if p.strip()]


# ---------------------------------------------------------------------------
# FLAT format: one row per Step, grouped by Test Case ID
# ---------------------------------------------------------------------------


def _group_rows(rows: list[_RawRow]) -> dict[str, _CandidateGroup]:
    groups: dict[str, _CandidateGroup] = {}
    for row in rows:
        test_case_id = row.values.get("test_case_id", "")
        if test_case_id == "":
            continue  # reported separately as a required-field error below
        groups.setdefault(test_case_id, _CandidateGroup(test_case_id=test_case_id)).rows.append(row)
    return groups


def _validate_flat_group(group: _CandidateGroup) -> tuple[TestCaseCreate | None, ImportRowError | None]:
    row_numbers = [r.row_number for r in group.rows]

    metadata_fields = ["component", "test_case_name", "user_type", "priority", "test_type", "status"]
    metadata_values = {f: {r.values.get(f, "") for r in group.rows} for f in metadata_fields}
    inconsistent = [f for f, values in metadata_values.items() if len(values) > 1 and f != "user_type"]
    if inconsistent:
        return None, ImportRowError(
            test_case_id=group.test_case_id,
            row_numbers=row_numbers,
            message=(
                f"Test Case '{group.test_case_id}': el campo {', '.join(inconsistent)} "
                "tiene valores distintos entre sus filas de Step."
            ),
        )

    first = group.rows[0].values
    component = first.get("component", "")
    test_case_name = first.get("test_case_name", "")
    if not component or not test_case_name:
        return None, ImportRowError(
            test_case_id=group.test_case_id,
            row_numbers=row_numbers,
            message=f"Test Case '{group.test_case_id}': Component y Test Case Name son obligatorios.",
        )

    priority = _resolve_priority(first.get("priority", ""))
    if priority is None:
        return None, ImportRowError(
            test_case_id=group.test_case_id,
            row_numbers=row_numbers,
            message=(
                f"Test Case '{group.test_case_id}': Priority '{first.get('priority', '')}' no es "
                "válido (solo se acepta Blocker o Critical)."
            ),
        )

    test_type = _resolve_test_type(first.get("test_type", ""))
    if test_type is None:
        return None, ImportRowError(
            test_case_id=group.test_case_id,
            row_numbers=row_numbers,
            message=f"Test Case '{group.test_case_id}': Test Type '{first.get('test_type', '')}' no es válido.",
        )

    status = _resolve_status(first.get("status", ""))
    if status is None:
        return None, ImportRowError(
            test_case_id=group.test_case_id,
            row_numbers=row_numbers,
            message=f"Test Case '{group.test_case_id}': Status '{first.get('status', '')}' no es válido.",
        )

    steps: list[TestStepCreate] = []
    for row in group.rows:
        step_raw = row.values.get("step", "")
        test_step = row.values.get("test_step", "")
        expected_result = row.values.get("expected_result", "")
        if not step_raw or not test_step or not expected_result:
            return None, ImportRowError(
                test_case_id=group.test_case_id,
                row_numbers=[row.row_number],
                message=(
                    f"Test Case '{group.test_case_id}', fila {row.row_number}: Step, Test Step y "
                    "Expected Result son obligatorios."
                ),
            )
        try:
            step_number = int(float(step_raw))
        except ValueError:
            return None, ImportRowError(
                test_case_id=group.test_case_id,
                row_numbers=[row.row_number],
                message=f"Test Case '{group.test_case_id}', fila {row.row_number}: Step '{step_raw}' no es un número.",
            )
        steps.append(
            TestStepCreate(step_number=step_number, test_step=test_step, expected_result=expected_result)
        )

    step_numbers = [s.step_number for s in steps]
    if len(step_numbers) != len(set(step_numbers)):
        return None, ImportRowError(
            test_case_id=group.test_case_id,
            row_numbers=row_numbers,
            message=f"Test Case '{group.test_case_id}': hay números de Step repetidos.",
        )
    steps.sort(key=lambda s: s.step_number)

    try:
        test_case = TestCaseCreate(
            test_case_id=group.test_case_id,
            component=component,
            test_case_name=test_case_name,
            description=_build_description(first),
            user_type=first.get("user_type") or None,
            priority=priority,
            test_type=test_type,
            status=status,
            steps=steps,
        )
    except ValidationError as exc:
        return None, ImportRowError(
            test_case_id=group.test_case_id,
            row_numbers=row_numbers,
            message=f"Test Case '{group.test_case_id}': {exc.errors()[0]['msg']}",
        )

    return test_case, None


def _validate_flat_rows(
    rows: list[_RawRow],
) -> tuple[list[TestCaseCreate], list[ImportRowError]]:
    valid: list[TestCaseCreate] = []
    errors: list[ImportRowError] = []

    missing_id_rows = [r.row_number for r in rows if r.values.get("test_case_id", "") == ""]
    if missing_id_rows:
        errors.append(
            ImportRowError(
                test_case_id=None,
                row_numbers=missing_id_rows,
                message="Filas sin Test Case ID (obligatorio).",
            )
        )

    for group in _group_rows(rows).values():
        test_case, error = _validate_flat_group(group)
        if error is not None:
            errors.append(error)
        elif test_case is not None:
            valid.append(test_case)

    return valid, errors


# ---------------------------------------------------------------------------
# EMBEDDED format: one row per Test Case, Steps/Expected Result in one cell each
# ---------------------------------------------------------------------------


def _validate_embedded_row(
    row: _RawRow, seen_ids: dict[str, int]
) -> tuple[TestCaseCreate | None, ImportRowError | None, ImportRowError | None]:
    """Returns (test_case_or_None, blocking_error_or_None, non_blocking_warning_or_None)."""
    values = row.values
    test_case_id = values.get("test_case_id", "")

    if test_case_id == "":
        return None, ImportRowError(
            test_case_id=None, row_numbers=[row.row_number], message=f"Fila {row.row_number}: falta Test Case ID."
        ), None

    if test_case_id in seen_ids:
        return None, ImportRowError(
            test_case_id=test_case_id,
            row_numbers=[seen_ids[test_case_id], row.row_number],
            message=(
                f"Test Case ID '{test_case_id}' está duplicado dentro del archivo "
                f"(filas {seen_ids[test_case_id]} y {row.row_number})."
            ),
        ), None
    seen_ids[test_case_id] = row.row_number

    component = values.get("component", "")
    test_case_name = values.get("test_case_name", "")
    steps_text = values.get("test_steps_embedded", "")
    expected_text = values.get("expected_result_embedded", "")
    if not component or not test_case_name or not steps_text or not expected_text:
        return None, ImportRowError(
            test_case_id=test_case_id,
            row_numbers=[row.row_number],
            message=(
                f"Test Case '{test_case_id}': Component, Test Case Name, Test Steps y "
                "Resultado Esperado son obligatorios."
            ),
        ), None

    priority = _resolve_priority(values.get("priority", ""))
    if priority is None:
        return None, ImportRowError(
            test_case_id=test_case_id,
            row_numbers=[row.row_number],
            message=(
                f"Test Case '{test_case_id}': Priority '{values.get('priority', '')}' no es "
                "válido (solo se acepta Blocker o Critical)."
            ),
        ), None

    test_type = _resolve_test_type(values.get("test_type", ""))
    if test_type is None:
        return None, ImportRowError(
            test_case_id=test_case_id,
            row_numbers=[row.row_number],
            message=f"Test Case '{test_case_id}': Test Type '{values.get('test_type', '')}' no es válido.",
        ), None

    status = _resolve_status(values.get("status", ""))
    if status is None:
        return None, ImportRowError(
            test_case_id=test_case_id,
            row_numbers=[row.row_number],
            message=f"Test Case '{test_case_id}': Status '{values.get('status', '')}' no es válido.",
        ), None

    step_lines = _split_numbered_cell(steps_text)
    expected_lines = _split_numbered_cell(expected_text)

    warning: ImportRowError | None = None
    if step_lines and len(step_lines) == len(expected_lines):
        # Line counts align: split into real, individually-paired Steps.
        steps = [
            TestStepCreate(step_number=i + 1, test_step=s, expected_result=e)
            for i, (s, e) in enumerate(zip(step_lines, expected_lines))
        ]
    else:
        # Line counts don't align (or nothing was numbered): importing this as N/M mismatched
        # pairs would mean inventing which action produced which result. Per product decision,
        # we never guess that pairing -- the whole cell content imports as a single Step, and a
        # warning surfaces the mismatch instead of resolving it silently.
        steps = [
            TestStepCreate(step_number=1, test_step=steps_text.strip(), expected_result=expected_text.strip())
        ]
        if len(step_lines) != len(expected_lines):
            warning = ImportRowError(
                test_case_id=test_case_id,
                row_numbers=[row.row_number],
                message=(
                    f"Test Case '{test_case_id}': Test Steps ({len(step_lines)} líneas) y "
                    f"Resultado Esperado ({len(expected_lines)} líneas) no coinciden en cantidad; "
                    "se importó como un solo Step con el texto completo de ambas celdas."
                ),
            )

    try:
        test_case = TestCaseCreate(
            test_case_id=test_case_id,
            component=component,
            test_case_name=test_case_name,
            description=_build_description(values),
            user_type=values.get("user_type") or None,
            priority=priority,
            test_type=test_type,
            status=status,
            steps=steps,
        )
    except ValidationError as exc:
        return None, ImportRowError(
            test_case_id=test_case_id,
            row_numbers=[row.row_number],
            message=f"Test Case '{test_case_id}': {exc.errors()[0]['msg']}",
        ), None

    return test_case, None, warning


def _validate_embedded_rows(
    rows: list[_RawRow],
) -> tuple[list[TestCaseCreate], list[ImportRowError], list[ImportRowError]]:
    valid: list[TestCaseCreate] = []
    errors: list[ImportRowError] = []
    warnings: list[ImportRowError] = []
    seen_ids: dict[str, int] = {}

    for row in rows:
        test_case, error, warning = _validate_embedded_row(row, seen_ids)
        if error is not None:
            errors.append(error)
        elif test_case is not None:
            valid.append(test_case)
            if warning is not None:
                warnings.append(warning)

    return valid, errors, warnings


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate_rows(
    rows: list[_RawRow], fmt: str
) -> tuple[list[TestCaseCreate], list[ImportRowError], list[ImportRowError]]:
    if fmt == "EMBEDDED":
        return _validate_embedded_rows(rows)
    valid, errors = _validate_flat_rows(rows)
    return valid, errors, []
