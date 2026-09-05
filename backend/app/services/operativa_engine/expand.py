"""Expand behaviors into device-level candidates. No cartesian of users × MDP × HN."""

from __future__ import annotations

import re
from collections import defaultdict
from itertools import combinations

from app.schemas.case_generation import CandidateStep, GeneratedCaseCandidate
from app.services.operativa_engine.behaviors import Behavior
from app.services.operativa_engine.devices import (
    ECOSYSTEM_IPTV,
    ECOSYSTEM_OTT,
    DeviceTarget,
    iptv_matrix,
    is_pending_device,
    ott_matrix,
)


def _targets_for(behavior: Behavior, targets: list[DeviceTarget]) -> list[DeviceTarget]:
    pool = behavior.device_targets if behavior.device_targets is not None else targets
    concrete = [target for target in pool if not is_pending_device(target.label)]
    if behavior.ecosystem is None:
        return concrete or pool
    matching = [
        target
        for target in concrete
        if target.ecosystem is None or target.ecosystem == behavior.ecosystem
    ]
    if matching:
        return matching
    if behavior.ecosystem == ECOSYSTEM_OTT:
        return ott_matrix(reason="Comportamiento restringido a OTT; universo candidato QC.")
    if behavior.ecosystem == ECOSYSTEM_IPTV:
        return iptv_matrix(reason="Comportamiento restringido a IPTV; universo candidato QC.")
    return []


def expand_candidates(
    *,
    release_name: str,
    brf_key: str,
    epc_key: str | None,
    estado_jira: str | None,
    nota_rte: str | None,
    behaviors: list[Behavior],
    targets: list[DeviceTarget],
    extra_notes: list[str],
) -> list[GeneratedCaseCandidate]:
    rows: list[GeneratedCaseCandidate] = []
    for behavior in behaviors:
        applicable = _targets_for(behavior, targets)
        if not applicable:
            continue
        user_types: list[str | None] = ["Suscrito", "No suscrito"] if behavior.user_split else [None]
        mdp_values: list[str | None] = [None]
        if behavior.transactional:
            mdp_values = ["MDP aplicables (matriz del BRF)"]
        for target in applicable:
            for user in user_types:
                if behavior.transactional and user == "No suscrito":
                    continue
                for mdp in mdp_values:
                    priority, priority_reason = _priority_for(behavior)
                    pending_device = is_pending_device(target.label)
                    requires = behavior.requires_condition or pending_device or priority is None
                    applicability = target.applicability_reason or (
                        "Universo candidato recortado por comportamiento."
                    )
                    evidence_lines = [
                        f"BRF: {brf_key}",
                        f"EPC: {epc_key or '—'}",
                        f"Componente: {brf_key}",
                        f"Estado BRF (contexto, no filtro): {estado_jira or '—'}",
                        f"Comportamiento: {behavior.key}",
                        f"HN: {', '.join(behavior.hn_keys) or '—'}",
                        f"HN source: {behavior.hn_source}",
                        f"Group ID: {behavior.group_id or '—'}",
                        f"Canal / Punto de interacción: {', '.join(behavior.interaction_points) or '—'}",
                        f"Ecosistema: {target.ecosystem or '—'}",
                        f"Dispositivo: {target.label}",
                        f"Fuente dispositivo: {target.source or 'BRF'}",
                        f"Aplicabilidad: {applicability}",
                        f"Reglas: {', '.join(behavior.rules)}",
                    ]
                    if nota_rte:
                        evidence_lines.append(f"Nota RTE: {nota_rte[:400]}")
                    justification = (
                        f"Origen {behavior.origin}. {behavior.title}. "
                        + " ".join(extra_notes[:2])
                    )
                    if behavior.observations:
                        justification += f" {behavior.observations}"
                    if estado_jira:
                        justification += (
                            " El estado Jira se conserva como ejecutabilidad/contexto, no excluyó el análisis."
                        )
                    justification += f" {priority_reason}"
                    candidate_id = _candidate_id(
                        brf_key, epc_key, behavior, target, user, mdp
                    )
                    rows.append(
                        GeneratedCaseCandidate(
                            name=_name(behavior, target, user, mdp)[:250],
                            description=behavior.title,
                            precondition="; ".join(extra_notes) or None,
                            requires_condition=requires,
                            steps=_steps_for(behavior),
                            test_data=behavior.test_data,
                            related_functionality=brf_key,
                            related_jira=epc_key or brf_key,
                            related_rn=release_name,
                            evidence="\n".join(evidence_lines),
                            justification=justification[:4000],
                            possible_duplicate_of=None,
                            confidence="low" if pending_device or priority is None or behavior.hn_source == "HN_ABSENT" else (
                                "high" if behavior.origin == "directo" else "medium"
                            ),
                            review_required=True,
                            priority=priority,
                            priority_reason=priority_reason,
                            user_type=user,
                            component=brf_key,
                            applied_rules=behavior.rules,
                            generation_origin=behavior.origin,
                            ecosystem=target.ecosystem,
                            device=target.label,
                            device_source=target.source or None,
                            applicability_reason=applicability,
                            mdp=mdp,
                            behavior=behavior.key,
                            hn_keys=list(behavior.hn_keys),
                            candidate_id=candidate_id,
                            duplicate_status="UNIQUE",
                            duplicate_with=[],
                            group_id=behavior.group_id,
                            interaction_points=list(behavior.interaction_points),
                            hn_source=behavior.hn_source,
                        )
                    )
    return rows


