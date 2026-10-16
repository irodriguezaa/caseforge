"""Choose QC matrix cases for a Release App scope. Does not persist test cases.

Region is always Mexico. Cases tagged "Otras regiones" are left out.
Cases with no region, "Todas", or "MX" apply.
{MDP} uses the device's Mexico payment methods.
Deduplication against RN cases is not done here.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.qc_matrix import QcMatrixCase, QcMatrixModule, QcMatrixVersion
from app.models.release import Release

# Release.platform -> (matrix code, device code in that matrix).
# Kepler no tiene columna propia: usa FireTV (FTV) de la matriz OTT.
# Los STV de TATA (STV Tata Samsung, STV Tata Hisense, STV Tata LG y STV Tata ADT)
# aún no tienen columna y no incorporan casos. ADR sí tiene columna OTT y sigue aplicando.
PLATFORM_MATRIX: dict[str, tuple[str, str]] = {
    "WEB": ("OTT", "WEB"),
    "ADR": ("OTT", "ADR"),
    "ADT": ("OTT", "ADT"),
    "FireTV": ("OTT", "FTV"),
    "Kepler": ("OTT", "FTV"),
    "Roku": ("OTT", "ROKU"),
    "AAF Evolutivo": ("OTT", "AAF"),
    "AAF Legacy": ("OTT", "AAF"),
    "WIN/XBOX": ("OTT", "WIN"),
    "Coship9085": ("OTT", "Coship9085"),
    "iOS": ("OTT", "iOS"),
    "tvOS": ("OTT", "tvOS"),
    "STB IPTV": ("IPTV", "STB TATA"),
    "IPTV AOSP": ("IPTV", "STB TATA"),
}

BE_PLATFORM = "BE"

TATA_STV_WITHOUT_COLUMN = (
    "STV Tata Samsung",
    "STV Tata Hisense",
    "STV Tata LG",
    "STV Tata ADT",
)
_TATA_STV_NOTE = (
    "Los STV de TATA (STV Tata Samsung, STV Tata Hisense, STV Tata LG y STV Tata ADT) "
    "aún no tienen columna en la matriz y no incorporan casos de matriz."
)

TRANSACTION_MODULES = frozenset({"COM-CHK", "COM-TX", "COM-TKT", "NAV-PPE"})
_SELECTOR_SCOPES = frozenset({"Pruebas Acotadas", "Regresivo", "No Afectación"})
_SKIP_WORDS = frozenset(
    {
        "nodo",
        "para",
        "desde",
        "hacia",
        "sobre",
        "entre",
        "como",
        "esta",
        "este",
        "todos",
        "todas",
        "principal",
    }
)


def normalize_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", folded.lower()).strip()


def region_applies(region: str | None) -> bool:
    key = normalize_text(region or "")
    if not key:
        return True
    return key in {"todas", "mx"}


def suggest_touched_modules(modules: list[QcMatrixModule], raw_analysis: dict | None) -> list[dict[str, Any]]:
    """Match the module key and the module name. The group name is not used."""
    rn_words = _rn_words(raw_analysis)
    if not rn_words:
        return []
    tokens = [token for _, token in rn_words]
    hits: list[dict[str, Any]] = []
    for module in modules:
        matched = _matched_rn_words(module, rn_words, tokens)
        if matched:
            hits.append({"module_key": module.module_key, "matched_words": matched})
    return hits


def providers_mentioned(provider_names: list[str], raw_analysis: dict | None) -> list[str]:
    blob = normalize_text(_analysis_text(raw_analysis))
    if not blob:
        return []
    found = [name for name in provider_names if normalize_text(name) and normalize_text(name) in blob]
    return found


def select_matrix_cases(
    db: Session,
    *,
    platform: str,
    validation_type: str | None,
    touched_modules: list[str] | None,
    template_values: dict[str, str] | None,
    raw_analysis: dict | None,
    pinned_version_id: int | None,
) -> dict[str, Any]:
    mapping = PLATFORM_MATRIX.get(platform)
    if mapping is None:
        note = _TATA_STV_NOTE if platform in TATA_STV_WITHOUT_COLUMN else f"El dispositivo {platform} no tiene matriz QC publicada."
        return _empty(platform, validation_type, note=note)
    matrix_code, device_code = mapping
    matrix = _resolve_matrix(db, matrix_code, pinned_version_id)
    if matrix is None:
        return _empty(
            platform,
            validation_type,
            matrix_code=matrix_code,
            device_code=device_code,
            note=f"No hay una versión publicada de la matriz {matrix_code}.",
        )

    device = next((item for item in matrix.devices if item.code == device_code), None)
    if device is None:
        return _empty(
            platform,
            validation_type,
            matrix_code=matrix_code,
            device_code=device_code,
            matrix_version_id=matrix.id,
            matrix_version=matrix.version,
            note=f"La matriz {matrix_code} {matrix.version} no tiene el dispositivo {device_code}.",
        )

    payment_methods = [str(item) for item in (device.mdp_mx or []) if str(item).strip()]
    suggestions = suggest_touched_modules(matrix.modules, raw_analysis)
    suggested = [item["module_key"] for item in suggestions]
    catalog = {module.module_key: module for module in matrix.modules}
    scope = (validation_type or "").strip()
    manual = _catalog_keys(touched_modules, catalog)
    if scope == "Pruebas Acotadas":
        effective = manual or []
    elif manual is None:
        effective = suggested
    else:
        effective = manual
    related = _related_keys(effective, catalog)
    expanded = list(dict.fromkeys([*effective, *related]))
    applicable = [
        case
        for case in matrix.cases
        if _on_device(case, device.id) and region_applies(case.region) and _keeps_transaction(case, payment_methods)
    ]
    by_module: dict[str, list[QcMatrixCase]] = {}
    for case in applicable:
        key = case.module.module_key if case.module else ""
        by_module.setdefault(key, []).append(case)

    if scope in {"", "N/A"} or scope not in {
        "Pruebas Acotadas",
        "Smoke Test",
        "Regresivo",
        "No Afectación",
        "Regresión completa",
    }:
        chosen: list[QcMatrixCase] = []
        note = (
            "No se incorporan casos de matriz por este concepto."
            if scope == "N/A"
            else "Este alcance no selecciona casos de la matriz."
        )
    elif scope == "Smoke Test":
        chosen = [case for case in applicable if case.smoke]
        note = ""
    elif scope == "Pruebas Acotadas":
        chosen = [case for key in effective for case in by_module.get(key, [])]
        note = "" if effective else "Pruebas Acotadas no trae casos hasta que QC elige los módulos."
    elif scope == "Regresivo":
        chosen = [case for key in expanded for case in by_module.get(key, [])]
        note = "" if effective else "No hay módulos tocados. QC puede marcarlos para armar el Regresivo."
    elif scope == "No Afectación":
        blocked = set(effective)
        chosen = [case for key, rows in by_module.items() if key not in blocked for case in rows]
        note = ""
    else:
        regresivo = {case.id for key in expanded for case in by_module.get(key, [])}
        no_afectacion = {case.id for key, rows in by_module.items() if key not in set(effective) for case in rows}
        chosen = [case for case in applicable if case.id in regresivo or case.id in no_afectacion]
        note = ""

    rn_providers = providers_mentioned(list(matrix.providers or []), raw_analysis)
    overrides = {key.upper(): value.strip() for key, value in (template_values or {}).items() if value and value.strip()}
    providers = _provider_names(overrides.get("PROVEEDOR", ""), rn_providers, list(matrix.providers or []))
    rendered_by_module: dict[str, list[dict[str, Any]]] = {}
    rendered: list[dict[str, Any]] = []
    chosen_ids = {case.id for case in chosen}
    for case in applicable:
        key = case.module.module_key if case.module else ""
        rows = _render_case(case, payment_methods, providers)
        device_note = next(
            (
                link.note.strip()
                for link in case.device_links
                if link.device_id == device.id and (link.note or "").strip()
            ),
            "",
        )
        user_types = [str(item).strip() for item in (case.user_types or []) if str(item).strip()]
        module_name = case.module.name if case.module else key
        for row in rows:
            row["device_note"] = device_note
            row["user_types"] = user_types
            row["module_name"] = module_name
        rendered_by_module.setdefault(key, []).extend(rows)
        if case.id in chosen_ids:
            rendered.extend(rows)
    module_rows = [
        {
            "module_key": module.module_key,
            "name": module.name,
            "group_name": module.group_name,
            "description": module.description,
            "related": [link.related_key for link in module.relations],
            "device_case_count": len(rendered_by_module.get(module.module_key, [])),
        }
        for module in sorted(matrix.modules, key=lambda item: item.module_key)
    ]
    summary = _impact_summary(scope, len(rendered), effective, related, module_rows)
    return {
        "platform": platform,
        "device_code": device_code,
        "matrix_code": matrix_code,
        "matrix_version_id": matrix.id,
        "matrix_version": matrix.version,
        "matrix_status": matrix.status,
        "region": "MX",
        "validation_type": scope,
        "suggested_modules": suggested,
        "suggestions": suggestions,
        "touched_modules": effective,
        "related_modules": related,
        "payment_methods_mx": payment_methods,
        "transactions_included": bool(payment_methods),
        "template_values": overrides,
        "providers_applied": providers,
        "modules": module_rows,
        "case_count": len(rendered),
        "cases": rendered,
        "note": note,
        "impact_summary": summary,
        "show_module_selector": scope in _SELECTOR_SCOPES,
        "deduplicated": False,
    }


def unique_matrix_devices() -> list[tuple[str, str, str]]:
    """One (platform, matrix, device) per matrix column. Kepler shares FireTV's FTV column."""
    seen: set[tuple[str, str]] = set()
    targets: list[tuple[str, str, str]] = []
    for platform, (matrix_code, device_code) in PLATFORM_MATRIX.items():
        key = (matrix_code, device_code)
        if key in seen:
            continue
        seen.add(key)
        targets.append((platform, matrix_code, device_code))
    return targets


