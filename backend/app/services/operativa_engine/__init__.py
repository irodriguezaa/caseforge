"""CaseForge Operativas engine V4.

RN → BRF/EPC candidatos → QC scope gate → HN/CA → comportamientos →
casos de uso → dimensiones de ejecución → Test Case ejecutable.
No usa Apps A–G.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.epc import Epc
from app.schemas.case_generation import GeneratedCaseCandidate
from app.services.operativa_engine.behaviors import Behavior, behaviors_for_brf
from app.services.operativa_engine.devices import (
    DeviceTarget,
    candidate_universe,
    extract_devices_from_text,
    infer_ecosystems,
    is_pending_device,
    parse_declared_devices,
    resolve_targets,
)
from app.services.operativa_engine.expand import annotate_duplicates, expand_candidates
from app.services.operativa_engine.hn import parse_historias, text_without_historias
from app.services.operativa_engine.coverage_matrix import build_coverage_matrix
from app.services.operativa_engine.matrix_official import materialize_official_candidates
from app.services.operativa_engine.tri import extract_tris

ENGINE_VERSION = "operativa-v4.1"


@dataclass
class OperativaGenerationResult:
    candidates: list[GeneratedCaseCandidate]
    skipped: list[str]
    brfs_analyzed: int = 0
    device_review_brfs: list[str] | None = None
    duplicate_groups: int = 0


def generate_operativa_from_matrix(
    *,
    release_id: int,
    release_name: str,
    epcs: list[Epc],
    pdf_bytes: bytes | None = None,
    context_loader=None,
) -> OperativaGenerationResult:
    """Live Operativas lote: matrix → use cases → device expander → TCs.

    Does not special-case diagnostic BRF keys. QC_REVIEW and OUT_OF_SCOPE
    produce 0 automatic TCs. TRI in the RN is noted for QC, not invented.
    """
    matrix = build_coverage_matrix(
        release_id=release_id,
        release_name=release_name,
        epcs=epcs,
        context_loader=context_loader,
    )
    candidates, warnings = materialize_official_candidates(matrix)
    skipped = list(matrix.notes) + list(warnings)
    for tri in extract_tris(pdf_bytes):
        skipped.append(
            f"{tri.key}: TRI en RN; sin HN/CA no se generan TCs automáticos (QC decide)."
        )
    device_review = sorted(
        {
            row.brf_key
            for row in matrix.rows
            if row.origin == "QC_REVIEW" or row.scope_status == "OUT_OF_SCOPE"
        }
    )
    duplicate_groups = len(
        {
            candidate.group_id or candidate.name
            for candidate in candidates
            if candidate.duplicate_status and candidate.duplicate_status != "UNIQUE"
        }
    )
    return OperativaGenerationResult(
        candidates=candidates,
        skipped=skipped,
        brfs_analyzed=matrix.brfs_analyzed,
        device_review_brfs=device_review,
        duplicate_groups=duplicate_groups,
    )


def generate_operativa_candidates(
    *,
    release_name: str,
    epcs: list[Epc],
    pdf_bytes: bytes | None = None,
    jira_loader=None,
) -> OperativaGenerationResult:
    """QC-selected EPCs only. Status is context. TRI is a separate source from the RN PDF."""
    loader = jira_loader if jira_loader is not None else fetch_brf_context
    candidates: list[GeneratedCaseCandidate] = []
    skipped: list[str] = []
    analyzed: set[str] = set()
    device_review: set[str] = set()
    for epc in epcs:
        analyzed.add(epc.brf_key)
        jira_blob = ""
        try:
            loaded = loader(epc.brf_key) if loader else ""
            jira_blob = loaded if isinstance(loaded, str) else str(loaded or "")
        except Exception:
            jira_blob = ""
        behaviors, notes = behaviors_for_brf(
            brf_key=epc.brf_key,
            title=epc.titulo,
            nota_rte=epc.nota_rte,
            jira_blob=jira_blob,
            alcance_funcional=epc.alcance_funcional,
        )
        skipped.extend(f"{epc.brf_key}: {note}" for note in notes)
        if not behaviors:
            continue
        evidence = "\n".join(
            part
            for part in (epc.titulo, epc.alcance, epc.alcance_funcional, epc.nota_rte, jira_blob)
            if part
        )
        device_notes = _attach_devices(behaviors, epc, evidence)
        skipped.extend(f"{epc.brf_key}: {note}" for note in device_notes)
        if any(
            not behavior.device_targets
            or any(is_pending_device(target.label) for target in behavior.device_targets)
            for behavior in behaviors
        ):
            device_review.add(epc.brf_key)
        fallback = behaviors[0].device_targets or []
        candidates.extend(
            expand_candidates(
                release_name=release_name,
                brf_key=epc.brf_key,
                epc_key=epc.epc_key,
                estado_jira=epc.estado_jira,
                nota_rte=epc.nota_rte,
                behaviors=behaviors,
                targets=fallback,
                extra_notes=device_notes + notes,
            )
        )

    for tri in extract_tris(pdf_bytes):
        analyzed.add(tri.key)
        targets = tri.devices or []
        if not targets:
            ott, iptv = infer_ecosystems(tri.summary)
            targets = candidate_universe(
                ott, iptv, reason=f"{tri.key}: ecosistema en RN; universo candidato QC"
            )
        if not targets:
            skipped.append(f"{tri.key}: TRI sin plataformas ni ecosistema explícitos; QC debe indicar dispositivos.")
            device_review.add(tri.key)
            continue
        behavior = Behavior(
            key=f"{tri.key}:fix",
            title=f"Regresión funcional {tri.key}",
            ecosystem=None,
            origin="directo",
            rules=["65.20", "65.21"],
            action="El usuario reproduce el escenario del incidente productivo.",
            expected="El comportamiento defectuoso queda corregido en las plataformas impactadas.",
            observations=tri.summary[:400],
            device_targets=targets,
        )
        candidates.extend(
            expand_candidates(
                release_name=release_name,
                brf_key=tri.key,
                epc_key=tri.key,
                estado_jira="TRI/QCO",
                nota_rte=None,
                behaviors=[behavior],
                targets=targets,
                extra_notes=["65.20: 1 TRI funcional = 1 comportamiento; 1 TC por dispositivo impactado."],
            )
        )
    annotated = annotate_duplicates(candidates)
    duplicate_groups = len(
        {
            (row.related_functionality, row.behavior, row.device)
            for row in annotated
            if row.duplicate_status and row.duplicate_status != "UNIQUE"
        }
    )
    return OperativaGenerationResult(
        candidates=annotated,
        skipped=skipped,
        brfs_analyzed=len(analyzed),
        device_review_brfs=sorted(device_review),
        duplicate_groups=duplicate_groups,
    )


def _attach_devices(behaviors: list[Behavior], epc: Epc, evidence: str) -> list[str]:
    notes: list[str] = []
    hns = parse_historias(evidence)
    brf_level = extract_devices_from_text(
        "\n".join(
            part
            for part in (epc.titulo, epc.alcance, epc.alcance_funcional, epc.nota_rte, text_without_historias(evidence))
            if part
        ),
        source=f"{epc.brf_key} contenido",
    )
    qc_targets = parse_declared_devices(epc.dispositivos_aplicables)
    fallback, pending_notes = _brf_fallback(epc, evidence, brf_level, qc_targets)
    notes.extend(pending_notes)
    any_hn_devices = any(item.devices for item in hns)
    by_key = {item.key: item for item in hns}
    for behavior in behaviors:
        hn_targets = _unique_targets(
            target
            for key in behavior.hn_keys
            for target in (by_key[key].devices if key in by_key else [])
        )
        if hn_targets:
            behavior.device_targets = hn_targets
            continue
        if behavior.hn_keys and any_hn_devices:
            behavior.device_targets = fallback
            notes.append(
                f"{behavior.key}: HN sin dispositivos propios; se usa el universo del BRF recortable por comportamiento."
            )
            continue
        behavior.device_targets = fallback
    return notes


def _brf_fallback(
    epc: Epc,
    evidence: str,
    brf_level: list[DeviceTarget],
    qc_targets: list[DeviceTarget],
) -> tuple[list[DeviceTarget], list[str]]:
    if brf_level:
        return brf_level, []
    if qc_targets:
        return qc_targets, [
            "Dispositivos tomados de la selección QC (el contenido del BRF no nombró plataformas)."
        ]
    return resolve_targets(None, evidence, source=epc.brf_key)


def _unique_targets(targets) -> list[DeviceTarget]:
    found: list[DeviceTarget] = []
    seen: set[str] = set()
    for target in targets:
        if target.label in seen:
            continue
        seen.add(target.label)
        found.append(target)
    return found
