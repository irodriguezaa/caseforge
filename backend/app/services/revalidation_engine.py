"""Revalidación generation for Release Apps.

Uses the origin Release as validated baseline. Does not copy, delete, or mutate origin Test Cases.
Does not change Nuevo/Evolutivo generation (see ai_case_engine.generate_release_app_candidates).
"""

from __future__ import annotations

import re
from typing import Any

from app.schemas.case_generation import (
    CandidateStep,
    GeneratedCaseCandidate,
    GenerateCasesResponse,
)
from app.services.ai_case_engine import _tickets_by_section

_JIRA_KEY = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_OBSERVABLE = re.compile(
    r"\b(usuario|pantalla|muestra|oculta|error|reproduce|ingresa|selecciona|"
    r"modal|banner|login|pago|checkout|reproducci|observa|flujo|correg|fix|"
    r"validar|comportamiento)\b",
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
    """Jira key → origin test_case_id labels that mention it (evidence of already-validated coverage)."""
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


def nco_has_validation_evidence(ticket_id: str, cell_text: str) -> bool:
    remainder = _JIRA_KEY.sub(" ", cell_text or "")
    remainder = re.sub(r"\s+", " ", remainder).strip()
    if len(remainder) < 40:
        return False
    other_keys = extract_jira_keys(cell_text) - {ticket_id.upper()}
    if other_keys:
        return True
    return bool(_OBSERVABLE.search(remainder))


def _related_origin_labels(ticket_id: str, cell_text: str, coverage: dict[str, list[str]]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for key in extract_jira_keys(ticket_id, cell_text) | {ticket_id.upper()}:
        for label in coverage.get(key, []):
            if label and label not in seen:
                seen.add(label)
                labels.append(label)
    return labels


def _fix_candidate(
    *,
    ticket_id: str,
    cell_text: str,
    rn_filename: str,
    origin_release_id: int,
    origin_release_name: str,
    related_origin: list[str],
    kind: str,
) -> GeneratedCaseCandidate:
    summary = cell_text
    if ":" in cell_text:
        summary = cell_text.split(":", 1)[1].strip()
    summary = summary[:400] or ticket_id
    origin_note = (
        f"Release origen {origin_release_name} (id={origin_release_id}). "
        + (
            f"Casos origen relacionados: {', '.join(related_origin)}. "
            if related_origin
            else "Sin vínculo a un TC origen con evidencia de clave Jira. "
        )
    )
    name = f"Validar corrección {ticket_id}: {summary[:160]}"
    justification = (
        origin_note
        + f"Revalidación: el RN clasifica {ticket_id} como {kind}. "
        "No se copia la cobertura funcional ya validada del origen; se cubre el cambio/fix evidenciado."
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
        generation_origin=f"revalidation-{kind}",
        origin_release_id=origin_release_id,
        origin_release_name=origin_release_name,
        related_origin_case_ids=related_origin,
        applied_rules=["revalidation-delta"],
    )


def _functional_delta_candidate(
    *,
    ticket_id: str,
    cell_text: str,
    rn_filename: str,
    origin_release_id: int,
    origin_release_name: str,
) -> GeneratedCaseCandidate:
    summary = cell_text.split(":", 1)[1].strip() if ":" in cell_text else cell_text
    summary = summary[:400] or ticket_id
    return GeneratedCaseCandidate(
        name=(f"Validar cambio funcional {ticket_id}: {summary[:140]}")[:250],
        description=summary[:2000],
        steps=[
            CandidateStep(
                step_number=1,
                action="El usuario recorre el flujo de la funcionalidad nueva o cambiada descrita en el RN.",
                expected_result="Se observa el comportamiento de usuario final declarado, distinto de la cobertura ya validada en el origen.",
            )
        ],
        related_functionality=ticket_id,
        related_jira=ticket_id,
        related_rn=rn_filename,
        evidence=cell_text[:2000],
        justification=(
            f"Release origen {origin_release_name} (id={origin_release_id}). "
            f"La clave {ticket_id} no aparece en los Test Cases del origen; se trata como cambio funcional explícito. "
            "No se regeneró el resto de la cobertura ya validada."
        )[:4000],
        confidence="medium",
        review_required=True,
        basic_validation=False,
        priority="CRITICAL",
        generation_origin="revalidation-functional-delta",
        origin_release_id=origin_release_id,
        origin_release_name=origin_release_name,
        applied_rules=["revalidation-delta"],
    )


def generate_revalidation_candidates(
    *,
    release_id: int,
    release_name: str,
    validation_type: str | None,
    rn_filename: str | None,
    pdf_bytes: bytes | None,
    origin_release_id: int,
    origin_release_name: str,
    origin_cases: list[dict[str, Any]],
    tickets: dict[str, list[tuple[str, str]]] | None = None,
) -> GenerateCasesResponse:
    details: list[str] = []
    filename = rn_filename or ""
    buckets = tickets if tickets is not None else (_tickets_by_section(pdf_bytes) if pdf_bytes else {})
    coverage = origin_coverage_by_key(origin_cases)
    origin_keys = set(coverage)

    qa_qc = buckets.get("qa_qc") or []
    nco = buckets.get("nco") or []
    functionality = buckets.get("functionality") or []
    change_keys = {tid.upper() for tid, _ in qa_qc} | {tid.upper() for tid, _ in nco}

    candidates: list[GeneratedCaseCandidate] = []

    for ticket_id, cell_text in functionality:
        key = ticket_id.upper()
        if key in origin_keys and key not in change_keys:
            related = coverage.get(key) or []
            details.append(
                f"No se regeneró {ticket_id}: ya hay cobertura validada en el Release origen"
                + (f" ({', '.join(related[:5])})" if related else "")
                + "."
            )
            continue
        if key in origin_keys and key in change_keys:
            details.append(
                f"{ticket_id} permanece en Funcionalidades pero el RN también reporta un cambio/fix; "
                "no se duplica la cobertura original, solo el delta."
            )
            continue
        candidates.append(
            _functional_delta_candidate(
                ticket_id=ticket_id,
                cell_text=cell_text,
                rn_filename=filename,
                origin_release_id=origin_release_id,
                origin_release_name=origin_release_name,
            )
        )

    for ticket_id, cell_text in qa_qc:
        related = _related_origin_labels(ticket_id, cell_text, coverage)
        candidates.append(
            _fix_candidate(
                ticket_id=ticket_id,
                cell_text=cell_text,
                rn_filename=filename,
                origin_release_id=origin_release_id,
                origin_release_name=origin_release_name,
                related_origin=related,
                kind="qa-qc",
            )
        )

    for ticket_id, cell_text in nco:
        related = _related_origin_labels(ticket_id, cell_text, coverage)
        if nco_has_validation_evidence(ticket_id, cell_text):
            candidates.append(
                _fix_candidate(
                    ticket_id=ticket_id,
                    cell_text=cell_text,
                    rn_filename=filename,
                    origin_release_id=origin_release_id,
                    origin_release_name=origin_release_name,
                    related_origin=related,
                    kind="nco",
                )
            )
        else:
            details.append(
                f"NCO {ticket_id} sin evidencia suficiente de comportamiento observable; "
                "marcado para revisión de QC. No se inventó un Test Case."
            )

    message = (
        f"Revalidación respecto de {origin_release_name}: se propusieron {len(candidates)} caso(s) de delta "
        f"(fixes/cambios). No se copiaron los {len(origin_cases)} Test Case(s) del origen. La IA propone; QC decide."
    )
    return GenerateCasesResponse(
        status="PROPOSED" if candidates else "EMPTY",
        message=message,
        release_id=release_id,
        release_name=release_name,
        validation_type=validation_type,
        has_analysis=True,
        engine="revalidation-delta",
        candidates=candidates,
        persisted=False,
        analysis_details=details,
    )
