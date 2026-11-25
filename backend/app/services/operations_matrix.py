"""Excel de Matriz Operaciones: regresión macro, índice del RN y detalle por EPC.

EPCs y TRIs salen del alcance normalizado. El MVP técnico y los criterios se leen
de Jira (customfield_19113 y customfield_19114) y se escriben con los párrafos y
las listas del ticket. La evidencia queda vacía.
"""

from __future__ import annotations

import io
import logging
import re
import unicodedata
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from app.services.jira_client import JiraApiError, JiraNotConfiguredError, _client
from app.services.rn_normalized import is_sic_key

logger = logging.getLogger(__name__)

MVP_FIELD = "customfield_19113"
CRITERIA_FIELD = "customfield_19114"
LLAVES_NOTE = (
    "Son alta/modificación de llaves. La participación de QC se realiza durante "
    "la validación de las aplicaciones de FE que consumen dichas llaves. Parte de la No Afectación"
)
_LLAVES_PHRASES = ("registro de llaves", "alta de llaves")
_KEEP = {"paragraph", "orderedList", "bulletList", "blockquote"}

_NAVY = PatternFill("solid", fgColor="002060")
_TITLE = PatternFill("solid", fgColor="1F4E78")
_LABEL_MVP = PatternFill("solid", fgColor="E7F0FA")
_LABEL_CA = PatternFill("solid", fgColor="EAF6EA")
_GREEN = PatternFill("solid", fgColor="34A853")
_EVIDENCE = PatternFill("solid", fgColor="FFF8E7")
_WHITE = PatternFill("solid", fgColor="FFFFFF")
_ZEBRA = PatternFill("solid", fgColor="F7F9FC")
_THIN = Border(
    left=Side(style="thin", color="D0D7E2"),
    right=Side(style="thin", color="D0D7E2"),
    top=Side(style="thin", color="D0D7E2"),
    bottom=Side(style="thin", color="D0D7E2"),
)
_FONT = Font(name="Calibri", size=11)
_HEADER = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
_LINK = Font(name="Calibri", size=11, color="0563C1", underline="single")
_MID = Alignment(wrap_text=True, vertical="center")

REGRESSION_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Acceso", ("Registro", "Inicio de sesión", "Cierre de sesión", "Recuperación de contraseña")),
    ("Perfiles", ("Selección de perfil", "Alta y edición de perfil", "Perfil infantil", "Cambio de perfil")),
    ("PIN parental", ("Configuración del PIN", "Bloqueo por clasificación", "Desbloqueo de contenido con PIN")),
    ("Inicio y navegación", ("Home y carruseles", "Menú de navegación", "Buscador", "Ficha del contenido")),
    ("VOD", ("Reproducción de película", "Reproducción de serie", "Continuar viendo", "Pausa, avance, audio y subtítulos")),
    ("TV en vivo", ("Reproducción de canal", "Cambio de canal", "Guía de programación", "Bloqueo y desbloqueo de canales")),
    ("Renta y suscripción", ("Alquiler", "Suscripción", "Medio de pago")),
    ("Mi contenido", ("Mi lista", "Descargas (si aplica)")),
    ("Otros", ("Centro de notificaciones", "Claro Música (si aplica)")),
)


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.casefold()


def _clean(value: str) -> str:
    return ILLEGAL_CHARACTERS_RE.sub("", value or "")


def _item_key_title(item: object) -> tuple[str, str]:
    if isinstance(item, dict):
        key = str(item.get("id") or item.get("key") or "").strip().upper()
        title = str(item.get("title") or item.get("summary") or "").strip()
    else:
        key = str(getattr(item, "id", "") or "").strip().upper()
        title = str(getattr(item, "title", "") or "").strip()
    return key, title


