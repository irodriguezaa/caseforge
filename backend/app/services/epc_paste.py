"""Parse a pasted Technical Epic list into the same normalized.technical_epics spine as an RN.

Does not generate Test Cases. Does not use the Operativa Epc model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.schemas.release import ReleaseAnalysisBase
from app.services.jira_client import JiraNotConfiguredError, _require_config
from app.services.jira_generation import fetch_artifacts_for_keys
from app.services.rn_epc_scope import rn_keys_from_normalized

PASTED_SOURCE = "pasted_epcs"
PASTED_FILENAME = "pasted-epcs.txt"

_JIRA_KEY = re.compile(r"\b([A-Z][A-Z0-9_]+-\d+)\b", re.IGNORECASE)
_DEVICE_HEADING = re.compile(
    r"^\s*dispositivo(?:s)?\s*[:\-]?\s*(.+?)\s*$",
    re.IGNORECASE,
)

# Explicit heading → expected Jira project prefixes. Unknown headings do not warn.
_HEADING_PREFIXES: dict[str, set[str]] = {
    "ADT": {"ADTCL", "ADTPR"},
    "WIN": {"WINCL", "WINPR"},
    "WIN/XBOX": {"WINCL", "WINPR"},
    "WINDOWS": {"WINCL", "WINPR"},
    "XBOX": {"WINCL", "WINPR"},
    "WEB": {"WEBCL", "WEBPR"},
    "ADR": {"ADRPR", "ADRCL"},
    "IOS": {"IOSPR", "IOSCL"},
    "TVOS": {"TVOSPR", "TVOSCL"},
    "ROKU": {"ROKUPR", "ROKUCL"},
    "FIRETV": {"ADTCL"},
    "FIRE TV": {"ADTCL"},
    "STV": {"STVCL"},
    "AAF": {"AAFCL", "STVCL"},
}


@dataclass
class ParsedEpcItem:
    key: str
    device_heading: str | None
    line_number: int


@dataclass
class ParsedEpcPaste:
    items: list[ParsedEpcItem] = field(default_factory=list)
    devices: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    invalid_lines: list[str] = field(default_factory=list)
    mismatches: list[dict[str, str]] = field(default_factory=list)


def is_pasted_epcs_analysis(raw_analysis: Any) -> bool:
    return isinstance(raw_analysis, dict) and raw_analysis.get("source") == PASTED_SOURCE


def tickets_from_normalized_technical_epics(raw_analysis: Any) -> dict[str, list[tuple[str, str]]]:
    """Same tickets.functionality shape the RN walker feeds into generate_release_app_candidates."""
    functionality: list[tuple[str, str]] = []
    if not isinstance(raw_analysis, dict):
        return {"functionality": [], "nco": [], "tri": [], "qa_qc": []}
    normalized = raw_analysis.get("normalized")
    epics = normalized.get("technical_epics") if isinstance(normalized, dict) else None
    if not isinstance(epics, list):
        keys = rn_keys_from_normalized(raw_analysis)
        functionality = [(key, key) for key in keys]
    else:
        seen: set[str] = set()
        for item in epics:
            if isinstance(item, dict):
                key = str(item.get("id") or item.get("key") or "").strip().upper()
                title = item.get("title")
                text = str(title).strip() if title else key
            else:
                key = str(getattr(item, "id", "") or "").strip().upper()
                text = str(getattr(item, "title", None) or key)
            if not key or key in seen:
                continue
            seen.add(key)
            functionality.append((key, text or key))
    return {"functionality": functionality, "nco": [], "tri": [], "qa_qc": []}


def parse_epc_paste(text: str) -> ParsedEpcPaste:
    parsed = ParsedEpcPaste()
    current_device: str | None = None
    seen: set[str] = set()
    for index, raw_line in enumerate((text or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        heading = _DEVICE_HEADING.match(line)
        if heading:
            current_device = heading.group(1).strip()
            if current_device and current_device not in parsed.devices:
                parsed.devices.append(current_device)
            continue
        keys = [_normalize_key(match.group(1)) for match in _JIRA_KEY.finditer(line)]
        if not keys:
            parsed.invalid_lines.append(line)
            continue
        for key in keys:
            mismatch = _device_mismatch(current_device, key)
            if mismatch:
                parsed.mismatches.append(mismatch)
            if key in seen:
                if key not in parsed.duplicates:
                    parsed.duplicates.append(key)
                continue
            seen.add(key)
            parsed.items.append(
                ParsedEpcItem(key=key, device_heading=current_device, line_number=index)
            )
    return parsed


def analyze_pasted_epcs(text: str) -> ReleaseAnalysisBase:
    parsed = parse_epc_paste(text)
    keys = [item.key for item in parsed.items]
    jira_configured, artifacts_by_key = _lookup_jira(keys)
    return build_pasted_analysis(parsed, artifacts_by_key, jira_configured=jira_configured)


def build_pasted_analysis(
    parsed: ParsedEpcPaste,
    artifacts_by_key: dict[str, dict[str, Any] | None],
    *,
    jira_configured: bool,
) -> ReleaseAnalysisBase:
    observations: list[str] = []
    technical_epics: list[dict[str, Any]] = []
    jira_lookups: list[dict[str, Any]] = []
    grouped: list[dict[str, Any]] = []

    if not parsed.items:
        observations.append("No se detectaron keys de Technical Epic en el listado.")
    if parsed.invalid_lines:
        observations.append(
            "Texto ignorado (no es una Technical Epic key): "
            + ", ".join(parsed.invalid_lines[:12])
        )
    for key in parsed.duplicates:
        observations.append(f"{key}: duplicado; se conservó la primera aparición.")
    for row in parsed.mismatches:
        observations.append(
            f"{row['key']}: encabezado «Dispositivo {row['heading']}» no coincide "
            f"con el prefijo {row['prefix']}; no se reasignó."
        )
    if len(parsed.devices) > 1:
        listed = ", ".join(parsed.devices)
        observations.append(
            f"Dispositivos detectados: {listed}. "
            "Cada Technical Epic conserva su encabezado. "
            "El campo Dispositivo de la Release admite un solo valor; selecciónalo en Paso 2 "
            "(no se eligió automáticamente el primero)."
        )
    elif parsed.devices:
        observations.append(
            f"Dispositivo detectado: {parsed.devices[0]} (contexto de presentación de cada Technical Epic)."
        )
    if parsed.items and not jira_configured:
        observations.append("Jira no está configurado; no se validó la existencia de las keys.")

    by_device: dict[str, list[str]] = {}
    for item in parsed.items:
        label = item.device_heading or "(sin dispositivo)"
        by_device.setdefault(label, []).append(item.key)
    for device, device_keys in by_device.items():
        grouped.append({"device": device, "keys": device_keys})

    for item in parsed.items:
        artifact = artifacts_by_key.get(item.key)
        found = isinstance(artifact, dict)
        issuetype = str((artifact or {}).get("issuetype") or "").strip() if found else ""
        summary = str((artifact or {}).get("summary") or "").strip() if found else ""
        status = str((artifact or {}).get("status") or "").strip() if found else ""
        description = str((artifact or {}).get("description") or "") if found else ""
        acceptance = str((artifact or {}).get("acceptance_criteria") or "") if found else ""
        children = (artifact or {}).get("children") if found else []
        title: str | None
        if found:
            title = summary or None
            if not _is_expected_epic_type(issuetype):
                observations.append(
                    f"{item.key}: tipo de issue inesperado ({issuetype or 'desconocido'}); "
                    "se esperaba Technical Epic."
                )
        else:
            title = None
            if jira_configured:
                observations.append(f"{item.key}: No encontrado en Jira")
        technical_epics.append(
            {
                "id": item.key,
                "title": title,
                "section": item.device_heading or "",
                "table_header": "",
                "column": "",
                "tbrf_id": None,
                "page": 0,
                "source_category": PASTED_SOURCE,
                "normalized_category": "technical_epics",
                "device_heading": item.device_heading,
            }
        )
        jira_lookups.append(
            {
                "key": item.key,
                "found": found,
                "issuetype": issuetype or None,
                "status": status or None,
                "summary": summary or None,
                "has_description": bool(description.strip()),
                "has_acceptance_criteria": bool(acceptance.strip()),
                "child_count": len(children) if isinstance(children, list) else 0,
                "has_gherkin": _looks_like_gherkin(description, acceptance),
                "device_heading": item.device_heading,
            }
        )

    detected_devices = ", ".join(parsed.devices) if parsed.devices else None
    detected_platform = _form_platform(parsed.devices)

    return ReleaseAnalysisBase(
        pdf_filename=PASTED_FILENAME,
        pdf_file_path=None,
        detected_name=None,
        detected_version=None,
        detected_platform=detected_platform,
        detected_description=None,
        features_count=len(technical_epics),
        qa_qc_issues_count=0,
        nco_issues_count=0,
        tri_issues_count=0,
        detected_devices=detected_devices,
        proposed_coverage=None,
        estimation_text=None,
        observations=observations,
        raw_analysis={
            "source": PASTED_SOURCE,
            "filename": PASTED_FILENAME,
            "vendor": None,
            "normalized": {
                "vendor": PASTED_SOURCE,
                "device": detected_devices,
                "family": None,
                "version": None,
                "technical_epics": technical_epics,
                "nco": [],
                "qco": [],
                "qa_bugs": [],
                "qc_bugs": [],
                "tri": [],
                "incidents": [],
                "known_issues": [],
                "qa_evidence": [],
            },
            "epc_paste": {
                "devices": parsed.devices,
                "grouped": grouped,
                "duplicates": parsed.duplicates,
                "invalid_lines": parsed.invalid_lines,
                "mismatches": parsed.mismatches,
                "jira_lookups": jira_lookups,
                "jira_configured": jira_configured,
            },
        },
        qc_engine_version="v0.1",
    )


def _normalize_key(raw: str) -> str:
    return (raw or "").strip().upper()


def _device_mismatch(heading: str | None, key: str) -> dict[str, str] | None:
    if not heading:
        return None
    prefix = key.split("-", 1)[0]
    expected = _HEADING_PREFIXES.get(_heading_alias(heading))
    if expected is None:
        return None
    if prefix in expected:
        return None
    return {"key": key, "heading": heading, "prefix": prefix}


_FORM_PLATFORM_ALIASES = {
    "WIN": "WIN/XBOX",
    "WINDOWS": "WIN/XBOX",
    "XBOX": "WIN/XBOX",
    "FIRE TV": "FireTV",
    "FIRETV": "FireTV",
    "ANDROID TV": "ADT",
}


def _form_platform(devices: list[str]) -> str | None:
    """Release.platform is a single select. Never pick the first of several headings."""
    if len(devices) != 1:
        return None
    heading = devices[0].strip()
    alias = _FORM_PLATFORM_ALIASES.get(heading.upper(), heading)
    return alias


def _heading_alias(heading: str) -> str:
    compact = re.sub(r"\s+", " ", heading.strip()).upper()
    compact = compact.replace("ANDROID TV", "ADT")
    return compact


def _is_expected_epic_type(issuetype: str) -> bool:
    return "epic" in (issuetype or "").lower()


def _looks_like_gherkin(*texts: str) -> bool:
    blob = "\n".join(texts).lower()
    return "feature:" in blob or "scenario:" in blob or "scenario outline:" in blob


def _lookup_jira(keys: list[str]) -> tuple[bool, dict[str, dict[str, Any] | None]]:
    if not keys:
        return True, {}
    try:
        _require_config()
        configured = True
    except JiraNotConfiguredError:
        return False, {key: None for key in keys}
    artifacts = fetch_artifacts_for_keys(keys)
    found: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        key = _normalize_key(str(artifact.get("key") or ""))
        if key:
            found[key] = artifact
    return configured, {key: found.get(key) for key in keys}
