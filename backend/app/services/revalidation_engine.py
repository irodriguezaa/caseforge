"""Incremental generation for Release Apps (Evolutivo with history and Revalidación).

Baseline is every prior Release of the same deliverable_id, not only the selected origin.
Does not copy, delete, or mutate historical Test Cases.
Does not change first-Release generation (see ai_case_engine.generate_release_app_candidates).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from app.schemas.case_generation import (
    CandidateStep,
    GeneratedCaseCandidate,
    GenerateCasesResponse,
)

_JIRA_KEY = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_OBSERVABLE = re.compile(
    r"\b(usuario|pantalla|muestra|oculta|error|reproduce|ingresa|selecciona|"
    r"modal|banner|login|pago|checkout|reproducci|observa|flujo|correg|fix|"
    r"validar|comportamiento)\b",
    re.IGNORECASE,
)
_CHANGE_MARKERS = re.compile(
    r"\b(cambi[oó]|modific|actualiz|ahora\b|ya no\b|se agreg|se a[nñ]ad|"
    r"correg|fix|nuevo comportamiento|en esta versi[oó]n)\b",
    re.IGNORECASE,
)


def extract_jira_keys(*texts: str | None) -> set[str]:
    found: set[str] = set()
    for text in texts:
        if not text:
            continue
        found.update(_JIRA_KEY.findall(text.upper()))
    return found


def origin_coverage_by_key(origin_cases: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Jira key → historical test_case_id labels that mention it."""
    index: dict[str, list[str]] = {}
    for row in origin_cases:
        label = (row.get("test_case_id") or row.get("test_case_name") or "").strip()
        blob = " ".join(
            str(row.get(field) or "")
            for field in (
                "test_case_id",
                "test_case_name",
                "description",
                "technical_story",
                "technical_epic",
                "evidence",
                "justification",
            )
        )
        for key in extract_jira_keys(blob):
            index.setdefault(key, []).append(label)
    return index


def has_stable_jira_key(ticket_id: str | None) -> bool:
    raw = (ticket_id or "").strip().upper()
    if not raw:
        return False
    return bool(_JIRA_KEY.fullmatch(raw))