def _steps_for(behavior: Behavior) -> list[CandidateStep]:
    steps = [
        CandidateStep(
            step_number=1,
            action=behavior.action,
            expected_result=behavior.expected,
        )
    ]
    for index, (action, expected) in enumerate(behavior.extra_steps, start=2):
        steps.append(CandidateStep(step_number=index, action=action, expected_result=expected))
    return steps


def _priority_for(behavior: Behavior) -> tuple[str | None, str]:
    if behavior.transactional or behavior.key.endswith(":mdp") or behavior.key.endswith(":offer-acquire"):
        return "BLOCKER", "Criterio: contratación/adquisición/pago (65.11)."
    if behavior.hn_source == "HN_ABSENT" or behavior.origin == "inferencia":
        return None, "Prioridad no asignada por defecto: HN ausente o origen inferencia; QC decide."
    if behavior.key.endswith(":negative"):
        return "CRITICAL", "Criterio: condición negativa explícita (no publicación / no habilitación)."
    return (
        "CRITICAL",
        "Criterio: disponibilidad, alta/baja, identidad, navegación o reproducción no transaccional.",
    )


def _name(behavior: Behavior, target: DeviceTarget, user: str | None, mdp: str | None) -> str:
    # Device lives in its own column; do not repeat it in the case name.
    parts = [behavior.title]
    if user:
        parts.append(user)
    if mdp:
        parts.append("MDP")
    return " · ".join(parts)


def _candidate_id(
    brf_key: str,
    epc_key: str | None,
    behavior: Behavior,
    target: DeviceTarget,
    user: str | None,
    mdp: str | None,
) -> str:
    hn = ",".join(behavior.hn_keys) or "-"
    return "|".join(
        [brf_key, epc_key or "-", behavior.key, hn, target.label, user or "-", mdp or "-"]
    )


def _norm(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def annotate_duplicates(candidates: list[GeneratedCaseCandidate]) -> list[GeneratedCaseCandidate]:
    """Flag duplicates/overlaps. Never deletes candidates."""
    groups: dict[tuple, list[int]] = defaultdict(list)
    for index, row in enumerate(candidates):
        groups[
            (
                row.related_functionality,
                row.behavior,
                _norm(row.device),
                _norm(row.user_type),
                _norm(row.mdp),
            )
        ].append(index)

    for indexes in groups.values():
        if len(indexes) < 2:
            continue
        for left, right in combinations(indexes, 2):
            a = candidates[left]
            b = candidates[right]
            same_origin = _norm(a.generation_origin) == _norm(b.generation_origin)
            same_hn = sorted(a.hn_keys) == sorted(b.hn_keys)
            same_condition = _norm(a.precondition) == _norm(b.precondition)
            same_action = _norm(a.steps[0].action if a.steps else "") == _norm(
                b.steps[0].action if b.steps else ""
            )
            same_expected = _norm(a.steps[0].expected_result if a.steps else "") == _norm(
                b.steps[0].expected_result if b.steps else ""
            )
            if same_origin and same_hn and same_condition and same_action and same_expected:
                status = "POSSIBLE_DUPLICATE"
            else:
                status = "OVERLAP"
            _link(a, b, status)
            _link(b, a, status)
    return candidates


def _link(row: GeneratedCaseCandidate, other: GeneratedCaseCandidate, status: str) -> None:
    other_id = other.candidate_id or other.name
    if other_id not in row.duplicate_with:
        row.duplicate_with.append(other_id)
    if row.duplicate_status == "UNIQUE":
        row.duplicate_status = status  # type: ignore[assignment]
    elif row.duplicate_status == "OVERLAP" and status == "POSSIBLE_DUPLICATE":
        row.duplicate_status = "POSSIBLE_DUPLICATE"
    row.possible_duplicate_of = row.possible_duplicate_of or other.name


def mark_duplicates(candidates: list[GeneratedCaseCandidate]) -> list[GeneratedCaseCandidate]:
    return annotate_duplicates(candidates)
