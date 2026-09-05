"""Official Test Cases from the approved coverage matrix + device expander.

Does not re-parse coverage, call Jira/Zephyr, or invent functional dimensions.
Materialization turns each approved preview TC into executable tester steps.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.schemas.case_generation import GeneratedCaseCandidate
from app.schemas.coverage_matrix import CoverageMatrixResponse, CoverageMatrixRow
from app.schemas.matrix_preview import PreviewTestCase
from app.services.operativa_engine.matrix_expand import expand_matrix_preview
from app.services.operativa_engine.matrix_steps import (
    _METADATA_EXPECTED_RE,
    _METADATA_STEP_RE,
    _TRUNCATED_COUNTRY_RE,
    build_executable_steps,
    build_tester_test_data,
    execution_precondition,
    execution_sets,
    extract_countries,
    extract_frequency,
    extract_prices,
    is_negative_source,
    source_text,
)

ENGINE_VERSION = "operativa-v4.0-executable-tc"
_BEHAVIOR_KEY_RE = re.compile(r"Comportamiento:\s*(\S+)")
_BROKEN_EXTRACT_RE = re.compile(r"\bID\s*$|�|\|{2,}")


def split_semi(value: object) -> list[str]:
    text = "" if value is None else str(value).strip()
    if not text or text == "—":
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


def load_approved_matrix(path: Path, *, release_id: int, release_name: str) -> CoverageMatrixResponse:
    """Load the frozen diagnostic JSON. Does not fetch Jira/Confluence."""
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = [matrix_row_from_export(item) for item in payload.get("rows") or []]
    brfs = {row.brf_key for row in rows}
    return CoverageMatrixResponse(
        status="MATRIX",
        engine="operativa-v3.1-coverage-matrix",
        release_id=release_id,
        release_name=release_name,
        brfs_analyzed=len(brfs),
        row_count=len(rows),
        rows=rows,
    )


def matrix_row_from_export(item: dict) -> CoverageMatrixRow:
    evidence = str(item.get("evidence") or "")
    key_match = _BEHAVIOR_KEY_RE.search(evidence)
    behavior_title = str(item.get("behavior") or "").strip()
    brf = str(item.get("BRF") or "").strip()
    hn_keys = split_semi(item.get("HN/CA"))
    behavior_key = (
        key_match.group(1)
        if key_match
        else f"{brf}:{hn_keys[0] if hn_keys else 'row'}:{re.sub(r'[^a-z0-9]+', '-', behavior_title.lower())[:60]}"
    )
    origin = str(item.get("origin") or "directo")
    if origin not in {"directo", "derivado", "inferencia", "QC_REVIEW"}:
        origin = "QC_REVIEW" if item.get("QC_REVIEW") else "directo"
    risk = str(item.get("duplicate_risk") or "UNIQUE")
    if risk not in {"UNIQUE", "POSSIBLE_DUPLICATE", "OVERLAP"}:
        risk = "UNIQUE"
    scope = str(item.get("scope_status") or "IN_SCOPE")
    if scope not in {"IN_SCOPE", "OUT_OF_SCOPE"}:
        scope = "OUT_OF_SCOPE" if origin == "QC_REVIEW" else "IN_SCOPE"
    return CoverageMatrixRow(
        brf_key=brf,
        epc_keys=split_semi(item.get("EPCs")),
        hn_keys=hn_keys,
        behavior_key=behavior_key,
        behavior_title=behavior_title,
        # Legacy diagnostic JSON used "surfaces"; canonical field is interaction_points.
        interaction_points=split_semi(item.get("interaction_points") or item.get("surfaces")),
        channel=str(item.get("channel") or "").strip() or None,
        ecosystem=str(item.get("ecosystem") or "").strip() or None,
        applicable_devices=split_semi(item.get("applicable_devices")),
        relevant_users=split_semi(item.get("relevant_users")),
        transactional=bool(item.get("transactional")),
        mdp=split_semi(item.get("MDP")),
        test_data=str(item.get("test_data") or "").strip() or None,
        origin=origin,  # type: ignore[arg-type]
        source=str(item.get("source") or "BRF/HN"),
        hn_source=str(item.get("hn_source") or "") or None,
        scope_status=scope,  # type: ignore[arg-type]
        behavior_reason=str(item.get("behavior_reason") or "") or None,
        reasoning=str(item.get("reasoning") or "") or None,
        evidence=evidence or f"BRF: {brf}",
        applicability_reason=str(item.get("reasoning") or "Fila de matriz aprobada."),
        duplicate_risk=risk,  # type: ignore[arg-type]
        duplicate_with=split_semi(item.get("duplicate_with")),
        rules=["65.4"],
    )


def materialize_official_candidates(
    matrix: CoverageMatrixResponse,
) -> tuple[list[GeneratedCaseCandidate], list[str]]:
    preview = expand_matrix_preview(matrix)
    by_key = {row.behavior_key: row for row in matrix.rows}
    candidates: list[GeneratedCaseCandidate] = []
    warnings = list(preview.warnings)
    for case in preview.cases:
        candidate, extra = materialize_preview_case(case, by_key.get(case.behavior_key))
        candidates.append(candidate)
        warnings.extend(extra)
    return candidates, warnings


def materialize_preview_case(
    preview: PreviewTestCase,
    matrix_row: CoverageMatrixRow | None,
) -> tuple[GeneratedCaseCandidate, list[str]]:
    steps, warnings = build_executable_steps(preview)
    test_data = build_tester_test_data(preview)
    hn = ", ".join(preview.hn_keys) if preview.hn_keys else "—"
    points = list(preview.interaction_points)
    if preview.channel == "Email" and "Email" not in points and "Correo de bienvenida" not in points:
        points.append("Email")
    interaction = ", ".join(points) if points else "—"
    users = preview.user_type or (
        "; ".join(preview.relevant_users) if preview.relevant_users else None
    )
    mdp = "; ".join(preview.mdp) if preview.mdp else None
    device_label = preview.device or (preview.channel if preview.channel else None)
    use_case = preview.use_case_title or "comportamiento"
    description = "\n".join(
        part
        for part in (
            f"BRF {preview.brf_key} · HN/CA {hn} · {preview.behavior_title}.",
            f"Caso de uso: {use_case}.",
            f"Canal / Punto de interacción: {interaction}.",
            f"Ecosistema: {preview.ecosystem or '—'} · País: {preview.country or '—'} · Ejecución: {device_label or '—'}.",
            f"Usuario: {users or 'sin split de usuario'}.",
            f"Transaccional: {'sí' if preview.transactional else 'no'}"
            + (f" · MDP: {mdp}" if mdp else " · MDP: no declarado (no inventado)."),
            f"Origin {preview.origin} · {preview.scope_status}.",
        )
    )
    candidate = GeneratedCaseCandidate(
        name=_case_name(preview)[:250],
        description=description,
        precondition=execution_precondition(preview),
        requires_condition=is_negative_source(preview) or preview.channel == "Email",
        steps=steps,
        test_data=test_data or None,
        related_functionality=preview.brf_key,
        related_jira=", ".join(preview.epc_keys) or None,
        related_rn=preview.brf_key,
        evidence=preview.evidence,
        justification=(preview.expansion_reason or "")[:4000],
        confidence="high",
        review_required=bool(warnings),
        priority="CRITICAL",
        user_type=preview.user_type or users,
        component=preview.brf_key,
        applied_rules=["matriz-aprobada", "caso-de-uso", "expansor-contexto-ejecucion", "tc-ejecutable"],
        generation_origin=preview.origin,
        device=preview.device,
        country=preview.country,
        device_source="applicable_devices de la matriz aprobada"
        if preview.device
        else ("Canal Email (matriz)" if preview.channel == "Email" else None),
        mdp=mdp,
        behavior=preview.behavior_title,
        hn_keys=list(preview.hn_keys),
        candidate_id=(
            f"{preview.behavior_key}:{preview.use_case_key}:"
            f"{preview.country or 'na'}:{preview.device or preview.channel or 'na'}"
        ),
        duplicate_status=preview.duplicate_risk,
        duplicate_with=list(preview.duplicate_with),
        priority_reason="Lote desde matriz; prioridad por defecto CRITICAL.",
        ecosystem=preview.ecosystem,
        applicability_reason=preview.expansion_reason,
        group_id=preview.behavior_key[:80],
        interaction_points=list(preview.interaction_points),
        hn_source=matrix_row.hn_source if matrix_row else None,
        use_case_key=preview.use_case_key,
        use_case_title=preview.use_case_title,
        access_path=preview.access_path,
    )
    return candidate, warnings


def _case_name(preview: PreviewTestCase) -> str:
    parts = [preview.behavior_title]
    if preview.use_case_title:
        parts.append(preview.use_case_title)
    if preview.country:
        parts.append(preview.country)
    parts.append(preview.device or preview.channel or "sin-dispositivo")
    return " · ".join(parts)


def audit_official_candidates(
    matrix: CoverageMatrixResponse,
    candidates: list[GeneratedCaseCandidate],
) -> dict:
    preview = expand_matrix_preview(matrix)
    omitted_qc = sum(1 for row in matrix.rows if row.origin == "QC_REVIEW")
    omitted_oos = sum(1 for row in matrix.rows if row.scope_status == "OUT_OF_SCOPE")
    findings: list[dict] = []

    def add(kind: str, detail: str, candidate: GeneratedCaseCandidate | None = None) -> None:
        findings.append(
            {
                "severity": "ERROR",
                "kind": kind,
                "detail": detail,
                "brf": candidate.related_functionality if candidate else None,
                "name": candidate.name if candidate else None,
                "example_step": (candidate.steps[0].action if candidate and candidate.steps else None),
                "example_expected": (candidate.steps[0].expected_result if candidate and candidate.steps else None),
            }
        )

    matrix_by_key = {row.behavior_key: row for row in matrix.rows}
    seen: dict[tuple, int] = {}
    for candidate in candidates:
        row = matrix_by_key.get(candidate.group_id or "")
        blob = source_text(
            PreviewTestCase(
                brf_key=candidate.related_functionality or "",
                hn_keys=list(candidate.hn_keys or []),
                behavior_key=candidate.group_id or "",
                behavior_title=candidate.behavior or "",
                evidence=candidate.evidence or "",
                test_data=candidate.test_data,
                expansion_reason="",
            )
        ) if candidate.evidence else (candidate.test_data or "")
        joined_steps = " ".join(step.action for step in candidate.steps)
        joined_expected = " ".join(step.expected_result for step in candidate.steps)
        if _METADATA_STEP_RE.search(joined_steps):
            add("ERROR_metadata_como_accion", "Step menciona BRF/HN/EPC/matriz/metadata como acción.", candidate)
        if re.search(r"abrir\s+(?:el\s+)?brf|validar\s+(?:el\s+)?brf|menciona que se debe abrir", joined_steps, re.I):
            add("ERROR_abrir_brf", "Step pide abrir o validar un BRF en el dispositivo.", candidate)
        if _METADATA_EXPECTED_RE.search(joined_expected):
            add("ERROR_metadata_como_expected", "Expected describe metadata del motor, no un resultado observable.", candidate)
        if not candidate.hn_keys:
            add("ERROR_perdida_hn", "TC sin HN/CA.", candidate)
        if row and row.hn_keys and set(row.hn_keys) - set(candidate.hn_keys):
            add("ERROR_perdida_hn", "HN de la matriz no copiadas al TC.", candidate)
        if row and row.interaction_points and set(row.interaction_points) - set(candidate.interaction_points or []):
            add(
                "ERROR_perdida_puntos_interaccion",
                "Canal / Punto de interacción de la matriz no copiado al TC.",
                candidate,
            )
        if row and row.applicable_devices and candidate.device and candidate.device not in row.applicable_devices:
            add("ERROR_perdida_dispositivos", "Dispositivo del TC no está en applicable_devices.", candidate)
        if row and row.applicable_devices and row.channel != "Email" and not candidate.device:
            add("ERROR_sin_dispositivo", "La HN tiene dispositivos aplicables y el TC no tiene dispositivo.", candidate)
        if row and row.channel == "Email" and candidate.device:
            add("ERROR_canal_como_dispositivo", "Email materializado como dispositivo.", candidate)
        source_countries = extract_countries((row.evidence if row else "") or blob)
        td = candidate.test_data or ""
        td_countries = extract_countries(td)
        if len(source_countries) >= 2:
            if not candidate.country and not td_countries:
                add("ERROR_sin_pais", "La HN declara países y el TC no tiene país de ejecución.", candidate)
            if len(td_countries) > 1 or "conjunto" in td.lower():
                add("ERROR_paises_agrupados", "Varios países quedaron en el mismo TC.", candidate)
            if candidate.country and td_countries and candidate.country not in td_countries:
                add("ERROR_paises_perdidos", "El país del TC no coincide con Test Data.", candidate)
        if _TRUNCATED_COUNTRY_RE.search(td + joined_steps + joined_expected + (candidate.evidence or "")):
            add("ERROR_paises_truncados", "País truncado o extraído de forma incompleta.", candidate)
        source_has_data = bool(
            extract_prices(blob)
            or extract_frequency(blob)
            or (row and (row.test_data or row.mdp))
        )
        if source_has_data and not (candidate.test_data or "").strip():
            add("ERROR_test_data_vacio", "La fuente tiene datos y el TC quedó sin Test Data.", candidate)
        preview_for_sets = PreviewTestCase(
            brf_key=candidate.related_functionality or "",
            hn_keys=list(candidate.hn_keys or []),
            behavior_key=candidate.group_id or "",
            behavior_title=candidate.behavior or "",
            evidence=candidate.evidence or "",
            test_data=candidate.test_data,
            expansion_reason="",
            relevant_users=[
                part.strip()
                for part in (candidate.user_type or "").split(";")
                if part.strip()
            ],
        )
        for dimension, values, _action, _expected in execution_sets(preview_for_sets):
            token = {
                "usuario": "cada tipo de usuario",
                "canal": "cada canal",
            }.get(dimension, f"cada {dimension}")
            if token not in joined_steps.lower():
                add(
                    "ERROR_dimension_sin_ejecucion",
                    f"La dimensión {dimension} ({', '.join(values)}) está en el TC pero ningún Step indica cómo ejecutarla.",
                    candidate,
                )
        if blob and extract_frequency(blob) and extract_frequency(blob) not in (candidate.test_data or "") + joined_expected:
            add("ERROR_datos_truncados", "Frecuencia de fuente no aparece en Test Data ni Expected.", candidate)
        for price in extract_prices(blob):
            if price.replace(" ", "") not in ((candidate.test_data or "") + joined_expected).replace(" ", ""):
                add("ERROR_datos_truncados", f"Precio {price} no copiado al TC.", candidate)
        if _BROKEN_EXTRACT_RE.search(joined_steps + joined_expected + (candidate.test_data or "")):
            add("ERROR_datos_truncados", "Texto de extracción roto en el TC.", candidate)
        if row and is_negative_source(
            PreviewTestCase(
                brf_key=row.brf_key,
                hn_keys=list(row.hn_keys),
                behavior_key=row.behavior_key,
                behavior_title=row.behavior_title,
                evidence=row.evidence,
                test_data=row.test_data,
                expansion_reason="",
            )
        ):
            if re.search(r"se muestra correctamente|está disponible para reproducción", joined_expected, re.I):
                add("ERROR_perdida_polaridad", "Expected invierte una HN negativa.", candidate)
        if not candidate.related_functionality or not candidate.evidence:
            add("ERROR_sin_trazabilidad", "Falta BRF o evidencia.", candidate)
        if not candidate.name or candidate.name.endswith(" · "):
            add("ERROR_nombre_incompleto", "Nombre de TC vacío o truncado.", candidate)
        dup_key = (
            candidate.group_id or candidate.behavior or "",
            candidate.device,
            candidate.country,
            row.channel if row else None,
        )
        seen[dup_key] = seen.get(dup_key, 0) + 1

    got_countries: dict[str, set[str]] = {}
    for candidate in candidates:
        key = candidate.group_id or ""
        got_countries.setdefault(key, set())
        if candidate.country:
            got_countries[key].add(candidate.country)
    for row in matrix.rows:
        needed = extract_countries((row.evidence or "") + "\n" + (row.test_data or ""))
        if len(needed) < 2:
            continue
        missing = [name for name in needed if name not in got_countries.get(row.behavior_key, set())]
        if missing:
            add(
                "ERROR_paises_perdidos",
                f"{row.behavior_key}: países no materializados: {', '.join(missing)}.",
                None,
            )

    for key, count in seen.items():
        if count > 1:
            add("ERROR_duplicados", f"{key} generado {count} veces.", None)

    if len(candidates) != preview.preview_tc_count:
        add("ERROR_conteo", f"TCs {len(candidates)} ≠ preview {preview.preview_tc_count}.", None)

    by_brf: dict[str, dict[str, int]] = {}
    for row in matrix.rows:
        stats = by_brf.setdefault(
            row.brf_key,
            {"matrix": 0, "qc_review": 0, "out_of_scope": 0, "generated": 0},
        )
        stats["matrix"] += 1
        if row.origin == "QC_REVIEW":
            stats["qc_review"] += 1
        if row.scope_status == "OUT_OF_SCOPE":
            stats["out_of_scope"] += 1
    for candidate in candidates:
        key = candidate.related_functionality or "—"
        by_brf.setdefault(key, {"matrix": 0, "qc_review": 0, "out_of_scope": 0, "generated": 0})
        by_brf[key]["generated"] += 1

    counts: dict[str, int] = {}
    for item in findings:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1

    return {
        "preview_tc_count": preview.preview_tc_count,
        "official_tc_count": len(candidates),
        "qc_review_rows": omitted_qc,
        "out_of_scope_rows": omitted_oos,
        "findings": findings,
        "finding_counts": counts,
        "by_brf": by_brf,
        "warnings": preview.warnings,
        "examples": findings[:12],
    }
