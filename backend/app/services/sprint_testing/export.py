"""Excel of execution issues and 2-slide executive PPTX for Sprint Testing."""

from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from app.schemas.sprint_testing import ExecutionIssueRow, SprintTestingRead

ISSUE_HEADERS = ["Key", "Summary", "Description", "Estado", "Prioridad", "Dispositivo"]

_HEADER_FILL = PatternFill("solid", fgColor="1B2A49")
_HEADER_FONT = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
_CELL_FONT = Font(name="Calibri", size=11)
_THIN = Border(
    left=Side(style="thin", color="BFBFBF"),
    right=Side(style="thin", color="BFBFBF"),
    top=Side(style="thin", color="BFBFBF"),
    bottom=Side(style="thin", color="BFBFBF"),
)
_EXCEL_MAX_CELL = 32767

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
NAVY = RGBColor(0x1B, 0x2A, 0x49)
TEAL = RGBColor(0x0D, 0x8B, 0x7D)
GOLD = RGBColor(0xE8, 0x9F, 0x1F)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
OFF = RGBColor(0xF4, 0xF8, 0xFB)
MUTED = RGBColor(0x6B, 0x7A, 0x8D)
BODY = RGBColor(0x3A, 0x47, 0x5C)
RED = RGBColor(0xC4, 0x44, 0x2E)


def _excel_value(value: object) -> str:
    text = ILLEGAL_CHARACTERS_RE.sub("", str(value or ""))
    if len(text) > _EXCEL_MAX_CELL:
        return text[: _EXCEL_MAX_CELL - 1]
    return text


def build_issues_workbook(rows: list[ExecutionIssueRow]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Issues"
    for index, header in enumerate(ISSUE_HEADERS, start=1):
        cell = sheet.cell(1, index, header)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cell.border = _THIN
    widths = [16, 42, 55, 18, 16, 18]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.row_dimensions[1].height = 28
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(ISSUE_HEADERS))}1"

    for row_index, row in enumerate(rows, start=2):
        values = [row.key, row.summary, row.description, row.status, row.priority, row.device]
        for col, value in enumerate(values, start=1):
            cell = sheet.cell(row_index, col, _excel_value(value))
            cell.font = _CELL_FONT
            cell.border = _THIN
            cell.alignment = Alignment(wrap_text=col in {2, 3}, vertical="top")
        sheet.row_dimensions[row_index].height = 36

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _add_rect(slide: Any, left: float, top: float, width: float, height: float, fill: RGBColor) -> Any:
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def _add_text(
    slide: Any,
    left: float,
    top: float,
    width: float,
    height: float,
    text: str,
    *,
    size: int,
    bold: bool = False,
    color: RGBColor = WHITE,
    align: PP_ALIGN = PP_ALIGN.LEFT,
) -> None:
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    run = paragraph.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Calibri"


def _sum_bucket(values: dict[str, int]) -> int:
    return sum(values.values())


def _closed_pct(open_count: int, closed_count: int) -> str:
    total = open_count + closed_count
    if total <= 0:
        return "—"
    return f"{round(closed_count * 100 / total, 1)}%"


def _set_cell(
    cell: Any,
    text: str,
    *,
    size: int = 11,
    bold: bool = False,
    color: RGBColor = BODY,
    fill: RGBColor | None = None,
    align: PP_ALIGN = PP_ALIGN.CENTER,
) -> None:
    cell.text = text
    frame = cell.text_frame
    frame.word_wrap = True
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    run = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = "Calibri"
    if fill is not None:
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill


def _kpi_card(slide: Any, left: float, top: float, width: float, value: str, label: str, accent: RGBColor) -> None:
    _add_rect(slide, left, top, width, Inches(1.05), OFF)
    _add_rect(slide, left, top, Inches(0.08), Inches(1.05), accent)
    _add_text(slide, left + Inches(0.18), top + Inches(0.12), width - Inches(0.28), Inches(0.48), value, size=22, bold=True, color=NAVY)
    _add_text(slide, left + Inches(0.18), top + Inches(0.58), width - Inches(0.28), Inches(0.32), label, size=11, color=MUTED)


def _fill_table_header(table: Any, headers: list[str]) -> None:
    for index, header in enumerate(headers):
        _set_cell(table.cell(0, index), header, size=10, bold=True, color=WHITE, fill=NAVY)


def build_executive_pptx(payload: SprintTestingRead) -> bytes:
    presentation = Presentation()
    presentation.slide_width = SLIDE_W
    presentation.slide_height = SLIDE_H
    blank = presentation.slide_layouts[6]
    _build_epics_slide(presentation.slides.add_slide(blank), payload)
    _build_issues_slide(presentation.slides.add_slide(blank), payload)
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def _slide_chrome(slide: Any, payload: SprintTestingRead, kicker: str) -> None:
    _add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.92), NAVY)
    _add_text(slide, Inches(0.4), Inches(0.12), Inches(8.5), Inches(0.36), kicker, size=12, color=TEAL)
    _add_text(
        slide,
        Inches(0.4),
        Inches(0.4),
        Inches(8.5),
        Inches(0.42),
        f"{payload.sprint.label}  ·  {payload.swf}",
        size=22,
        bold=True,
    )
    _add_text(
        slide,
        Inches(0.4),
        Inches(7.18),
        Inches(12.5),
        Inches(0.24),
        "QCPulse · Sprint Testing",
        size=10,
        color=MUTED,
    )