def select_be_matrix_cases(
    db: Session,
    *,
    validation_type: str | None,
    touched_modules: list[str] | None,
    template_values: dict[str, str] | None,
    raw_analysis: dict | None,
    pinned_version_id: int | None,
) -> dict[str, Any]:
    """Same App scope rules, run on every mapped OTT/IPTV device. The backend is what changed."""
    targets = unique_matrix_devices()
    merged_cases: list[dict[str, Any]] = []
    modules_by_key: dict[str, dict[str, Any]] = {}
    suggestions_by_key: dict[str, dict[str, Any]] = {}
    suggested_order: list[str] = []
    touched_union: list[str] = []
    related_union: list[str] = []
    notes: list[str] = []
    versions: list[str] = []
    payment: list[str] = []
    providers: list[str] = []
    last_good: dict[str, Any] | None = None
    for platform, matrix_code, device_code in targets:
        preview = select_matrix_cases(
            db,
            platform=platform,
            validation_type=validation_type,
            touched_modules=touched_modules,
            template_values=template_values,
            raw_analysis=raw_analysis,
            pinned_version_id=pinned_version_id,
        )
        if preview.get("matrix_code"):
            version = f"{preview.get('matrix_code')} {preview.get('matrix_version') or ''}".strip()
            if version not in versions:
                versions.append(version)
            last_good = preview
        note = (preview.get("note") or "").strip()
        if note:
            notes.append(note)
        for row in preview.get("cases") or []:
            stamped = dict(row)
            stamped["platform"] = platform
            stamped["device_code"] = preview.get("device_code") or device_code
            stamped["matrix_code"] = preview.get("matrix_code") or matrix_code
            stamped["matrix_version"] = preview.get("matrix_version") or ""
            merged_cases.append(stamped)
        for module in preview.get("modules") or []:
            key = module["module_key"]
            existing = modules_by_key.get(key)
            if existing is None:
                modules_by_key[key] = dict(module)
            else:
                existing["device_case_count"] = int(existing.get("device_case_count") or 0) + int(
                    module.get("device_case_count") or 0
                )
        for item in preview.get("suggestions") or []:
            key = item["module_key"]
            if key not in suggestions_by_key:
                suggestions_by_key[key] = item
                suggested_order.append(key)
        for key in preview.get("touched_modules") or []:
            if key not in touched_union:
                touched_union.append(key)
        for key in preview.get("related_modules") or []:
            if key not in related_union:
                related_union.append(key)
        for method in preview.get("payment_methods_mx") or []:
            if method not in payment:
                payment.append(method)
        for name in preview.get("providers_applied") or []:
            if name not in providers:
                providers.append(name)

    scope = (validation_type or "").strip()
    count = len(merged_cases)
    unique_notes = list(dict.fromkeys(notes))
    note = ""
    if count == 0:
        if scope == "N/A":
            note = "No se incorporan casos de matriz por este concepto."
        elif unique_notes:
            note = unique_notes[0]
    verb = "Se agregará" if count == 1 else "Se agregarán"
    summary = f"{verb} {_quantity(count, 'caso', 'casos')} en {_quantity(len(targets), 'dispositivo', 'dispositivos')} OTT/IPTV."
    base = last_good or _empty(BE_PLATFORM, validation_type, note=note)
    return {
        **base,
        "platform": BE_PLATFORM,
        "device_code": "ALL",
        "matrix_code": "OTT+IPTV" if versions else "",
        "matrix_version_id": None,
        "matrix_version": ", ".join(versions),
        "validation_type": scope,
        "suggested_modules": suggested_order,
        "suggestions": [suggestions_by_key[key] for key in suggested_order],
        "touched_modules": touched_union,
        "related_modules": related_union,
        "payment_methods_mx": payment,
        "transactions_included": bool(payment),
        "providers_applied": providers,
        "modules": list(modules_by_key.values()),
        "case_count": count,
        "cases": merged_cases,
        "note": note,
        "impact_summary": summary if scope not in {"", "N/A"} else "",
        "show_module_selector": scope == "Pruebas Acotadas" and bool(modules_by_key),
        "deduplicated": False,
    }