def identity_coverage_by_key(origin_cases: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Keys bound to a historical TC via technical_story / technical_epic only.

    Incidental mentions in evidence, justification, or description do not count as coverage.
    """
    index: dict[str, list[str]] = {}
    for row in origin_cases:
        label = (row.get("test_case_id") or row.get("test_case_name") or "").strip()
        for key in extract_jira_keys(row.get("technical_story"), row.get("technical_epic")):
            index.setdefault(key, []).append(label)
    return index


def historical_item_has_explicit_change(current_cell: str, prior_cell: str | None) -> bool:
    """Delta vs a prior RN cell of the same key. No prior cell → cannot prove change."""
    if not prior_cell:
        return False
    return functionality_cell_has_real_change(current_cell, prior_cell)


def nco_has_validation_evidence(ticket_id: str, cell_text: str) -> bool:
    remainder = _JIRA_KEY.sub(" ", cell_text or "")
    remainder = re.sub(r"\s+", " ", remainder).strip()
    if len(remainder) < 40:
        return False
    other_keys = extract_jira_keys(cell_text) - {ticket_id.upper()}
    if other_keys:
        return True
    return bool(_OBSERVABLE.search(remainder))


def _normalize_cell(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def functionality_cell_has_real_change(current_cell: str, prior_cell: str | None) -> bool:
    """Compare RN functionality cells for the same Jira key. Do not use Test Case prose."""
    current = _normalize_cell(current_cell)
    if not current:
        return False
    if _CHANGE_MARKERS.search(current_cell or ""):
        prior = _normalize_cell(prior_cell)
        if not prior:
            return True
        if current == prior:
            return False
        return True
    if not prior_cell:
        return False
    prior = _normalize_cell(prior_cell)
    if current == prior:
        return False
    return SequenceMatcher(None, current, prior).ratio() < 0.92


def _related_origin_labels(ticket_id: str, cell_text: str, coverage: dict[str, list[str]]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for key in extract_jira_keys(ticket_id, cell_text) | {ticket_id.upper()}:
        for label in coverage.get(key, []):
            if label and label not in seen:
                seen.add(label)
                labels.append(label)
    return labels


@dataclass
class IncrementalPlan:
    analysis_details: list[str] = field(default_factory=list)
    new_functionality: list[tuple[str, str]] = field(default_factory=list)
    changed_functionality: list[tuple[str, str]] = field(default_factory=list)
    qa_qc: list[tuple[str, str]] = field(default_factory=list)
    nco_generate: list[tuple[str, str]] = field(default_factory=list)


def plan_incremental_generation(
    tickets: dict[str, list[tuple[str, str]]],
    baseline_cases: list[dict[str, Any]],
    prior_functionality_cells: dict[str, str] | None = None,
    prior_qa_qc_cells: dict[str, str] | None = None,
    prior_nco_cells: dict[str, str] | None = None,
) -> IncrementalPlan:
    coverage = origin_coverage_by_key(baseline_cases)
    origin_keys = set(coverage)
    identity = identity_coverage_by_key(baseline_cases)
    identity_keys = set(identity)
    prior_cells = {key.upper(): text for key, text in (prior_functionality_cells or {}).items()}
    prior_qa = {key.upper(): text for key, text in (prior_qa_qc_cells or {}).items()}
    prior_nco = {key.upper(): text for key, text in (prior_nco_cells or {}).items()}
    qa_qc = list(tickets.get("qa_qc") or [])
    nco = list(tickets.get("nco") or [])
    functionality = list(tickets.get("functionality") or [])
    change_keys = {tid.upper() for tid, _ in qa_qc} | {tid.upper() for tid, _ in nco}

    plan = IncrementalPlan()
    for ticket_id, cell_text in functionality:
        key = ticket_id.upper()
        if key not in origin_keys:
            plan.new_functionality.append((ticket_id, cell_text))
            continue
        if key in change_keys:
            plan.analysis_details.append(
                f"{ticket_id} permanece en Funcionalidades pero el RN también reporta un cambio/fix; "
                "no se duplica la cobertura original, solo el delta."
            )
            continue
        prior_cell = prior_cells.get(key)
        if functionality_cell_has_real_change(cell_text, prior_cell):
            plan.changed_functionality.append((ticket_id, cell_text))
            plan.analysis_details.append(
                f"{ticket_id} ya estaba cubierto; el RN evidencia un cambio funcional. "
                "Se genera solo el delta, no la cobertura anterior."
            )
            continue
        related = coverage.get(key) or []
        plan.analysis_details.append(
            f"No se regeneró {ticket_id}: ya hay cobertura en el histórico del Entregable"
            + (f" ({', '.join(related[:5])})" if related else "")
            + "."
        )

    for ticket_id, cell_text in qa_qc:
        if not has_stable_jira_key(ticket_id):
            plan.analysis_details.append(
                f"QA/QC {ticket_id} sin identificador estable; marcado para revisión de QC. "
                "No se deduplicó por texto ni se inventó un Test Case."
            )
            continue
        key = ticket_id.upper()
        related = identity.get(key) or []
        if key in identity_keys:
            if historical_item_has_explicit_change(cell_text, prior_qa.get(key)):
                plan.qa_qc.append((ticket_id, cell_text))
                plan.analysis_details.append(
                    f"QA/QC {ticket_id} ya tenía Test Case histórico"
                    + (f" ({', '.join(related[:5])})" if related else "")
                    + "; el RN evidencia un cambio. Se genera solo el delta."
                )
            else:
                plan.analysis_details.append(
                    f"No se regeneró QA/QC {ticket_id}: ya hay Test Case histórico ligado a la key"
                    + (f" ({', '.join(related[:5])})" if related else "")
                    + "."
                )
            continue
        plan.qa_qc.append((ticket_id, cell_text))

    for ticket_id, cell_text in nco:
        if not has_stable_jira_key(ticket_id):
            plan.analysis_details.append(
                f"NCO {ticket_id} sin identificador estable; marcado para revisión de QC. "
                "No se deduplicó por similitud de texto ni se inventó un Test Case."
            )
            continue
        key = ticket_id.upper()
        related = identity.get(key) or []
        if key in identity_keys:
            if historical_item_has_explicit_change(
                cell_text, prior_nco.get(key)
            ) and nco_has_validation_evidence(ticket_id, cell_text):
                plan.nco_generate.append((ticket_id, cell_text))
                plan.analysis_details.append(
                    f"NCO {ticket_id} ya tenía Test Case histórico"
                    + (f" ({', '.join(related[:5])})" if related else "")
                    + "; el RN evidencia un cambio. Se genera solo el delta."
                )
            else:
                plan.analysis_details.append(
                    f"No se regeneró NCO {ticket_id}: ya hay Test Case histórico ligado a la key"
                    + (f" ({', '.join(related[:5])})" if related else "")
                    + "."
                )
            continue
        if nco_has_validation_evidence(ticket_id, cell_text):
            plan.nco_generate.append((ticket_id, cell_text))
        else:
            plan.analysis_details.append(
                f"NCO {ticket_id} sin evidencia suficiente de comportamiento observable; "
                "marcado para revisión de QC. No se inventó un Test Case."
            )
    return plan


def _fix_candidate(
    *,
    ticket_id: str,
    cell_text: str,
    rn_filename: str,
    origin_release_id: int | None,
    origin_release_name: str | None,
    related_origin: list[str],
    kind: str,
) -> GeneratedCaseCandidate:
    summary = cell_text
    if ":" in cell_text:
        summary = cell_text.split(":", 1)[1].strip()
    summary = summary[:400] or ticket_id
    origin_note = ""
    if origin_release_name:
        origin_note = f"Release origen declarado: {origin_release_name}"
        if origin_release_id is not None:
            origin_note += f" (id={origin_release_id})"
        origin_note += ". "
    origin_note += (
        f"Casos históricos relacionados: {', '.join(related_origin)}. "
        if related_origin
        else "Sin vínculo a un TC histórico con evidencia de clave Jira. "
    )
    name = f"Validar corrección {ticket_id}: {summary[:160]}"
    justification = (
        origin_note
        + f"Generación incremental: el RN clasifica {ticket_id} como {kind}. "
        "No se copia la cobertura funcional ya validada; se cubre el cambio/fix evidenciado."
    )
    steps = [
        CandidateStep(
            step_number=1,
            action="El usuario recorre el flujo afectado por la corrección descrita en el RN.",
            expected_result="Se observa el comportamiento corregido declarado en el RN, sin revalidar funcionalidades no modificadas.",
        )
    ]
    return GeneratedCaseCandidate(
        name=name[:250],
        description=summary[:2000],
        steps=steps,
        related_functionality=ticket_id,
        related_jira=ticket_id,
        related_rn=rn_filename,
        evidence=cell_text[:2000],
        justification=justification[:4000],
        possible_duplicate_of=related_origin[0] if related_origin else None,
        confidence="medium",
        review_required=True,
        basic_validation=False,
        priority="CRITICAL",
        generation_origin=f"incremental-{kind}",
        origin_release_id=origin_release_id,
        origin_release_name=origin_release_name,
        related_origin_case_ids=related_origin,
        applied_rules=["incremental-delta"],
    )


def _functional_change_candidate(
    *,
    ticket_id: str,
    cell_text: str,
    rn_filename: str,
    origin_release_id: int | None,
    origin_release_name: str | None,
    related_origin: list[str],
) -> GeneratedCaseCandidate:
    summary = cell_text.split(":", 1)[1].strip() if ":" in cell_text else cell_text
    summary = summary[:400] or ticket_id
    origin_note = ""
    if origin_release_name:
        origin_note = f"Release origen declarado: {origin_release_name}. "
    return GeneratedCaseCandidate(
        name=(f"Validar cambio funcional {ticket_id}: {summary[:140]}")[:250],
        description=summary[:2000],
        steps=[
            CandidateStep(
                step_number=1,
                action="El usuario recorre el flujo del cambio funcional descrito en el RN.",
                expected_result="Se observa el comportamiento modificado declarado, sin regenerar la cobertura ya validada.",
            )
        ],
        related_functionality=ticket_id,
        related_jira=ticket_id,
        related_rn=rn_filename,
        evidence=cell_text[:2000],
        justification=(
            origin_note
            + f"La clave {ticket_id} ya tenía cobertura; el RN evidencia un cambio. "
            "Se genera solo el delta, no toda la funcionalidad anterior."
        )[:4000],
        possible_duplicate_of=related_origin[0] if related_origin else None,
        confidence="medium",
        review_required=True,
        basic_validation=False,
        priority="CRITICAL",
        generation_origin="incremental-functional-change",
        origin_release_id=origin_release_id,
        origin_release_name=origin_release_name,
        related_origin_case_ids=related_origin,
        applied_rules=["incremental-delta"],
    )


def candidates_from_incremental_plan(
    plan: IncrementalPlan,
    *,
    rn_filename: str,
    origin_release_id: int | None,
    origin_release_name: str | None,
    baseline_cases: list[dict[str, Any]],
) -> list[GeneratedCaseCandidate]:
    coverage = origin_coverage_by_key(baseline_cases)
    candidates: list[GeneratedCaseCandidate] = []
    for ticket_id, cell_text in plan.changed_functionality:
        related = _related_origin_labels(ticket_id, cell_text, coverage)
        candidates.append(
            _functional_change_candidate(
                ticket_id=ticket_id,
                cell_text=cell_text,
                rn_filename=rn_filename,
                origin_release_id=origin_release_id,
                origin_release_name=origin_release_name,
                related_origin=related,
            )
        )
    for ticket_id, cell_text in plan.qa_qc:
        related = _related_origin_labels(ticket_id, cell_text, coverage)
        candidates.append(
            _fix_candidate(
                ticket_id=ticket_id,
                cell_text=cell_text,
                rn_filename=rn_filename,
                origin_release_id=origin_release_id,
                origin_release_name=origin_release_name,
                related_origin=related,
                kind="qa-qc",
            )
        )
    for ticket_id, cell_text in plan.nco_generate:
        related = _related_origin_labels(ticket_id, cell_text, coverage)
        candidates.append(
            _fix_candidate(
                ticket_id=ticket_id,
                cell_text=cell_text,
                rn_filename=rn_filename,
                origin_release_id=origin_release_id,
                origin_release_name=origin_release_name,
                related_origin=related,
                kind="nco",
            )
        )
    return candidates


def stamp_incremental_traceability(
    candidate: GeneratedCaseCandidate,
    *,
    origin_release_id: int | None,
    origin_release_name: str | None,
    baseline_cases: list[dict[str, Any]],
) -> GeneratedCaseCandidate:
    coverage = origin_coverage_by_key(baseline_cases)
    related = _related_origin_labels(
        candidate.related_jira or candidate.related_functionality or "",
        candidate.evidence or "",
        coverage,
    )
    candidate.origin_release_id = origin_release_id
    candidate.origin_release_name = origin_release_name
    candidate.related_origin_case_ids = related
    if not candidate.generation_origin:
        candidate.generation_origin = "incremental-new-functionality"
    note = "Generación incremental: funcionalidad nueva del RN; pipeline completo (Jira/Gherkin/motor). "
    if origin_release_name:
        note += f"Release origen declarado: {origin_release_name}. "
    candidate.justification = (note + (candidate.justification or ""))[:4000]
    rules = list(candidate.applied_rules or [])
    if "incremental-new-functionality" not in rules:
        rules.append("incremental-new-functionality")
    candidate.applied_rules = rules
    return candidate


def generate_revalidation_candidates(
    *,
    release_id: int,
    release_name: str,
    validation_type: str | None,
    rn_filename: str | None,
    pdf_bytes: bytes | None,
    origin_release_id: int | None,
    origin_release_name: str | None,
    origin_cases: list[dict[str, Any]],
    tickets: dict[str, list[tuple[str, str]]] | None = None,
    prior_functionality_cells: dict[str, str] | None = None,
    prior_qa_qc_cells: dict[str, str] | None = None,
    prior_nco_cells: dict[str, str] | None = None,
    new_functionality_candidates: list[GeneratedCaseCandidate] | None = None,
) -> GenerateCasesResponse:
    """Compose incremental candidates. New functionality must be supplied via the Apps engine."""
    from app.services.ai_case_engine import _tickets_by_section

    filename = rn_filename or ""
    buckets = tickets if tickets is not None else (_tickets_by_section(pdf_bytes) if pdf_bytes else {})
    plan = plan_incremental_generation(
        buckets,
        origin_cases,
        prior_functionality_cells,
        prior_qa_qc_cells=prior_qa_qc_cells,
        prior_nco_cells=prior_nco_cells,
    )
    candidates = list(new_functionality_candidates or [])
    candidates.extend(
        candidates_from_incremental_plan(
            plan,
            rn_filename=filename,
            origin_release_id=origin_release_id,
            origin_release_name=origin_release_name,
            baseline_cases=origin_cases,
        )
    )
    engine = "incremental-delta"
    if new_functionality_candidates:
        engine = "incremental-new+delta"
    message = (
        f"Generación incremental respecto del histórico del Entregable: "
        f"{len(candidates)} caso(s) nuevos o afectados. "
        f"No se copiaron los {len(origin_cases)} Test Case(s) previos. La IA propone; QC decide."
    )
    return GenerateCasesResponse(
        status="PROPOSED" if candidates else "EMPTY",
        message=message,
        release_id=release_id,
        release_name=release_name,
        validation_type=validation_type,
        has_analysis=True,
        engine=engine,
        candidates=candidates,
        persisted=False,
        analysis_details=plan.analysis_details,
    )