def _build_epics_slide(slide: Any, payload: SprintTestingRead) -> None:
    _slide_chrome(slide, payload, "Technical Epics")
    open_count = sum(row.open for row in payload.programs)
    closed_count = sum(row.closed_total for row in payload.programs)
    cards = [
        (str(payload.technical_epic_count), "Technical Epics", TEAL),
        (str(open_count), "Abiertos", GOLD),
        (str(closed_count), "Cerrados", TEAL),
        (_closed_pct(open_count, closed_count), "% cerrado", NAVY),
    ]
    card_w = Inches(2.95)
    gap = Inches(0.18)
    start = Inches(0.4)
    for index, (value, label, accent) in enumerate(cards):
        _kpi_card(slide, start + index * (card_w + gap), Inches(1.12), card_w, value, label, accent)

    headers = ["Dispositivo", "Desarrollo", "Testing", "Cerrado", "To Do", "Abierto", "Total"]
    rows = payload.programs
    table_rows = max(len(rows) + 1, 2)
    table_shape = slide.shapes.add_table(
        table_rows,
        len(headers),
        Inches(0.4),
        Inches(2.4),
        Inches(12.5),
        Inches(0.38 + 0.36 * table_rows),
    )
    table = table_shape.table
    _fill_table_header(table, headers)
    if not rows:
        _set_cell(table.cell(1, 0), "Sin Technical Epics para este SWF", size=11, color=MUTED, align=PP_ALIGN.LEFT)
        for col in range(1, len(headers)):
            _set_cell(table.cell(1, col), "—", size=11, color=MUTED)
        return
    for row_index, program in enumerate(rows, start=1):
        values = [
            program.display_name,
            str(_sum_bucket(program.development)),
            str(_sum_bucket(program.testing)),
            str(program.closed_total),
            str(_sum_bucket(program.todo)),
            str(program.open),
            str(program.total),
        ]
        fill = OFF if row_index % 2 == 0 else WHITE
        for col, value in enumerate(values):
            _set_cell(
                table.cell(row_index, col),
                value,
                size=12,
                bold=col == 0,
                color=NAVY if col == 0 else BODY,
                fill=fill,
                align=PP_ALIGN.LEFT if col == 0 else PP_ALIGN.CENTER,
            )
    _add_text(
        slide,
        Inches(0.4),
        Inches(6.72),
        Inches(12.5),
        Inches(0.32),
        f"Filtro Jira {payload.sprint.filter_id}  ·  Cerrado = Done / Roll Out / Canceled / Data Validation y categoría Done.",
        size=10,
        color=MUTED,
    )


def _build_issues_slide(slide: Any, payload: SprintTestingRead) -> None:
    _slide_chrome(slide, payload, "Issues del Sprint en ejecución")
    execution = payload.execution
    issue_count = execution.issue_count if execution else 0
    blocker = sum(row.blocker for row in execution.programs) if execution else 0
    non_blocker = sum(row.non_blocker for row in execution.programs) if execution else 0
    cards = [
        (str(issue_count), "Issues", TEAL),
        (str(blocker), "Blocker", RED),
        (str(non_blocker), "No Blocker", NAVY),
    ]
    card_w = Inches(3.95)
    gap = Inches(0.22)
    start = Inches(0.4)
    for index, (value, label, accent) in enumerate(cards):
        _kpi_card(slide, start + index * (card_w + gap), Inches(1.12), card_w, value, label, accent)

    headers = ["Dispositivo", "Blocker", "No Blocker", "Total"]
    programs = execution.programs if execution else []
    table_rows = max(len(programs) + 1, 2)
    table_shape = slide.shapes.add_table(
        table_rows,
        len(headers),
        Inches(0.4),
        Inches(2.4),
        Inches(12.5),
        Inches(0.38 + 0.36 * table_rows),
    )
    table = table_shape.table
    _fill_table_header(table, headers)
    if execution is None:
        _set_cell(
            table.cell(1, 0),
            "Este Sprint aún no tiene un Saved Filter de issues en ejecución.",
            size=11,
            color=MUTED,
            align=PP_ALIGN.LEFT,
        )
        for col in range(1, len(headers)):
            _set_cell(table.cell(1, col), "—", size=11, color=MUTED)
        return
    if not programs:
        _set_cell(table.cell(1, 0), "No hay issues de ejecución para este SWF.", size=11, color=MUTED, align=PP_ALIGN.LEFT)
        for col in range(1, len(headers)):
            _set_cell(table.cell(1, col), "—", size=11, color=MUTED)
        return
    for row_index, program in enumerate(programs, start=1):
        values = [program.display_name, str(program.blocker), str(program.non_blocker), str(program.total)]
        fill = OFF if row_index % 2 == 0 else WHITE
        for col, value in enumerate(values):
            color = RED if col == 1 and program.blocker else (NAVY if col == 0 else BODY)
            _set_cell(
                table.cell(row_index, col),
                value,
                size=12,
                bold=col in {0, 1},
                color=color,
                fill=fill,
                align=PP_ALIGN.LEFT if col == 0 else PP_ALIGN.CENTER,
            )
    _add_text(
        slide,
        Inches(0.4),
        Inches(6.72),
        Inches(12.5),
        Inches(0.32),
        f"Filtro Jira {execution.filter_id}  ·  Blocker = Blocker / Impedimento / Bloqueador. El detalle fila a fila está en el Excel.",
        size=10,
        color=MUTED,
    )