def pin_published_matrix(db: Session, release: Release) -> None:
    if release.qc_matrix_version_id is not None:
        return
    if release.be_release_id is not None or release.operativa_release_id is not None:
        return
    mapping = PLATFORM_MATRIX.get(release.platform)
    if mapping is None:
        return
    published = db.execute(
        select(QcMatrixVersion).where(
            QcMatrixVersion.code == mapping[0],
            QcMatrixVersion.status == "published",
        )
    ).scalar_one_or_none()
    if published is not None:
        release.qc_matrix_version_id = published.id


def _resolve_matrix(db: Session, code: str, pinned_version_id: int | None) -> QcMatrixVersion | None:
    loader = (
        selectinload(QcMatrixVersion.modules).selectinload(QcMatrixModule.relations),
        selectinload(QcMatrixVersion.devices),
        selectinload(QcMatrixVersion.cases).selectinload(QcMatrixCase.device_links),
        selectinload(QcMatrixVersion.cases).selectinload(QcMatrixCase.module),
    )
    if pinned_version_id is not None:
        pinned = db.execute(
            select(QcMatrixVersion).where(QcMatrixVersion.id == pinned_version_id).options(*loader)
        ).scalar_one_or_none()
        if pinned is not None and pinned.code == code:
            return pinned
    return db.execute(
        select(QcMatrixVersion)
        .where(QcMatrixVersion.code == code, QcMatrixVersion.status == "published")
        .options(*loader)
    ).scalar_one_or_none()


