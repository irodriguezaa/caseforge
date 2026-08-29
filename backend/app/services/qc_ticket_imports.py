"""Parsing and validation for the QcTicket bulk-import pipeline.

All mapping tables below (QCO_MAP, PRE_POST_BASE, OPE_SWF_MAP, REL_OPERATIVO_FINAL,
REL_SWF_MAP2) were extracted VERBATIM from the QC team's reference dashboard_qco.html --
not re-derived or approximated. Column matching is by exact normalized header text (never
substring), specifically to avoid Jira's decoy fields ("Contador Programa Afectado" is numeric
and NOT the same as "Campo personalizado (Programa Afectado)"; same caution applies if a
"Nuevo Cluster" field is ever populated).
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date as date_cls

import openpyxl

from app.models.qc_ticket import QcTicketPriority, QcTicketSource, QcTicketView
from app.schemas.qc_tickets import QcTicketCreate, QcTicketImportRowError
from app.services.cluster_resolution import resolve_cluster

_REQUIRED_HEADERS = ["issue_key", "priority_raw", "status_raw", "created_date"]

_HEADER_ALIASES = {
    "clave de incidencia": "issue_key",
    "tipo de incidencia": "issue_type",
    "clave del proyecto": "project_key",
    "prioridad": "priority_raw",
    "estado": "status_raw",
    "creada": "created_date",
    "resuelta": "resolved_date",
    "resumen": "summary",
    "campo personalizado (cluster)": "cluster_raw",
    # Exact match only -- "Campo personalizado (Contador Programa Afectado)" is a DIFFERENT,
    # numeric field that must never be picked up here (see module docstring).
    "campo personalizado (programa afectado)": "affected_program",
}

# --- Operativas: Programa Afectado -> Program Base -> SWF ------------------------------------
# Extracted verbatim from QCO_MAP / PRE_POST_BASE / OPE_CUTOFF / OPE_SWF_MAP in the reference tool.
QCO_MAP = {
    "Gestion Cambios Operativos": "GCO", "Editorial": "GCO",
    "Buscadores y Recomendadores": "BE (HITSS)", "Usuarios y Sociabilizacion": "BE (HITSS)",
    "Akamai": "BE (HITSS)", "Player": "BE (HITSS)", "Pagos": "BE (HITSS)",
    "Tecnología": "BE (HITSS)", "Arquitectura": "BE (HITSS)", "Buscador": "BE (HITSS)",
    "Arquitectura BE": "BE (HITSS)", "CMS": "BE (HITSS)", "Gestores": "BE (HITSS)", "GPS": "BE (HITSS)",
    "Content Platform": "BE (HITSS)", "Business Support System": "BE (HITSS)",
    "Electronic Program Guide": "BE (HITSS)",
    "Claro Video Web": "WEBCL", "Claro Musica Web": "WEBCL",
    "Claro Video Windows": "WINCL", "XBox One": "WINCL",
    "Claro Video AndroidTV": "ADTCL",
    "AAF": "STVCL", "AAF IPTV": "STVCL", "STB AAF": "STVCL", "Kaon": "STVCL",
    "AAF Legacy": "STVCL", "MID": "STVCL",
    "Android TV STB": "ATSCL",
    "Claro Argentina": "LCDN", "LCDN Colombia": "LCDN",
}
PRE_POST_BASE = {
    "TVOS": "TVOS", "Claro Video Apple TV": "TVOS",
    "Claro Video iOS": "IOS",
    "Claro video Android": "ADR", "Claro Video Android": "ADR",
    "Coship": "C9085",
    "CVRKS": "ROKU",
}
OPE_CUTOFF = date_cls(2026, 4, 20)
OPE_SWF_MAP = {
    "BE (HITSS)": "HITSS", "GCO": "HITSS", "WEBCL": "HITSS", "WINCL": "HITSS", "ADTCL": "HITSS",
    "STVCL": "HITSS", "ATSCL": "TATA", "LCDN": "OPERACION",
    "TVOSCL": "HITSS", "TVOSPR": "NEORIS", "IOSCL": "HITSS", "IOSPR": "NEORIS",
    "ADRCL": "HITSS", "ADRPR": "NEORIS", "C9085CL": "HITSS", "C9085PR": "NEORIS",
    "ROKUCL": "HITSS", "ROKUPR": "NEORIS",
}

# --- Release: Clave del proyecto -> Operativo Final -> SWF ------------------------------------
REL_OPERATIVO_FINAL = {
    "CLAUP": "BE (HITSS)", "CLGLO": "BE (HITSS)", "CENAM": "BE (HITSS)", "CANRD": "BE (HITSS)",
    "CLBRA": "BE (HITSS)", "AKMCL": "BE (HITSS)", "ARQCL": "BE (HITSS)", "BSSCL": "BE (HITSS)",
    "CONCL": "BE (HITSS)", "PLYCL": "BE (HITSS)", "PRGCL": "BE (HITSS)",
    "IMDCL": "BE (Nubiral)", "RECCL": "BE (Nubiral)", "APIMCL": "BE (Nubiral)",
    "DPLCL": "BE (Nubiral)", "CLGES": "BE (Nubiral)", "DATCL": "BE (Nubiral)",
    "APISPR": "BE (NEORIS)", "DISPT": "EXCLUIR",
}
REL_SWF_MAP2 = {
    "BE (Nubiral)": "NUBIRAL", "ADRPR": "NEORIS", "WINCL": "HITSS", "AAFCL": "HITSS",
    "STVCL": "HITSS", "IOSPR": "NEORIS", "ROKUPR": "NEORIS", "IOSCL": "HITSS",
    "AOSPCL": "HITSS", "ADRCL": "HITSS", "KPLCL": "HITSS", "TVOSCL": "HITSS",
    "GCECL": "HITSS", "BE (HITSS)": "HITSS", "ATSCL": "TATA", "WEBCL": "HITSS",
    "SCTCL": "TATA", "TVOSPR": "NEORIS", "ADTCL": "HITSS", "C9085PR": "NEORIS",
    "C9085CL": "HITSS", "BE (NEORIS)": "NEORIS", "ROKUCL": "HITSS", "LCDN": "OPERACION",
    "CIACL": "OPERACION", "GCO": "HITSS",
}

_CLOSED_STATUSES_OPERATIVAS = {"FINALIZADA"}
_CLOSED_STATUSES_RELEASE = {"FINALIZADA", "ROLL OUT"}
_KNOWN_STATUSES = {
    "FINALIZADA", "ROLL OUT", "TO DEVELOP", "IN PROGRAM REVIEW", "PENDING EXTERNAL DATA",
    "PENDING BUSINESS OWNER", "ANALYSIS", "DEVELOPMENT", "INTEGRATION", "TAREAS POR HACER",
    "PENDING RESOLUTION", "PENDING BUSINESS ANALYST", "VALIDATE QC", "QA VALIDATION", "VALIDATION",
}

_MONTHS_ES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}
_DATE_RE = re.compile(r"(\d{2})/(\w{3})/(\d{2})\s+(\d{1,2}):(\d{2})\s*(AM|PM)", re.IGNORECASE)


class QcTicketImportStructureError(Exception):
    def __init__(self, messages: list[str]) -> None:
        super().__init__("; ".join(messages))
        self.messages = messages


@dataclass
class _RawRow:
    row_number: int
    values: dict[str, str] = field(default_factory=dict)
    linked_issue_keys: list[str] = field(default_factory=list)


def _clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def _normalize_header(raw: str) -> str | None:
    return _HEADER_ALIASES.get(raw.strip().lower())


def _is_link_header(raw: str) -> bool:
    """'Enlace a la incidencia (...)' columns: matched by PREFIX deliberately, unlike the exact
    matching used elsewhere -- Jira emits one such column per link type/slot, unpredictably."""
    return raw.strip().lower().startswith("enlace")


def _parse_jira_date(raw: str) -> date_cls | None:
    match = _DATE_RE.match(raw.strip())
    if not match:
        return None
    day, mon_es, yy, _hh, _mm, _ampm = match.groups()
    month = _MONTHS_ES.get(mon_es.lower())
    if month is None:
        return None
    try:
        return date_cls(2000 + int(yy), month, int(day))
    except ValueError:
        return None


def _read_grid(filename: str, content: bytes) -> list[list[object]]:
    lower = filename.lower()
    if lower.endswith(".csv"):
        text = content.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(text)))
    if lower.endswith((".xlsx", ".xlsm")):
        workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        sheet = workbook.worksheets[0]
        return [list(row) for row in sheet.iter_rows(values_only=True)]
    raise QcTicketImportStructureError(
        ["Formato de archivo no soportado. Solo se aceptan archivos .csv o .xlsx."]
    )


def parse_file(filename: str, content: bytes) -> list[_RawRow]:
    grid = _read_grid(filename, content)
    if not grid:
        raise QcTicketImportStructureError(["El archivo está vacío."])

    header_row = grid[0]
    canonical_by_index: dict[int, str] = {}
    link_indexes: list[int] = []
    for index, raw_header in enumerate(header_row):
        if raw_header is None:
            continue
        raw_header_str = str(raw_header)
        canonical = _normalize_header(raw_header_str)
        if canonical is not None:
            canonical_by_index[index] = canonical
        elif _is_link_header(raw_header_str):
            link_indexes.append(index)

    found = set(canonical_by_index.values())
    missing = [f for f in _REQUIRED_HEADERS if f not in found]
    if missing:
        raise QcTicketImportStructureError(
            [f"Faltan columnas obligatorias en el archivo: {', '.join(missing)}."]
        )

    rows: list[_RawRow] = []
    for offset, data_row in enumerate(grid[1:], start=2):
        if all(cell is None or _clean(cell) == "" for cell in data_row):
            continue
        values = {
            canonical: _clean(data_row[index] if index < len(data_row) else None)
            for index, canonical in canonical_by_index.items()
        }
        linked = [
            _clean(data_row[i]) for i in link_indexes if i < len(data_row) and _clean(data_row[i])
        ]
        rows.append(_RawRow(row_number=offset, values=values, linked_issue_keys=linked))

    if not rows:
        raise QcTicketImportStructureError(["El archivo no contiene filas de datos."])

    return rows


def _resolve_priority(raw: str) -> QcTicketPriority:
    lowered = raw.lower()
    if "impedimento" in lowered or "blocker" in lowered:
        return QcTicketPriority.BLOCKER
    if "crítica" in lowered or "critica" in lowered or "critical" in lowered:
        return QcTicketPriority.CRITICAL
    return QcTicketPriority.OTHER


def _resolve_operativas_device_swf(affected_program: str | None, created: date_cls) -> tuple[str | None, str | None]:
    if not affected_program:
        return None, None
    if affected_program in PRE_POST_BASE:
        base = PRE_POST_BASE[affected_program]
        suffix = "CL" if created < OPE_CUTOFF else "PR"
        device = base + suffix
    elif affected_program in QCO_MAP:
        device = QCO_MAP[affected_program]
    else:
        return None, None
    swf = OPE_SWF_MAP.get(device, "OTROS")
    return device, swf


def _resolve_release_swf(project_key: str | None) -> tuple[str | None, str | None]:
    """Returns (operativo_final_or_None_if_excluded, swf). A return of (None, "EXCLUIR") signals
    the ticket should be dropped entirely (matches REL_OPERATIVO_FINAL['DISPT'] = 'EXCLUIR')."""
    if not project_key:
        return None, None
    operativo_final = REL_OPERATIVO_FINAL.get(project_key, project_key)
    if operativo_final == "EXCLUIR":
        return None, "EXCLUIR"
    swf = REL_SWF_MAP2.get(operativo_final, "OTROS")
    return operativo_final, swf


def validate_rows(
    rows: list[_RawRow], view: QcTicketView, source: QcTicketSource
) -> tuple[list[QcTicketCreate], list[QcTicketImportRowError], list[QcTicketImportRowError], int, dict[str, list[str]]]:
    """Returns (valid, errors, warnings, excluded_cancelled_count, linked_keys_by_issue).

    linked_keys_by_issue is only populated for view=RELEASE, source=LEAKED -- the router uses it
    to compute is_attributed (genuine-leak cross-reference) against already-imported QC/QA Bugs.
    """
    valid: list[QcTicketCreate] = []
    errors: list[QcTicketImportRowError] = []
    warnings: list[QcTicketImportRowError] = []
    linked_keys_by_issue: dict[str, list[str]] = {}
    seen_keys: dict[str, int] = {}
    excluded_cancelled = 0

    for row in rows:
        issue_key = row.values.get("issue_key", "")
        if not issue_key:
            errors.append(
                QcTicketImportRowError(row_number=row.row_number, message="Falta Clave de incidencia.")
            )
            continue

        status_raw = row.values.get("status_raw", "")
        if "cancel" in status_raw.strip().lower():
            excluded_cancelled += 1
            continue  # Cancelled tickets are excluded from ALL counts, no exception -- not imported.

        if issue_key in seen_keys:
            errors.append(
                QcTicketImportRowError(
                    issue_key=issue_key,
                    row_number=row.row_number,
                    message=f"'{issue_key}' está duplicado dentro del archivo (fila {seen_keys[issue_key]}).",
                )
            )
            continue
        seen_keys[issue_key] = row.row_number

        created_raw = row.values.get("created_date", "")
        created = _parse_jira_date(created_raw) if created_raw else None
        if created is None:
            errors.append(
                QcTicketImportRowError(
                    issue_key=issue_key,
                    row_number=row.row_number,
                    message=f"'{issue_key}': fecha 'Creada' inválida o vacía ('{created_raw}').",
                )
            )
            continue

        resolved_raw = row.values.get("resolved_date", "")
        resolved = _parse_jira_date(resolved_raw) if resolved_raw else None

        status_upper = status_raw.strip().upper()
        closed_set = _CLOSED_STATUSES_OPERATIVAS if view == QcTicketView.OPERATIVAS else _CLOSED_STATUSES_RELEASE
        is_open = status_upper not in closed_set
        if status_upper not in _KNOWN_STATUSES:
            warnings.append(
                QcTicketImportRowError(
                    issue_key=issue_key,
                    row_number=row.row_number,
                    message=(
                        f"'{issue_key}': estado '{status_raw}' no reconocido, se asumió "
                        f"{'ABIERTO' if is_open else 'CERRADO'} por comparación de texto -- revisar."
                    ),
                )
            )

        cluster = None
        if view == QcTicketView.OPERATIVAS:
            cluster_raw = row.values.get("cluster_raw", "")
            cluster, cluster_warning = resolve_cluster(cluster_raw, row.values.get("summary", ""))
            if cluster_warning:
                warnings.append(
                    QcTicketImportRowError(
                        issue_key=issue_key, row_number=row.row_number, message=f"'{issue_key}': {cluster_warning}"
                    )
                )

        device = swf = None
        if view == QcTicketView.OPERATIVAS:
            device, swf = _resolve_operativas_device_swf(row.values.get("affected_program") or None, created)
            if row.values.get("affected_program") and device is None:
                warnings.append(
                    QcTicketImportRowError(
                        issue_key=issue_key,
                        row_number=row.row_number,
                        message=f"'{issue_key}': Programa Afectado '{row.values['affected_program']}' no reconocido, sin SWF.",
                    )
                )
        else:
            device, swf = _resolve_release_swf(row.values.get("project_key") or None)
            if swf == "EXCLUIR":
                continue  # DISPT-mapped projects are excluded from Release SWF entirely.
            if row.values.get("project_key") and swf is None:
                swf = "OTROS"

        ticket = QcTicketCreate(
            issue_key=issue_key,
            issue_type=row.values.get("issue_type") or None,
            project_key=row.values.get("project_key") or None,
            priority_bucket=_resolve_priority(row.values.get("priority_raw", "")),
            status_raw=status_raw,
            is_open=is_open,
            view=view,
            source=source,
            cluster=cluster,
            affected_program=row.values.get("affected_program") or None,
            device=device,
            swf=swf,
            created_date=created,
            resolved_date=resolved,
            summary=row.values.get("summary") or None,
        )
        valid.append(ticket)

        if view == QcTicketView.RELEASE and source == QcTicketSource.LEAKED and row.linked_issue_keys:
            linked_keys_by_issue[issue_key] = row.linked_issue_keys

    return valid, errors, warnings, excluded_cancelled, linked_keys_by_issue