def scope_from_analysis(raw_analysis: object) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """EPCs de funcionalidad y TRIs, en el orden del RN. Sin NCO ni bugs."""
    if not isinstance(raw_analysis, dict):
        return [], []
    normalized = raw_analysis.get("normalized")
    if not isinstance(normalized, dict):
        return [], []
    epcs: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in normalized.get("technical_epics") or []:
        key, title = _item_key_title(item)
        if not key or is_sic_key(key) or key in seen:
            continue
        seen.add(key)
        epcs.append({"key": key, "title": title or key, "tipo": "Funcionalidad"})
    tris: list[dict[str, str]] = []
    seen_tri: set[str] = set()
    for item in normalized.get("tri") or []:
        key, title = _item_key_title(item)
        if not key or key in seen_tri:
            continue
        seen_tri.add(key)
        tris.append({"key": key, "title": title or key, "tipo": "Issue Productivo"})
    return epcs, tris


def is_llaves_ticket(*parts: str) -> bool:
    blob = _fold(" ".join(parts))
    return any(phrase in blob for phrase in _LLAVES_PHRASES)


def _plain(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    if node.get("type") == "text":
        return str(node.get("text") or "")
    if node.get("type") == "hardBreak":
        return "\n"
    return "".join(_plain(child) for child in node.get("content") or [])


def _runs(node: Any) -> list[str]:
    parts: list[str] = []
    for child in node.get("content") or []:
        kind = child.get("type")
        if kind == "text":
            parts.append(_clean(str(child.get("text") or "")))
        elif kind == "hardBreak":
            parts.append("\n")
        elif kind == "inlineCard":
            url = str((child.get("attrs") or {}).get("url") or "")
            if url:
                parts.append(url)
        elif isinstance(child, dict):
            parts.extend(_runs(child))
    return parts


def _content(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        return [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]
    if isinstance(value, dict):
        content = value.get("content")
        if isinstance(content, list):
            return [node for node in content if isinstance(node, dict)]
    return []


def mvp_nodes(value: Any) -> list[dict[str, Any]]:
    """Primer bloque del campo MVP: objetivo o la sección MVP, sin el resto del brief."""
    content = _content(value)
    headings = [
        (index, node)
        for index, node in enumerate(content)
        if node.get("type") == "heading" and int((node.get("attrs") or {}).get("level") or 2) <= 2
    ]
    if not headings:
        return [node for node in content if node.get("type") in _KEEP]
    start, first = headings[0]
    title = _plain(first).lower()
    end = headings[1][0] if len(headings) > 1 else len(content)
    body = content[start + 1 : end] if ("objetivo" in title or re.search(r"\bmvp\b", title)) else content[:end]
    return [node for node in body if node.get("type") in _KEEP]


def criteria_nodes(value: Any) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for node in _content(value):
        if node.get("type") == "heading" and "criterio" in _plain(node).lower():
            continue
        if node.get("type") in _KEEP:
            kept.append(node)
    return kept


def _blocks(nodes: list[dict[str, Any]], *, loose_bullets: bool) -> list[str]:
    """Plain paragraphs. Excel repairs rich text with line breaks on this sheet."""
    blocks: list[str] = []
    for node in nodes:
        kind = node.get("type")
        if kind in {"paragraph", "blockquote"}:
            text = _clean("".join(_runs(node))).strip()
            if text:
                blocks.append(text)
        elif kind == "orderedList":
            number = int((node.get("attrs") or {}).get("order") or 1)
            lines: list[str] = []
            for item in node.get("content") or []:
                if item.get("type") != "listItem":
                    continue
                text = _clean("".join(_runs(item))).strip()
                if not text:
                    continue
                lines.append(f"{number}. {text}")
                number += 1
            if lines:
                blocks.append("\n".join(lines))
        elif kind == "bulletList":
            lines = []
            for item in node.get("content") or []:
                if item.get("type") != "listItem":
                    continue
                text = _clean("".join(_runs(item))).strip()
                if text:
                    lines.append(f"• {text}")
            if not lines:
                continue
            if loose_bullets:
                blocks.extend(lines)
            else:
                blocks.append("\n".join(lines))
    return blocks


def _plain_blocks(blocks: list[str]) -> str:
    return "\n\n".join(block for block in blocks if block).strip()


def _line_count(text: str) -> int:
    if not text:
        return 1
    total = max(1, text.count("\n") + 1)
    total += sum(max(0, len(line) // 100) for line in text.split("\n"))
    return total


def fetch_epic_documents(keys: list[str]) -> dict[str, dict[str, Any]]:
    """Summary, MVP técnico y criterios. Vacío si Jira no está configurado."""
    unique: list[str] = []
    seen: set[str] = set()
    for key in keys:
        token = (key or "").strip().upper()
        if token and token not in seen:
            seen.add(token)
            unique.append(token)
    if not unique:
        return {}
    try:
        client_cm = _client(timeout=60)
    except JiraNotConfiguredError:
        return {}
    found: dict[str, dict[str, Any]] = {}
    try:
        with client_cm as client:
            for start in range(0, len(unique), 40):
                chunk = unique[start : start + 40]
                token: str | None = None
                while True:
                    body: dict[str, Any] = {
                        "jql": "key in (" + ", ".join(chunk) + ")",
                        "maxResults": 50,
                        "fields": ["summary", MVP_FIELD, CRITERIA_FIELD],
                    }
                    if token:
                        body["nextPageToken"] = token
                    response = client.post("/rest/api/3/search/jql", json=body)
                    if response.status_code != 200:
                        logger.warning("Jira no devolvió el detalle de las EPC (%s)", response.status_code)
                        return found
                    payload = response.json()
                    for issue in payload.get("issues") or []:
                        key = str(issue.get("key") or "").strip().upper()
                        fields = issue.get("fields") or {}
                        if key:
                            found[key] = {
                                "summary": str(fields.get("summary") or "").strip(),
                                "mvp": fields.get(MVP_FIELD),
                                "criterios": fields.get(CRITERIA_FIELD),
                            }
                    token = payload.get("nextPageToken") or None
                    if not token:
                        break
    except (JiraApiError, httpx.TimeoutException, httpx.RequestError) as exc:
        logger.warning("No se pudo leer MVP y criterios en Jira: %s", exc)
    return found


def _cell_text(value: str) -> str | None:
    """None keeps a styled blank cell. An empty string becomes an invalid inline string."""
    text = (value or "").strip()
    return text or None


_EMPTY_TYPED_CELL = re.compile(r'<c\b[^>]*\st="(?:n|inlineStr)"[^>]*(?:/>|></c>)')


def _drop_empty_typed_cells(payload: bytes) -> bytes:
    """Excel repairs empty cells marked as text or numbers and reports string properties."""
    source = ZipFile(io.BytesIO(payload))
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as target:
        for item in source.infolist():
            data = source.read(item.filename)
            if item.filename.startswith("xl/worksheets/sheet") and item.filename.endswith(".xml"):
                text = data.decode("utf-8")
                text = _EMPTY_TYPED_CELL.sub(lambda match: re.sub(r'\s+t="(?:n|inlineStr)"', "", match.group(0), count=1), text)
                data = text.encode("utf-8")
            target.writestr(item, data)
    return output.getvalue()


def _banner(platform: str, version: str, name: str) -> str:
    parts = [part.strip() for part in (platform, version, name) if part and part.strip()]
    return "  ·  ".join(parts)


def _apply_page(sheet, area: str, *, fit_height: int) -> None:
    sheet.print_area = area
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_TABLOID
    sheet.page_setup.fitToPage = True
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = fit_height
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.horizontalCentered = True
    sheet.page_margins.left = 0.4
    sheet.page_margins.right = 0.4
    sheet.page_margins.top = 0.55
    sheet.page_margins.bottom = 0.45
    sheet.page_margins.header = 0.22
    sheet.page_margins.footer = 0.22
    sheet.oddFooter.right.text = "Página &P"
    sheet.sheet_view.showGridLines = False


def build_operations_matrix_workbook(
    *,
    platform: str,
    version: str,
    name: str,
    raw_analysis: object,
    issues: dict[str, dict[str, Any]] | None = None,
    fetch_jira: bool = True,
) -> bytes:
    epcs, tris = scope_from_analysis(raw_analysis)
    documents = dict(issues or {})
    if fetch_jira and issues is None:
        documents = fetch_epic_documents([row["key"] for row in (*epcs, *tris)])
    banner = _banner(platform, version, name) or "Release"

    workbook = Workbook()
    regression = workbook.active
    regression.title = "No Afectación"
    regression.merge_cells("B2:D2")
    regression["B2"] = f"TABLA DE VALIDACIONES    {banner}"
    regression["B2"].font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    regression["B2"].fill = _TITLE
    regression["B2"].alignment = _MID
    for column, (header, fill) in enumerate(
        (("Validaciones", _NAVY), ("Comentarios operación", _NAVY), ("Comentarios AMCO", _GREEN)),
        start=2,
    ):
        cell = regression.cell(3, column, header)
        cell.fill = fill
        cell.font = _HEADER
        cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        cell.border = _THIN
    regression.row_dimensions[2].height = 28
    regression.row_dimensions[3].height = 22
    row = 4
    scenario_index = 0
    for group, items in REGRESSION_GROUPS:
        for column in range(2, 5):
            cell = regression.cell(row, column, group if column == 2 else None)
            cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
            cell.fill = _TITLE
            cell.alignment = Alignment(vertical="center", indent=1)
            cell.border = _THIN
        regression.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
        regression.row_dimensions[row].height = 20
        row += 1
        for item in items:
            fill = _WHITE if scenario_index % 2 == 0 else _ZEBRA
            for column, value in enumerate((item, None, None), start=2):
                body = regression.cell(row, column, value)
                body.font = _FONT
                body.fill = fill
                body.border = _THIN
                body.alignment = Alignment(vertical="center", indent=1 if column == 2 else 0)
            regression.row_dimensions[row].height = 20
            scenario_index += 1
            row += 1
    last_regression = row - 1
    regression.column_dimensions["A"].width = 3
    regression.column_dimensions["B"].width = 52
    regression.column_dimensions["C"].width = 38
    regression.column_dimensions["D"].width = 32
    regression.freeze_panes = "B4"
    regression.print_title_rows = "2:3"
    regression.sheet_view.zoomScale = 120
    _apply_page(regression, f"B2:D{last_regression}", fit_height=1)
    regression.oddHeader.left.text = banner

    detail = workbook.create_sheet("EPCs")
    detail.column_dimensions["A"].width = 28
    detail.column_dimensions["B"].width = 118
    detail.column_dimensions["C"].width = 32
    detail.merge_cells("A1:C1")
    detail["A1"] = f"EPCs    {banner}"
    detail["A1"].font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    detail["A1"].fill = _TITLE
    detail["A1"].alignment = _MID
    detail.row_dimensions[1].height = 28
    detail.freeze_panes = "A3"
    detail.print_title_rows = "1:1"
    detail.sheet_view.zoomScale = 110

    anchors: dict[str, int] = {}
    cursor = 3
    prepared: list[dict[str, Any]] = []
    for epic in epcs:
        document = documents.get(epic["key"]) or {}
        summary = str(document.get("summary") or "").strip() or epic["title"]
        mvp_blocks = _blocks(mvp_nodes(document.get("mvp")), loose_bullets=False)
        criteria_blocks = _blocks(criteria_nodes(document.get("criterios")), loose_bullets=True)
        note = ""
        if is_llaves_ticket(epic["title"], summary, _plain_blocks(mvp_blocks), _plain_blocks(criteria_blocks)):
            note = LLAVES_NOTE
        prepared.append({"key": epic["key"], "summary": summary, "tipo": epic["tipo"], "note": note})
        anchors[epic["key"]] = cursor
        detail.merge_cells(start_row=cursor, start_column=1, end_row=cursor, end_column=2)
        title = detail.cell(cursor, 1, _clean(f"{epic['key']}    {summary}"))
        title.font = Font(name="Calibri", size=12, bold=True, color="FFFFFF")
        title.fill = _TITLE
        title.alignment = Alignment(vertical="center", indent=1)
        evidence = detail.cell(cursor, 3, "Evidencia")
        evidence.font = _HEADER
        evidence.fill = _TITLE
        evidence.alignment = Alignment(vertical="center", horizontal="center")
        detail.row_dimensions[cursor].height = 26
        for offset, (label, blocks, fill) in enumerate(
            (
                ("MVP técnico", mvp_blocks, _LABEL_MVP),
                ("Criterios de aceptación", criteria_blocks, _LABEL_CA),
            )
        ):
            line = cursor + 1 + offset
            lab = detail.cell(line, 1, label)
            lab.font = Font(name="Calibri", size=11, bold=True, color="1F4E78")
            lab.fill = fill
            lab.alignment = Alignment(wrap_text=True, vertical="top", indent=1)
            lab.border = _THIN
            text = _plain_blocks(blocks)
            body = detail.cell(line, 2, _cell_text(text))
            body.alignment = Alignment(wrap_text=True, vertical="top")
            body.border = _THIN
            side = detail.cell(line, 3, None)
            side.fill = _EVIDENCE
            side.border = _THIN
            detail.row_dimensions[line].height = min(400, max(56, 15 * _line_count(text) + 18))
        detail.merge_cells(start_row=cursor + 1, start_column=3, end_row=cursor + 2, end_column=3)
        cursor += 4
    _apply_page(detail, f"A1:C{max(cursor - 1, 1)}", fit_height=0)
    detail.page_setup.fitToHeight = 0
    detail.oddHeader.left.text = banner

    index = workbook.create_sheet("RN", 1)
    index.merge_cells("A1:D1")
    index["A1"] = f"RN    {banner}"
    index["A1"].font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    index["A1"].fill = _TITLE
    index["A1"].alignment = _MID
    for column, header in enumerate(("ID", "TAREA", "TIPO", "Comentarios / Observaciones"), start=1):
        cell = index.cell(2, column, header)
        cell.fill = _NAVY
        cell.font = _HEADER
        cell.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
        cell.border = _THIN
    index.row_dimensions[1].height = 28
    index.row_dimensions[2].height = 24
    catalog = [*prepared, *[{"key": row["key"], "summary": row["title"], "tipo": row["tipo"], "note": ""} for row in tris]]
    for position, row in enumerate(catalog):
        line = 3 + position
        fill = _WHITE if position % 2 == 0 else _ZEBRA
        identifier = index.cell(line, 1, row["key"])
        identifier.font = _LINK if row["key"] in anchors else _FONT
        if row["key"] in anchors:
            identifier.hyperlink = f"#EPCs!A{anchors[row['key']]}"
        identifier.alignment = _MID
        identifier.border = _THIN
        identifier.fill = fill
        task = index.cell(line, 2, _clean(row["summary"]))
        task.font = _FONT
        task.alignment = Alignment(wrap_text=True, vertical="center")
        task.border = _THIN
        task.fill = fill
        kind = index.cell(line, 3, row["tipo"])
        kind.font = _FONT
        kind.alignment = _MID
        kind.border = _THIN
        kind.fill = fill
        comment = index.cell(line, 4, _cell_text(row["note"]))
        comment.font = _FONT
        comment.alignment = Alignment(wrap_text=True, vertical="center")
        comment.border = _THIN
        comment.fill = fill
        index.row_dimensions[line].height = 48 if row["note"] else 28
    last_index = 2 + len(catalog)
    index.column_dimensions["A"].width = 16
    index.column_dimensions["B"].width = 88
    index.column_dimensions["C"].width = 22
    index.column_dimensions["D"].width = 46
    index.freeze_panes = "A3"
    if catalog:
        index.auto_filter.ref = f"A2:D{last_index}"
    index.print_title_rows = "1:2"
    index.sheet_view.zoomScale = 120
    _apply_page(index, f"A1:D{last_index}", fit_height=1)
    index.oddHeader.left.text = banner

    buffer = io.BytesIO()
    workbook.save(buffer)
    return _drop_empty_typed_cells(buffer.getvalue())