def _on_device(case: QcMatrixCase, device_id: int) -> bool:
    return any(link.device_id == device_id for link in case.device_links)


def _keeps_transaction(case: QcMatrixCase, payment_methods: list[str]) -> bool:
    if payment_methods:
        return True
    module_key = case.module.module_key if case.module else ""
    if module_key in TRANSACTION_MODULES:
        return False
    blob = f"{case.title}\n{case.steps}\n{case.expected}"
    return "{MDP}" not in blob


def _catalog_keys(keys: list[str] | None, catalog: dict[str, QcMatrixModule]) -> list[str] | None:
    if keys is None:
        return None
    return [key for key in dict.fromkeys(keys) if key in catalog]


def _related_keys(touched: list[str], catalog: dict[str, QcMatrixModule]) -> list[str]:
    related: list[str] = []
    for key in touched:
        module = catalog.get(key)
        if module is None:
            continue
        for link in module.relations:
            if link.related_key in catalog and link.related_key not in touched and link.related_key not in related:
                related.append(link.related_key)
    return related


def _provider_names(qc_value: str, rn_providers: list[str], matrix_providers: list[str]) -> list[str]:
    qc_names = [part.strip() for part in re.split(r"[,;]", qc_value) if part.strip()]
    if qc_names:
        return qc_names
    if rn_providers:
        return rn_providers
    return [name.strip() for name in matrix_providers if name and name.strip()]


def _render_case(case: QcMatrixCase, payment_methods: list[str], providers: list[str]) -> list[dict[str, Any]]:
    source = f"{case.title}\n{case.steps}\n{case.expected}"
    if "{PROVEEDOR}" not in source or not providers:
        return [_render_one(case, payment_methods, provider=None)]
    return [_render_one(case, payment_methods, provider=provider) for provider in providers]


