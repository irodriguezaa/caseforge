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

ISSUE_HEADERS = ["Key", "Summary", "Issue Type", "Estado", "Prioridad"]

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
    widths = [16, 64, 16, 18, 16]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    sheet.row_dimensions[1].height = 28
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(ISSUE_HEADERS))}1"

    for row_index, row in enumerate(rows, start=2):
        values = [row.key, row.summary, row.issue_type, row.status, row.priority]
        for col, value in enumerate(values, start=1):
            cell = sheet.cell(row_index, col, _excel_value(value))
            cell.font = _CELL_FONT
            cell.border = _THIN
            cell.alignment = Alignment(wrap_text=col == 2, vertical="top")
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


def _fill_table_body(table: Any, rows: list[list[str]], *, blocker_col: int | None = None) -> None:
    if not rows:
        _set_cell(table.cell(1, 0), "Sin datos para este SWF.", size=11, color=MUTED, align=PP_ALIGN.LEFT)
        for col in range(1, len(table.columns)):
            _set_cell(table.cell(1, col), "—", size=11, color=MUTED)
        return
    for row_index, values in enumerate(rows, start=1):
        fill = OFF if row_index % 2 == 0 else WHITE
        for col, value in enumerate(values):
            highlight = blocker_col is not None and col == blocker_col and value not in {"0", "—"}
            _set_cell(
                table.cell(row_index, col),
                value,
                size=11,
                bold=col == 0 or highlight,
                color=RED if highlight else (NAVY if col == 0 else BODY),
                fill=fill,
                align=PP_ALIGN.LEFT if col == 0 else PP_ALIGN.CENTER,
            )


def build_executive_pptx(payload: SprintTestingRead) -> bytes:
    presentation = Presentation()
    presentation.slide_width = SLIDE_W
    presentation.slide_height = SLIDE_H
    _build_executive_slide(presentation.slides.add_slide(presentation.slide_layouts[6]), payload)
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def _build_executive_slide(slide: Any, payload: SprintTestingRead) -> None:
    _add_rect(slide, Inches(0), Inches(0), SLIDE_W, Inches(0.88), NAVY)
    _add_text(slide, Inches(0.4), Inches(0.1), Inches(8.5), Inches(0.28), "Reporte ejecutivo", size=12, color=TEAL)
    _add_text(
        slide,
        Inches(0.4),
        Inches(0.36),
        Inches(12.5),
        Inches(0.42),
        f"{payload.sprint.label}  ·  {payload.swf}",
        size=22,
        bold=True,
    )

    closed_count = sum(row.closed_total for row in payload.programs)
    execution = payload.execution
    issue_count = execution.issue_count if execution else 0
    blocker = sum(row.blocker for row in execution.programs) if execution else 0
    non_blocker = sum(row.non_blocker for row in execution.programs) if execution else 0
    cards = [
        (str(payload.technical_epic_count), "Technical Epics", TEAL),
        (str(closed_count), "Cerrados", TEAL),
        (_closed_pct(payload.technical_epic_count - closed_count, closed_count), "% cerrado", NAVY),
        (str(issue_count), "Issues", GOLD),
        (str(blocker), "Blocker", RED),
        (str(non_blocker), "No Blocker", NAVY),
    ]
    card_w = Inches(2.0)
    gap = Inches(0.12)
    start = Inches(0.4)
    for index, (value, label, accent) in enumerate(cards):
        _kpi_card(slide, start + index * (card_w + gap), Inches(1.04), card_w, value, label, accent)

    _add_text(slide, Inches(0.4), Inches(2.22), Inches(6.1), Inches(0.28), "Technical Epics", size=13, bold=True, color=NAVY)
    _add_text(
        slide,
        Inches(7.2),
        Inches(2.22),
        Inches(5.7),
        Inches(0.28),
        "Issues en ejecución",
        size=13,
        bold=True,
        color=NAVY,
    )
    _add_rect(slide, Inches(6.78), Inches(2.18), Inches(0.018), Inches(4.7), GOLD)

    epic_headers = ["Dispositivo", "Desarrollo", "Testing", "Cerrado", "Total"]
    epic_rows = [
        [
            program.display_name,
            str(_sum_bucket(program.development)),
            str(_sum_bucket(program.testing)),
            str(program.closed_total),
            str(program.total),
        ]
        for program in payload.programs
    ]
    epic_table_rows = max(len(epic_rows) + 1, 2)
    epic_shape = slide.shapes.add_table(
        epic_table_rows,
        len(epic_headers),
        Inches(0.4),
        Inches(2.54),
        Inches(6.15),
        Inches(0.32 + 0.36 * epic_table_rows),
    )
    _fill_table_header(epic_shape.table, epic_headers)
    _fill_table_body(epic_shape.table, epic_rows)

    issue_headers = ["Dispositivo", "Blocker", "No Blocker", "Total"]
    if execution is None:
        issue_rows: list[list[str]] = []
    else:
        issue_rows = [
            [program.display_name, str(program.blocker), str(program.non_blocker), str(program.total)]
            for program in execution.programs
        ]
    issue_table_rows = max(len(issue_rows) + 1, 2)
    issue_shape = slide.shapes.add_table(
        issue_table_rows,
        len(issue_headers),
        Inches(7.2),
        Inches(2.54),
        Inches(5.7),
        Inches(0.32 + 0.36 * issue_table_rows),
    )
    _fill_table_header(issue_shape.table, issue_headers)
    if execution is None:
        _set_cell(
            issue_shape.table.cell(1, 0),
            "Sin filtro de issues en ejecución.",
            size=11,
            color=MUTED,
            align=PP_ALIGN.LEFT,
        )
        for col in range(1, len(issue_headers)):
            _set_cell(issue_shape.table.cell(1, col), "—", size=11, color=MUTED)
    else:
        _fill_table_body(issue_shape.table, issue_rows, blocker_col=1)

    execution_filter = execution.filter_id if execution else "—"
    _add_text(
        slide,
        Inches(0.4),
        Inches(7.12),
        Inches(12.5),
        Inches(0.28),
        f"Filtros Jira {payload.sprint.filter_id} / {execution_filter}",
        size=10,
        color=MUTED,
    )
