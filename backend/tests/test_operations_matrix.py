from io import BytesIO

from openpyxl import load_workbook
from openpyxl.cell.rich_text import CellRichText

from app.services.operations_matrix import (
    LLAVES_NOTE,
    build_operations_matrix_workbook,
    is_llaves_ticket,
)


def _text(value: object) -> str:
    if isinstance(value, CellRichText):
        return "".join(getattr(block, "text", str(block)) for block in value)
    return "" if value is None else str(value)


def _mvp() -> dict:
    return {
        "type": "doc",
        "content": [
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "1. Objetivo técnico"}]},
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Implementar el botón de Telcel en la Landing."}],
            },
            {
                "type": "orderedList",
                "attrs": {"order": 1},
                "content": [
                    {
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Consulta la llave."}]}],
                    },
                    {
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Carga el logo."}]}],
                    },
                ],
            },
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "2. Alcance"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "Esto no entra en el MVP."}]},
        ],
    }


def _criteria() -> dict:
    return {
        "type": "doc",
        "content": [
            {"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Criterios de Aceptación"}]},
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "El botón se muestra."}]}],
                    },
                    {
                        "type": "listItem",
                        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "El logo se carga."}]}],
                    },
                ],
            },
        ],
    }


def _analysis() -> dict:
    return {
        "normalized": {
            "technical_epics": [
                {"id": "WEBCL-10", "title": "Landing Telcel"},
                {"id": "SIC-77844", "title": "ventana UAT"},
                {"id": "WEBCL-20", "title": "Alta de llaves de configuración en el dispositivo"},
            ],
            "nco": [{"id": "WEBCL-99", "title": "un NCO"}],
            "tri": [{"id": "TRI-15", "title": "Falla en reproducción"}],
            "qa_qc": [{"id": "WEBCL-30", "title": "un bug"}],
        }
    }


def test_llaves_phrase_matches_alta_and_registro() -> None:
    assert is_llaves_ticket("Alta de llaves de configuración")
    assert is_llaves_ticket("Registro de llaves en appKeys")
    assert not is_llaves_ticket("Landing Page Telcel")


def test_workbook_keeps_epc_and_tri_and_formats_mvp() -> None:
    payload = build_operations_matrix_workbook(
        platform="WEB",
        version="vWEBCL-18.1.0",
        name="Sprint 45-46",
        raw_analysis=_analysis(),
        issues={
            "WEBCL-10": {"summary": "Landing Telcel", "mvp": _mvp(), "criterios": _criteria()},
            "WEBCL-20": {"summary": "Alta de llaves de configuración en el dispositivo", "mvp": "", "criterios": ""},
        },
        fetch_jira=False,
    )
    book = load_workbook(BytesIO(payload))
    assert book.sheetnames == ["No Afectación", "RN", "EPCs"]

    regression = book["No Afectación"]
    assert regression["C3"].value == "Comentarios operación"
    assert regression["B4"].value == "Acceso"
    assert regression["B5"].value == "Registro"
    assert regression["C5"].value in (None, "")

    index = book["RN"]
    assert [index.cell(2, column).value for column in range(1, 5)] == [
        "ID",
        "TAREA",
        "TIPO",
        "Comentarios / Observaciones",
    ]
    rows = {
        index.cell(row, 1).value: (
            index.cell(row, 3).value,
            index.cell(row, 4).value or "",
        )
        for row in range(3, 6)
    }
    assert rows["WEBCL-10"] == ("Funcionalidad", "")
    assert rows["WEBCL-20"][0] == "Funcionalidad"
    assert LLAVES_NOTE in rows["WEBCL-20"][1]
    assert rows["TRI-15"] == ("Issue Productivo", "")
    assert "WEBCL-99" not in rows
    assert "WEBCL-30" not in rows
    assert "SIC-77844" not in rows

    detail = book["EPCs"]
    assert "WEBCL-10" in _text(detail["A3"].value)
    assert detail["A4"].value == "MVP técnico"
    mvp = _text(detail["B4"].value)
    assert "Implementar el botón de Telcel" in mvp
    assert "1. Consulta la llave." in mvp
    assert "2. Carga el logo." in mvp
    assert "Esto no entra en el MVP." not in mvp
    criteria = _text(detail["B5"].value)
    assert "El botón se muestra." in criteria
    assert "El logo se carga." in criteria
    assert "\n\n" in criteria
    assert detail["C4"].value in (None, "")