def _render_one(case: QcMatrixCase, payment_methods: list[str], provider: str | None) -> dict[str, Any]:
    # {PAQUETE}, {APP} and {NIVEL} stay as written. They are not pending and not replaced.
    values = {"MDP": ", ".join(payment_methods), "PROVEEDOR": provider or ""}
    title = _fill(case.title, values)
    if provider and provider.casefold() not in title.casefold():
        title = f"{title} — {provider}"
    pending = ["PROVEEDOR"] if "{PROVEEDOR}" in f"{title}\n{case.steps}\n{case.expected}" and not provider else []
    return {
        "base_id": case.base_id,
        "module_key": case.module.module_key if case.module else "",
        "title": title,
        "steps": _fill(case.steps, values),
        "expected": _fill(case.expected, values),
        "severity": case.severity,
        "smoke": case.smoke,
        "region": case.region,
        "provider": provider,
        "pending_templates": pending,
    }


def _fill(text: str, values: dict[str, str]) -> str:
    rendered = text or ""
    for token, value in values.items():
        if value:
            rendered = rendered.replace(f"{{{token}}}", value)
    return rendered


def _impact_summary(
    scope: str,
    case_count: int,
    touched: list[str],
    related: list[str],
    modules: list[dict[str, Any]],
) -> str:
    verb = "Se agregará" if case_count == 1 else "Se agregarán"
    cases = _quantity(case_count, "caso", "casos")
    if scope == "Regresivo":
        modules_label = _quantity(len(touched) + len(related), "módulo", "módulos")
        touched_label = _quantity(len(touched), "tocado", "tocados")
        related_label = _quantity(len(related), "relacionado", "relacionados")
        return f"{verb} {cases} de {modules_label} ({touched_label} + {related_label})."
    if scope == "No Afectación":
        outside = sum(1 for module in modules if module["device_case_count"] and module["module_key"] not in set(touched))
        return f"{verb} {cases} de los {_quantity(outside, 'módulo', 'módulos')} no relacionados con el cambio."
    if scope == "Smoke Test":
        return f"{verb} {cases} smoke del dispositivo."
    if scope == "Regresión completa":
        return f"{verb} {cases} aplicables del dispositivo."
    if scope == "Pruebas Acotadas":
        return f"{verb} {cases} de los {_quantity(len(touched), 'módulo', 'módulos')} elegidos."
    return ""


def _quantity(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _analysis_text(raw_analysis: dict | None) -> str:
    if not isinstance(raw_analysis, dict):
        return ""
    normalized = raw_analysis.get("normalized")
    chunks: list[str] = []
    if isinstance(normalized, dict):
        for rows in normalized.values():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict):
                    chunks.append(str(row.get("title") or ""))
                    chunks.append(str(row.get("id") or ""))
                elif isinstance(row, str):
                    chunks.append(row)
    return " ".join(chunks)


def _rn_words(raw_analysis: dict | None) -> list[tuple[str, str]]:
    words = re.findall(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", _analysis_text(raw_analysis))
    return [(word, normalize_text(word)) for word in words if normalize_text(word)]


def _matched_rn_words(
    module: QcMatrixModule,
    rn_words: list[tuple[str, str]],
    tokens: list[str],
) -> list[str]:
    name_terms = {
        word
        for word in normalize_text(module.name).split()
        if len(word) >= 5 and word not in _SKIP_WORDS
    }
    key_tokens = [word for word in normalize_text(module.module_key.replace("-", " ")).split() if word]
    matched: list[str] = []
    key_hits = {
        index
        for index in range(len(tokens))
        if key_tokens and tokens[index : index + len(key_tokens)] == key_tokens
    }
    for index, (original, token) in enumerate(rn_words):
        in_key = any(start <= index < start + len(key_tokens) for start in key_hits)
        if (token in name_terms or in_key) and original not in matched:
            matched.append(original)
    return matched


def _empty(
    platform: str,
    validation_type: str | None,
    *,
    note: str,
    matrix_code: str = "",
    device_code: str = "",
    matrix_version_id: int | None = None,
    matrix_version: str = "",
) -> dict[str, Any]:
    return {
        "platform": platform,
        "device_code": device_code,
        "matrix_code": matrix_code,
        "matrix_version_id": matrix_version_id,
        "matrix_version": matrix_version,
        "matrix_status": "",
        "region": "MX",
        "validation_type": (validation_type or "").strip(),
        "suggested_modules": [],
        "suggestions": [],
        "touched_modules": [],
        "related_modules": [],
        "payment_methods_mx": [],
        "transactions_included": False,
        "template_values": {},
        "providers_applied": [],
        "modules": [],
        "case_count": 0,
        "cases": [],
        "note": note,
        "impact_summary": "",
        "show_module_selector": (validation_type or "").strip() in _SELECTOR_SCOPES,
        "deduplicated": False,
    }
