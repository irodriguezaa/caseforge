"""Build intermediate coverage matrix before device expansion and TC generation."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from app.models.epc import Epc
from app.schemas.coverage_matrix import CoverageMatrixResponse, CoverageMatrixRow, HnCoverageRecord
from app.services.operativa_engine.devices import (
    ECOSYSTEM_IPTV,
    ECOSYSTEM_OTT,
    QC_OTT_EXECUTION_MATRIX,
    extract_devices_from_text,
    infer_ecosystems,
    iptv_matrix,
    ott_matrix,
    parse_declared_devices,
)
from app.services.operativa_engine.families import FAMILY_INFRA, FAMILY_REPORTS, classify_family
from app.services.operativa_engine.hn import HistoriaNegocio, hn_title, parse_historias
from app.services.operativa_engine.hn_roles import (
    DEPENDENCY_CONFIGURATION,
    OOS_QC,
    PRIMARY,
    SCENARIO,
    SUPPORTING,
    TEST_DATA,
    HnDisposition,
    classify_historias,
    extract_supporting_facts,
)
from app.services.operativa_engine.jira_context import BrfContextBundle, fetch_brf_context_bundle

ENGINE_VERSION = "operativa-v4.3"

CHANNEL_EMAIL = "Email"

_TV_DEVICES: tuple[str, ...] = ("tvOS", "ADT", "Roku", "Fire TV")

# Ordered longest-first so "landing comercial" wins over incidental fragments.
_INTERACTION_POINT_PATTERNS: tuple[tuple[str, str], ...] = (
    ("carrusel de canales premium", "Carrusel Premium"),
    ("carrusel locales", "Carrusel Locales"),
    ("carrusel premium", "Carrusel Premium"),
    ("landing comercial", "Landing Comercial"),
    ("plan selector", "Plan Selector"),
    ("home del add on", "Home del add-on"),
    ("home del add-on", "Home del add-on"),
    ("mi cuenta", "Mi cuenta/Suscripción"),
    ("brand header", "Brand header"),
    ("correo de bienvenida", "Correo de bienvenida"),
    ("epg full", "EPG Full"),
    ("epg mini", "EPG Mini"),
    ("player live", "Player Live"),
    ("panel de opciones", "Panel de opciones"),
    ("superdestacado", "Superdestacado"),
    ("vcard", "vCard"),
    ("checkout", "Checkout"),
    ("ticket", "Ticket"),
    ("mosaico", "Mosaico"),
    ("buscador", "Buscador"),
    ("búsqueda", "Buscador"),
    ("chapita", "Chapita en contenido"),
)

_SPLIT_PAIRS: tuple[tuple[str, str, str], ...] = (
    ("timeshift", "npvr", "65.8"),
    ("timeshift", "tv everywhere", "65.8"),
    ("npvr", "tv everywhere", "65.8"),
)


@dataclass
class BehaviorDraft:
    behavior_key: str
    behavior_title: str
    hn_keys: list[str]
    interaction_points: list[str] = field(default_factory=list)
    channel: str | None = None
    transactional: bool = False
    rules: list[str] = field(default_factory=list)
    origin: str = "directo"
    evidence_excerpt: str = ""
    qc_review: bool = False
    qc_review_reason: str = ""


@dataclass
class _BrfGroup:
    brf_key: str
    epcs: list[Epc]
    title: str
    alcance_funcional: str | None
    nota_rte: str | None
    dispositivos: list[str]
    ecosystem: str | None


def build_coverage_matrix(
    *,
    release_id: int,
    release_name: str,
    epcs: list[Epc],
    context_loader=None,
) -> CoverageMatrixResponse:
    """One functional matrix row set per BRF. EPCs are traceability only — no duplication."""
    loader = context_loader or fetch_brf_context_bundle
    groups = _group_epcs_by_brf(epcs)
    rows: list[CoverageMatrixRow] = []
    notes: list[str] = []
    hn_source_by_brf: dict[str, str] = {}
    hn_coverage: list[HnCoverageRecord] = []

    for group in groups.values():
        bundle = _load_context(group.brf_key, loader)
        hn_source_by_brf[group.brf_key] = bundle.hn_source
        if bundle.hn_source == "HN_ABSENT":
            notes.append(f"{group.brf_key}: HN/CA no disponible; matriz vacía o inferida.")
        if bundle.confluence_page_id:
            notes.append(
                f"{group.brf_key}: HN desde Confluence pageId={bundle.confluence_page_id}."
            )
        epc_keys = sorted({epc.epc_key for epc in group.epcs if epc.epc_key})
        if len(epc_keys) > 1:
            notes.append(
                f"{group.brf_key}: {len(epc_keys)} EPC con mismo alcance funcional; "
                "matriz consolidada sin duplicar comportamientos."
            )

        brf_rows, brf_notes, brf_coverage = _matrix_for_brf(group, bundle, epc_keys)
        rows.extend(brf_rows)
        notes.extend(brf_notes)
        hn_coverage.extend(brf_coverage)

    annotated = _annotate_matrix_duplicates(rows)
    return CoverageMatrixResponse(
        status="MATRIX",
        engine=ENGINE_VERSION,
        release_id=release_id,
        release_name=release_name,
        brfs_analyzed=len(groups),
        row_count=len(annotated),
        rows=annotated,
        notes=notes,
        hn_source_by_brf=hn_source_by_brf,
        hn_coverage=hn_coverage,
    )


def _load_context(brf_key: str, loader) -> BrfContextBundle:
    loaded = loader(brf_key)
    if isinstance(loaded, BrfContextBundle):
        return loaded
    blob = loaded if isinstance(loaded, str) else str(loaded or "")
    return BrfContextBundle(brf_key=brf_key, jira_blob=blob)


def _group_epcs_by_brf(epcs: list[Epc]) -> dict[str, _BrfGroup]:
    grouped: dict[str, _BrfGroup] = {}
    for epc in epcs:
        if epc.brf_key not in grouped:
            devices: list[str] = []
            if epc.dispositivos_aplicables:
                devices = [
                    target.label
                    for target in parse_declared_devices(epc.dispositivos_aplicables)
                ]
            grouped[epc.brf_key] = _BrfGroup(
                brf_key=epc.brf_key,
                epcs=[epc],
                title=epc.titulo,
                alcance_funcional=epc.alcance_funcional,
                nota_rte=epc.nota_rte,
                dispositivos=devices,
                ecosystem=_infer_ecosystem(epc),
            )
        else:
            grouped[epc.brf_key].epcs.append(epc)
            if epc.dispositivos_aplicables and not grouped[epc.brf_key].dispositivos:
                grouped[epc.brf_key].dispositivos = [
                    target.label
                    for target in parse_declared_devices(epc.dispositivos_aplicables)
                ]
    return grouped


def _infer_ecosystem(epc: Epc) -> str | None:
    blob = " ".join(
        part for part in (epc.titulo, epc.alcance, epc.alcance_funcional) if part
    )
    ott, iptv = infer_ecosystems(blob)
    declared = parse_declared_devices(epc.dispositivos_aplicables)
    device_ott = any(item.ecosystem == ECOSYSTEM_OTT for item in declared)
    device_iptv = any(item.ecosystem == ECOSYSTEM_IPTV for item in declared)
    # "OTT e IPTV" (or ADR+ADT+STB) is dual: Android=ADR, Android TV STV=ADT, STB=IPTV.
    if (ott and iptv) or (device_ott and device_iptv):
        return None
    if ott or (device_ott and not device_iptv):
        return ECOSYSTEM_OTT
    if iptv or device_iptv:
        return ECOSYSTEM_IPTV
    return None


def _matrix_for_brf(
    group: _BrfGroup,
    bundle: BrfContextBundle,
    epc_keys: list[str],
) -> tuple[list[CoverageMatrixRow], list[str], list[HnCoverageRecord]]:
    notes: list[str] = []
    evidence_blob = bundle.combined_blob
    extra = "\n".join(
        part
        for part in (
            group.title,
            group.alcance_funcional,
            group.nota_rte,
        )
        if part
    )
    full_evidence = "\n".join(part for part in (extra, evidence_blob) if part)

    family_blob = "\n".join(part for part in (group.title, group.alcance_funcional, group.nota_rte) if part)
    family = classify_family(group.title, family_blob)
    if family == FAMILY_REPORTS:
        notes.append(f"{group.brf_key}: 65.16 reportes/métricas — sin filas de matriz QC.")
        row = _diagnostic_row(
            group,
            bundle,
            epc_keys,
            title="Fuera de alcance QC: reportes/métricas",
            reason="Familia reportes: no entra a matriz funcional de Operativas.",
        )
        return [row], notes, []
    if family == FAMILY_INFRA:
        notes.append(f"{group.brf_key}: infra/whitelist/VPN — fuera de alcance funcional QC.")
        row = _diagnostic_row(
            group,
            bundle,
            epc_keys,
            title="Fuera de alcance QC: dependencia técnica/infra",
            reason=(
                "La evidencia del BRF es de infraestructura/configuración (p. ej. whitelist, VPN, IPs). "
                "No se derivan comportamientos funcionales user-facing."
            ),
        )
        return [row], notes, []

    historias = parse_historias(full_evidence)
    classified = classify_historias(historias)
    if not historias:
        notes.append(f"{group.brf_key}: sin HN funcionales parseables.")
        row = _diagnostic_row(
            group,
            bundle,
            epc_keys,
            title="Sin HN/CA funcionales parseables",
            reason=(
                "No hay historias de negocio funcionales en Jira/Confluence, o el alcance es de "
                "configuración/infra. QC confirma si existe cobertura o si el BRF queda fuera."
            ),
        )
        coverage = _hn_coverage_from_classification(group.brf_key, classified, [row])
        notes.extend(_hn_coverage_notes(coverage))
        return [row], notes, coverage

    brf_devices = _brf_device_labels(group, full_evidence)
    by_key = {item.key: item for item in historias}
    test_data_hns = [
        by_key[key]
        for key, item in classified.items()
        if item.disposition == TEST_DATA and key in by_key
    ]
    rows: list[CoverageMatrixRow] = []

    for key, role in classified.items():
        if role.disposition != PRIMARY:
            continue
        hn = by_key[key]
        attached = [
            by_key[other]
            for other, other_role in classified.items()
            if other_role.related_to == key and other in by_key and other_role.disposition != TEST_DATA
        ]
        drafts = behaviors_from_hn(group.brf_key, hn)
        merged_parts = [hn, *attached, *test_data_hns]
        merged_blob = "\n".join(part.text for part in merged_parts if part)
        extra_keys = [item.key for item in attached] + [item.key for item in test_data_hns]
        for draft in drafts:
            draft.hn_keys = _unique([hn.key, *extra_keys])
            draft.evidence_excerpt = merged_blob[:8000]
            channel = draft.channel or _detect_channel(hn, draft.interaction_points)
            interaction_points = draft.interaction_points or _extract_interaction_points(merged_blob)
            ecosystem = _behavior_ecosystem(hn, group, channel)
            devices = _applicable_devices(
                hn=hn,
                interaction_points=interaction_points,
                channel=channel,
                brf_devices=brf_devices,
                ecosystem=ecosystem,
            )
            if draft.qc_review and _is_dependency_title(draft.behavior_title):
                devices = []
            users, user_reason = _relevant_users(hn, draft.transactional, channel)
            if not users:
                for extra in attached:
                    users, user_reason = _relevant_users(extra, draft.transactional, channel)
                    if users:
                        break
            mdp = _mdp_for_behavior(hn, draft.transactional, interaction_points)
            test_data = _test_data_lines(
                group.brf_key,
                hn,
                interaction_points,
                channel,
                extra_blob=merged_blob,
                extra_hn_keys=draft.hn_keys,
            )
            applicability = _applicability_reason(
                channel=channel,
                devices=devices,
                interaction_points=interaction_points,
                user_reason=user_reason,
                brf_devices=brf_devices,
            )
            scope_status = (
                "OUT_OF_SCOPE"
                if draft.qc_review and _is_dependency_title(draft.behavior_title)
                else "IN_SCOPE"
            )
            if "mantener" in hn_title(hn.text).lower() and not attached:
                draft.origin = "QC_REVIEW"
                draft.qc_review = True
            rows.append(
                CoverageMatrixRow(
                    brf_key=group.brf_key,
                    epc_keys=epc_keys,
                    hn_keys=draft.hn_keys,
                    behavior_key=draft.behavior_key,
                    behavior_title=draft.behavior_title,
                    interaction_points=interaction_points,
                    channel=channel,
                    ecosystem=ecosystem,
                    applicable_devices=devices,
                    relevant_users=users,
                    transactional=draft.transactional,
                    mdp=mdp,
                    test_data=test_data,
                    origin=_origin_for(draft),
                    source="Confluence" if bundle.hn_source == "CONFLUENCE" else "Jira",
                    hn_source=bundle.hn_source,
                    scope_status=scope_status,
                    behavior_reason=_behavior_reason(hn, draft, interaction_points),
                    reasoning=_reasoning_text(
                        hn=hn,
                        draft=draft,
                        interaction_points=interaction_points,
                        channel=channel,
                        devices=devices,
                        users=users,
                        mdp=mdp,
                        epc_keys=epc_keys,
                    ),
                    evidence=_row_evidence(group.brf_key, hn, draft, bundle),
                    applicability_reason=applicability,
                    rules=draft.rules or ["65.4"],
                )
            )

    if not rows:
        notes.append(f"{group.brf_key}: sin comportamientos PRIMARY; HN clasificadas sin TC automático.")
        row = _diagnostic_row(
            group,
            bundle,
            epc_keys,
            title="Sin comportamiento PRIMARY ejecutable",
            reason="Las HN se clasificaron (OOS/TEST_DATA/DEPENDENCY) y no quedó un comportamiento primario.",
        )
        coverage = _hn_coverage_from_classification(group.brf_key, classified, [row])
        notes.extend(_hn_coverage_notes(coverage))
        return [row], notes, coverage

    clustered = _consolidate_functional_clusters(_consolidate_same_behavior(rows))
    flagged = _flag_release_polarity(clustered)
    coverage = _hn_coverage_from_classification(group.brf_key, classified, flagged)
    notes.extend(_hn_coverage_notes(coverage))
    return flagged, notes, coverage


def behaviors_from_hn(brf_key: str, hn: HistoriaNegocio) -> list[BehaviorDraft]:
    """HN → one or more functional behaviors when the content differentiates them."""
    splits = _functional_splits(hn)
    if not splits:
        return [_behavior_draft(brf_key, hn, aspect=None)]
    return [_behavior_draft(brf_key, hn, aspect=aspect) for aspect in splits]


def _functional_splits(hn: HistoriaNegocio) -> list[tuple[str, str]]:
    """Split only when one HN independently requires two capabilities.

    Do not split: specialized titles (solo NPVR / solo Timeshift), nor 'mantener' impact lists.
    """
    title = hn_title(hn.text).lower()
    if "mantener" in title:
        return []
    specialized = [token for token in ("timeshift", "npvr", "tv everywhere") if token in title]
    if len(specialized) == 1:
        return []
    lowered = hn.text.lower()
    labels: list[tuple[str, str]] = []
    for left, right, _rule in _SPLIT_PAIRS:
        if left in lowered and right in lowered:
            if left not in {item[0] for item in labels}:
                labels.append((left, left.upper()))
            if right not in {item[0] for item in labels}:
                labels.append((right, right.upper()))
    if len(labels) >= 2:
        return labels
    return []


def _behavior_draft(
    brf_key: str,
    hn: HistoriaNegocio,
    aspect: tuple[str, str] | None,
) -> BehaviorDraft:
    base_title = hn_title(hn.text) or hn.key
    interaction_points = _extract_interaction_points(hn.text)
    channel = _detect_channel(hn, interaction_points)
    transactional = hn.is_transactional or _is_transactional_text(hn_title(hn.text))
    qc_review, qc_reason = _qc_review_for(hn, base_title)
    if aspect:
        slug, label = aspect
        title = f"{base_title} — {label}"
        behavior_key = f"{brf_key}:{hn.key}:{slug}"
        rules = ["65.4", "65.8"]
    else:
        title = base_title
        behavior_key = f"{brf_key}:{hn.key}:{_slug(title)}"
        rules = ["65.4", "65.9"] if transactional else ["65.4"]
    if channel == CHANNEL_EMAIL:
        interaction_points = interaction_points or ["Correo de bienvenida"]
    return BehaviorDraft(
        behavior_key=behavior_key,
        behavior_title=title[:250],
        hn_keys=[hn.key],
        interaction_points=interaction_points,
        channel=channel,
        transactional=transactional,
        rules=rules,
        origin="QC_REVIEW" if qc_review else "directo",
        evidence_excerpt=hn.text[:8000],
        qc_review=qc_review,
        qc_review_reason=qc_reason,
    )


def _qc_review_for(hn: HistoriaNegocio, title: str) -> tuple[bool, str]:
    lowered = (title or "").lower()
    if not title:
        return True, "Título de HN vacío o ilegible; QC debe confirmar el comportamiento."
    if "mantener" in lowered:
        return True, (
            "HN de impacto/mantener: no se materializa un comportamiento por cada "
            "capacidad citada (TS/NPVR/TVE). QC confirma si hay cobertura de no-regresión."
        )
    return False, ""


def _behavior_ecosystem(hn: HistoriaNegocio, group: _BrfGroup, channel: str | None) -> str | None:
    if channel == CHANNEL_EMAIL:
        return None
    title = hn_title(hn.text).lower()
    text = hn.text.lower()
    title_ott = bool(re.search(r"\bott\b", title))
    title_iptv = bool(re.search(r"\biptv\b", title))
    blob = f"{title} {text}"
    # "OTT e IPTV" in the BRF header copied into the HN is dual, not IPTV-only.
    if (title_ott and title_iptv) or re.search(r"\bott\s+[ey]\s+iptv\b", blob):
        return None
    if _hn_android_family(hn) and group.ecosystem is None:
        return None
    if "paquetes iptv" in text or (title_iptv and not title_ott):
        return ECOSYSTEM_IPTV
    if any(token in title for token in ("timeshift", "npvr")) and "ott" not in title:
        return ECOSYSTEM_IPTV
    if "tv everywhere" in title:
        return group.ecosystem
    if "paquetes de ott" in text or "paquetes ott" in text or (title_ott and not title_iptv):
        return ECOSYSTEM_OTT
    return group.ecosystem


def _is_dependency_title(title: str) -> bool:
    lowered = (title or "").lower()
    return any(
        token in lowered
        for token in (
            "insumos de diseño",
            "insumos de diseno",
            "compartir insumos",
            "valores de configuración",
            "valores de configuracion",
            "resource id",
            "obtener las plantillas",
            "plantillas de comunicación",
            "plantillas de comunicacion",
        )
    )


def _origin_for(draft: BehaviorDraft) -> str:
    if draft.qc_review:
        return "QC_REVIEW"
    return draft.origin


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower())
    return cleaned.strip("-")[:60] or "functional"


def _extract_interaction_points(text: str) -> list[str]:
    """Named interaction points. Incidental mentions are not coverage dimensions."""
    blob = (text or "").lower()
    blob = re.sub(r"posici[oó]n\s+\d+\s+de\s+la\s+landing comercial", " ", blob)
    blob = re.sub(r"proceso de suscripci[oó]n", " ", blob)
    found: list[str] = []
    for needle, label in _INTERACTION_POINT_PATTERNS:
        if needle in blob and label not in found:
            found.append(label)
    title = hn_title(text).lower()
    if "ticket" in title and "checkout" not in title:
        found = [item for item in found if item != "Checkout"]
    if "checkout" in title and "ticket" not in title:
        found = [item for item in found if item != "Ticket"]
    if "checkout" in title or "ticket" in title:
        found = [item for item in found if item != "Landing Comercial"]
    if "locales" in title:
        found = [item for item in found if item != "Carrusel Premium"]
    return found


def _detect_channel(hn: HistoriaNegocio, interaction_points: list[str]) -> str | None:
    lowered = hn.text.lower()
    title = hn_title(hn.text).lower()
    email_tokens = (
        "correo de bienvenida",
        "correo electrónico",
        "correo electronico",
        "correo de confirmación",
        "correo de confirmacion",
        "logo en el correo",
        "logotipo en el correo",
        "en el correo de",
    )
    if any(token in title or token in lowered for token in email_tokens):
        return CHANNEL_EMAIL
    if re.search(r"\b(?:e-?mail)\b", f"{title} {lowered}"):
        return CHANNEL_EMAIL
    if "Correo de bienvenida" in interaction_points:
        return CHANNEL_EMAIL
    return None


def _is_transactional_text(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        token in lowered
        for token in (
            "flujo transaccional",
            "flujo de contratación",
            "contratación norte-sur",
            "iniciar el flujo de contrat",
            "medio de pago",
            "medios de pago",
        )
    )


def _brf_device_labels(group: _BrfGroup, evidence: str) -> list[str]:
    if group.dispositivos:
        labels = list(group.dispositivos)
    else:
        extracted = extract_devices_from_text(evidence, source=group.brf_key)
        if extracted:
            labels = [target.label for target in extracted]
        elif group.ecosystem == ECOSYSTEM_IPTV:
            labels = [target.label for target in iptv_matrix()]
        elif group.ecosystem == ECOSYSTEM_OTT:
            labels = list(QC_OTT_EXECUTION_MATRIX)
        else:
            labels = list(QC_OTT_EXECUTION_MATRIX) + [target.label for target in iptv_matrix()]
    return _ensure_android_family_on_dual_brf(group, labels)


def _ensure_android_family_on_dual_brf(group: _BrfGroup, labels: list[str]) -> list[str]:
    """OTT e IPTV + Android: ADR, ADT and STB when the Release named that set."""
    title = group.title or ""
    ott, iptv = infer_ecosystems(title)
    if not (ott and iptv):
        return labels
    found = list(labels)
    if re.search(r"\bandroid\b", title, re.I):
        for extra in ("ADR", "ADT", "STB"):
            if extra not in found:
                found.append(extra)
    return found


def _hn_android_family(hn: HistoriaNegocio) -> bool:
    """HN talks about dispositivos Android; on a dual BRF that is ADR+ADT+STB, not STB-only."""
    title = hn_title(hn.text)
    return bool(re.search(r"dispositivos?\s+android\b", title, re.I))


def _declared_execution_devices(brf_devices: list[str]) -> list[str]:
    named = [label for label in brf_devices if label in {"ADR", "ADT", "STB"}]
    return named or list(brf_devices)


def _applicable_devices(
    *,
    hn: HistoriaNegocio,
    interaction_points: list[str],
    channel: str | None,
    brf_devices: list[str],
    ecosystem: str | None,
) -> list[str]:
    if channel == CHANNEL_EMAIL:
        return []
    lowered = hn.text.lower()
    if "aplica para dispositivos con experiencia de tele" in lowered:
        return list(_TV_DEVICES)
    if _hn_android_family(hn):
        return _declared_execution_devices(brf_devices)
    explicit = _explicit_hn_devices(hn)
    if explicit:
        return explicit
    points = set(interaction_points)
    if points and points <= {"Checkout", "Ticket"}:
        return _checkout_ticket_devices(brf_devices, ecosystem)
    if ecosystem == ECOSYSTEM_IPTV:
        return [target.label for target in iptv_matrix()]
    if ecosystem == ECOSYSTEM_OTT:
        ott = [label for label in brf_devices if label not in {"STB"}]
        return ott or list(QC_OTT_EXECUTION_MATRIX)
    return list(brf_devices)


def _checkout_ticket_devices(brf_devices: list[str], ecosystem: str | None) -> list[str]:
    """Checkout/Ticket is TV-only on a full OTT catalog, not when the BRF named ADR+ADT+STB."""
    named = list(brf_devices)
    if "STB" in named:
        return named
    if ecosystem is None:
        return named or (list(QC_OTT_EXECUTION_MATRIX) + [target.label for target in iptv_matrix()])
    if ecosystem == ECOSYSTEM_IPTV:
        return [target.label for target in iptv_matrix()]
    tv = [label for label in named if label in _TV_DEVICES]
    return tv or list(_TV_DEVICES)


def _explicit_hn_devices(hn: HistoriaNegocio) -> list[str]:
    """Only devices from an explicit Dispositivos: list — not incidental brand mentions."""
    if not re.search(r"dispositivos?\s*[:\-]", hn.text, re.I):
        return []
    return [target.label for target in hn.devices]


def _relevant_users(
    hn: HistoriaNegocio,
    transactional: bool,
    channel: str | None,
) -> tuple[list[str], str]:
    lowered = hn.text.lower()
    if channel == CHANNEL_EMAIL:
        return ["Registrado (tras alta)"], "Validación en canal Email tras alta de cuenta."
    if any(token in lowered for token in ("usuario no suscrit", "sin suscripción", "sin suscripcion")):
        if "suscrit" in lowered and "no suscrit" in lowered:
            return ["Suscrito", "No suscrito"], "HN distingue acceso/restricción por suscripción."
        return ["No suscrito"], "HN acota explícitamente usuario no suscrito."
    if transactional and any(token in lowered for token in ("suscrito", "registrado")) and not any(
        token in lowered for token in ("anónimo", "anonimo")
    ):
        return ["Suscrito"], "Flujo transaccional acotado a usuario suscrito/registrado."
    return [], "Sin diferencia funcional por tipo de usuario; no se multiplica por usuario."


def _mdp_for_behavior(
    hn: HistoriaNegocio,
    transactional: bool,
    interaction_points: list[str],
) -> list[str]:
    title = hn_title(hn.text).lower()
    if hn.is_payment or any(token in title for token in ("medio de pago", "medios de pago")):
        return ["Matriz MDP del BRF"]
    # Starting a hire flow is transactional but MDP is not a coverage dimension until payment is explicit.
    if transactional:
        return []
    return []


def _test_data_lines(
    brf_key: str,
    hn: HistoriaNegocio,
    interaction_points: list[str],
    channel: str | None,
    extra_blob: str | None = None,
    extra_hn_keys: list[str] | None = None,
) -> str:
    blob = extra_blob or hn.text
    keys = extra_hn_keys or [hn.key]
    lines = [f"BRF: {brf_key}", f"HN: {', '.join(keys)}"]
    points = list(interaction_points)
    if channel == CHANNEL_EMAIL and "Email" not in points and "Correo de bienvenida" not in points:
        points.append("Email")
    if points:
        lines.append("Canal / Punto de interacción: " + ", ".join(points))
    for fact in extract_supporting_facts(blob):
        lines.append(fact)
    prices = re.findall(
        r"(?:USD|U\$S|\$)\s*[\d][\d.,]*|\b\d+[.,]\d{2}\s*(?:USD)?",
        blob,
        flags=re.I,
    )
    if prices:
        lines.append("Valores declarados: " + "; ".join(dict.fromkeys(prices[:8])))
    numbered = re.findall(r"(?:^|\n)\s*\d{1,2}[\.\)]\s+([^\n]{3,80})", blob)
    if numbered:
        lines.append("Ítems declarados: " + "; ".join(item.strip() for item in numbered[:12]))
    figma = re.findall(r"figma\.com/design/[^\s)]+", blob, re.I)
    if figma:
        lines.append("Figma: " + "; ".join(figma[:3]))
    return "\n".join(dict.fromkeys(lines))


def _applicability_reason(
    *,
    channel: str | None,
    devices: list[str],
    interaction_points: list[str],
    user_reason: str,
    brf_devices: list[str],
) -> str:
    if channel == CHANNEL_EMAIL:
        return "Canal Email — fuera de matriz OTT de dispositivos."
    if not devices and channel:
        return f"Canal {channel}; no aplica dispositivo OTT/IPTV."
    if devices and devices != brf_devices:
        return (
            "Dispositivos recortados por comportamiento/punto de interacción "
            f"({', '.join(devices)})."
        )
    if devices:
        return f"Universo candidato del BRF/ecosistema ({len(devices)} dispositivos)."
    return user_reason or "Aplicabilidad por evidencia del BRF/HN."


def _row_evidence(
    brf_key: str,
    hn: HistoriaNegocio,
    draft: BehaviorDraft,
    bundle: BrfContextBundle,
) -> str:
    lines = [
        f"BRF: {brf_key}",
        f"HN: {', '.join(draft.hn_keys)}",
        f"Comportamiento: {draft.behavior_key}",
        f"Fuente HN: {bundle.hn_source}",
    ]
    if bundle.confluence_page_id:
        lines.append(f"Confluence: pageId={bundle.confluence_page_id}")
    lines.append("Extracto: " + (draft.evidence_excerpt or "")[:8000])
    return "\n".join(lines)


def _behavior_reason(hn: HistoriaNegocio, draft: BehaviorDraft, interaction_points: list[str]) -> str:
    bits = [
        f"{hn.key} describe un comportamiento funcional verificable (HN ≠ TC).",
        "Los EPC del BRF se conservan como trazabilidad; no multiplican esta fila.",
    ]
    if interaction_points:
        bits.append(
            "Los canales / puntos de interacción listados son contexto de cobertura, "
            "no un comportamiento por punto."
        )
    if draft.transactional:
        bits.append("Transaccional porque el título/HN declara inicio o flujo de contratación/pago.")
    if draft.channel == CHANNEL_EMAIL:
        bits.append("Canal Email: no es dispositivo OTT/IPTV.")
    if hn.is_negative:
        bits.append("Expectativa negativa: ausencia/no publicación, no disponibilidad positiva.")
    if draft.qc_review:
        bits.append(f"QC_REVIEW: {draft.qc_review_reason}")
    return " ".join(bits)


def _reasoning_text(
    *,
    hn: HistoriaNegocio,
    draft: BehaviorDraft,
    interaction_points: list[str],
    channel: str | None,
    devices: list[str],
    users: list[str],
    mdp: list[str],
    epc_keys: list[str],
) -> str:
    parts = [
        f"Fuente {hn.key} ({hn_title(hn.text) or hn.key}).",
        f"EPC consolidado: {', '.join(epc_keys) or '—'}.",
    ]
    if interaction_points:
        parts.append(f"Canal / Punto de interacción: {', '.join(interaction_points)}.")
    if channel:
        parts.append(f"Canal: {channel} (no se trata como dispositivo).")
    if devices:
        parts.append(f"Dispositivos aplicables: {', '.join(devices)}.")
    else:
        parts.append("Sin dispositivo OTT/IPTV aplicable.")
    if users:
        parts.append(f"Usuarios relevantes (solo si cambia el comportamiento): {', '.join(users)}.")
    else:
        parts.append("Sin split de usuario: la HN no diferencia tipos de usuario.")
    if mdp:
        parts.append(f"MDP: {', '.join(mdp)}.")
    elif draft.transactional:
        parts.append("Transaccional sin MDP explícito en la HN: no se inventa catálogo de pago.")
    if hn.is_negative:
        parts.append("Cobertura negativa: validar ausencia/no disponibilidad.")
    if draft.qc_review:
        parts.append(f"QC_REVIEW: {draft.qc_review_reason} No se inventó el detalle faltante.")
    return " ".join(parts)


def _hn_coverage_from_classification(
    brf_key: str,
    classified: dict[str, HnDisposition],
    rows: list[CoverageMatrixRow],
) -> list[HnCoverageRecord]:
    """Every HN has an explicit disposition. Grouping never deletes the HN."""
    by_hn: dict[str, list[CoverageMatrixRow]] = defaultdict(list)
    for row in rows:
        for key in row.hn_keys:
            by_hn[key].append(row)
    status_map = {
        PRIMARY: "COVERED",
        SUPPORTING: "ABSORBED",
        SCENARIO: "ABSORBED",
        TEST_DATA: "DEPENDENCY",
        DEPENDENCY_CONFIGURATION: "DEPENDENCY",
        OOS_QC: "OUT_OF_SCOPE",
    }
    records: list[HnCoverageRecord] = []
    for key, role in classified.items():
        related_rows = by_hn.get(key, [])
        if role.related_to:
            related_rows = related_rows or by_hn.get(role.related_to, [])
        behavior_keys = [row.behavior_key for row in related_rows]
        status = status_map.get(role.disposition, "UNCOVERED")
        if role.disposition == PRIMARY and related_rows:
            if any(row.origin == "QC_REVIEW" and row.scope_status != "IN_SCOPE" for row in related_rows) or (
                related_rows and related_rows[0].origin == "QC_REVIEW" and "mantener" in (related_rows[0].behavior_title or "").lower()
            ):
                status = "QC_REVIEW"
            elif any(len(row.hn_keys) > 1 for row in related_rows):
                status = "COVERED"
        if role.disposition == PRIMARY and not related_rows:
            status = "UNCOVERED"
        if role.disposition == SCENARIO and not role.related_to and related_rows:
            status = "QC_REVIEW" if related_rows[0].origin == "QC_REVIEW" else "COVERED"
        records.append(
            HnCoverageRecord(
                brf_key=brf_key,
                hn_key=key,
                status=status,  # type: ignore[arg-type]
                disposition=role.disposition,  # type: ignore[arg-type]
                related_hn=[role.related_to] if role.related_to else [],
                behavior_keys=behavior_keys,
                reason=role.reason,
            )
        )
    return records


def _hn_coverage_notes(records: list[HnCoverageRecord]) -> list[str]:
    return [
        f"{item.brf_key} {item.hn_key}: {item.disposition or item.status} — {item.reason}"
        for item in records
        if (item.disposition or item.status) not in {"PRIMARY_BEHAVIOR", "COVERED"}
    ]


def _unique(items: list[str]) -> list[str]:
    found: list[str] = []
    for item in items:
        if item and item not in found:
            found.append(item)
    return found


def _diagnostic_row(
    group: _BrfGroup,
    bundle: BrfContextBundle,
    epc_keys: list[str],
    *,
    title: str,
    reason: str,
) -> CoverageMatrixRow:
    return CoverageMatrixRow(
        brf_key=group.brf_key,
        epc_keys=epc_keys,
        hn_keys=[],
        behavior_key=f"{group.brf_key}:qc-review:scope",
        behavior_title=title,
        interaction_points=[],
        channel=None,
        ecosystem=group.ecosystem,
        applicable_devices=[],
        relevant_users=[],
        transactional=False,
        mdp=[],
        test_data=None,
        origin="QC_REVIEW",
        source="Confluence" if bundle.hn_source == "CONFLUENCE" else "Jira",
        hn_source=bundle.hn_source,
        scope_status="OUT_OF_SCOPE",
        behavior_reason=reason,
        reasoning=reason + " No se inventaron comportamientos ni se avanzó a dispositivo/TC.",
        evidence="\n".join(
            part
            for part in (
                f"BRF: {group.brf_key}",
                f"Título: {group.title}",
                f"Fuente HN: {bundle.hn_source}",
                (group.alcance_funcional or "")[:400],
                (bundle.combined_blob or "")[:400],
            )
            if part
        ),
        applicability_reason="Fuera de matriz funcional hasta que QC confirme alcance.",
        rules=["65.4"],
    )


_LOGO_IMPL = re.compile(r"^implementar (?:el )?logotipo del canal\s+(.+)$", re.I)
_NAME_UPD = re.compile(r"^actualizar nombre del canal\s+(.+)$", re.I)
_LOGO_UPD = re.compile(r"^actualizar logotipo del canal\s+(.+)$", re.I)


def _consolidate_functional_clusters(rows: list[CoverageMatrixRow]) -> list[CoverageMatrixRow]:
    """Same functional identity across channels → one behavior; channels stay as data."""
    by_brf: dict[str, list[CoverageMatrixRow]] = defaultdict(list)
    for row in rows:
        by_brf[row.brf_key].append(row)
    out: list[CoverageMatrixRow] = []
    for group in by_brf.values():
        out.extend(_cluster_one_brf(group))
    return out


def _cluster_one_brf(rows: list[CoverageMatrixRow]) -> list[CoverageMatrixRow]:
    logo_impl: list[CoverageMatrixRow] = []
    rest: list[CoverageMatrixRow] = []
    for row in rows:
        if _LOGO_IMPL.match(row.behavior_title or ""):
            logo_impl.append(row)
        else:
            rest.append(row)
    clustered: list[CoverageMatrixRow] = []
    if len(logo_impl) >= 2:
        channels = [_LOGO_IMPL.match(row.behavior_title).group(1).strip() for row in logo_impl]  # type: ignore[union-attr]
        clustered.append(
            _merge_cluster(
                logo_impl,
                title="Implementar logotipo de canales declarados",
                key_suffix="logos-canales",
                reason=(
                    "Mismo comportamiento de identidad visual. Los canales no duplican filas; "
                    "quedan como datos funcionales. HN conservadas: "
                    + ", ".join(sorted({key for row in logo_impl for key in row.hn_keys}))
                    + ". Canales: "
                    + "; ".join(channels)
                    + "."
                ),
                extra_test_data="Canales: " + "; ".join(channels),
            )
        )
    else:
        rest.extend(logo_impl)

    identity_groups: dict[str, list[CoverageMatrixRow]] = defaultdict(list)
    leftover: list[CoverageMatrixRow] = []
    for row in rest:
        channel = _identity_channel(row.behavior_title or "")
        if channel:
            identity_groups[channel].append(row)
        else:
            leftover.append(row)
    for channel, group in identity_groups.items():
        kinds = {("nombre" if _NAME_UPD.match(row.behavior_title or "") else "logo") for row in group}
        if "nombre" in kinds and "logo" in kinds:
            clustered.append(
                _merge_cluster(
                    group,
                    title=f"Actualizar nombre y logotipo del canal {channel}",
                    key_suffix="identity-" + _slug(channel),
                    reason=(
                        "Nombre y logotipo del mismo canal son un solo comportamiento de identidad. "
                        "HN conservadas: "
                        + ", ".join(sorted({key for row in group for key in row.hn_keys}))
                        + "."
                    ),
                    extra_test_data=f"Canal: {channel}",
                )
            )
        else:
            leftover.extend(group)
    return clustered + leftover


def _identity_channel(title: str) -> str | None:
    match = _NAME_UPD.match(title) or _LOGO_UPD.match(title)
    if not match:
        return None
    return match.group(1).strip()


def _merge_cluster(
    rows: list[CoverageMatrixRow],
    *,
    title: str,
    key_suffix: str,
    reason: str,
    extra_test_data: str,
) -> CoverageMatrixRow:
    first = rows[0].model_copy(deep=True)
    first.behavior_title = title[:250]
    first.behavior_key = f"{first.brf_key}:cluster:{key_suffix}"
    first.hn_keys = sorted({key for row in rows for key in row.hn_keys})
    first.epc_keys = sorted({key for row in rows for key in row.epc_keys})
    first.interaction_points = _unique(
        [point for row in rows for point in row.interaction_points]
    )
    first.applicable_devices = _unique([device for row in rows for device in row.applicable_devices])
    first.relevant_users = _unique([user for row in rows for user in row.relevant_users])
    first.test_data = "\n".join(
        part
        for part in (
            first.test_data,
            extra_test_data,
            "HN consolidadas: " + ", ".join(first.hn_keys),
        )
        if part
    )
    first.origin = "derivado"
    first.behavior_reason = reason
    first.reasoning = ((first.reasoning or "") + " " + reason).strip()
    first.duplicate_risk = "UNIQUE"
    first.duplicate_with = []
    return first


def _flag_release_polarity(rows: list[CoverageMatrixRow]) -> list[CoverageMatrixRow]:
    by_brf: dict[str, list[CoverageMatrixRow]] = defaultdict(list)
    for row in rows:
        by_brf[row.brf_key].append(row)
    for group in by_brf.values():
        no_release = [row for row in group if "no liberar" in (row.behavior_title or "").lower()]
        yes_release = [
            row
            for row in group
            if re.search(r"(?<!no )\bliberar a produc", (row.behavior_title or "").lower())
        ]
        if no_release and yes_release:
            extra = (
                " Contradicción de polaridad de liberación a producción en el mismo BRF; "
                "QC confirma cuál aplica. No se eliminó ninguna fila."
            )
            for row in no_release + yes_release:
                row.origin = "QC_REVIEW"
                row.reasoning = ((row.reasoning or "") + extra).strip()
                row.behavior_reason = ((row.behavior_reason or "") + extra).strip()
            for left in no_release:
                for right in yes_release:
                    _link_rows(left, right, "OVERLAP")
                    _link_rows(right, left, "OVERLAP")
    return rows


def _consolidate_same_behavior(rows: list[CoverageMatrixRow]) -> list[CoverageMatrixRow]:
    """Same BRF + behavior_key → one row; merge EPC keys. Never one row per EPC."""
    merged: dict[tuple[str, str], CoverageMatrixRow] = {}
    order: list[tuple[str, str]] = []
    for row in rows:
        key = (row.brf_key, row.behavior_key)
        if key not in merged:
            merged[key] = row
            order.append(key)
            continue
        existing = merged[key]
        existing.epc_keys = sorted(set(existing.epc_keys) | set(row.epc_keys))
        existing.hn_keys = sorted(set(existing.hn_keys) | set(row.hn_keys))
        extra = f" Consolidado con EPC {', '.join(row.epc_keys)}."
        if extra.strip() not in (existing.reasoning or ""):
            existing.reasoning = ((existing.reasoning or "") + extra).strip()
    return [merged[key] for key in order]


def _annotate_matrix_duplicates(rows: list[CoverageMatrixRow]) -> list[CoverageMatrixRow]:
    """Flag overlap risk between rows of the same BRF without removing any row."""
    by_brf: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        by_brf[row.brf_key].append(index)

    for indexes in by_brf.values():
        for left in indexes:
            for right in indexes:
                if left >= right:
                    continue
                a = rows[left]
                b = rows[right]
                if a.behavior_key == b.behavior_key:
                    _link_rows(a, b, "POSSIBLE_DUPLICATE")
                    continue
                if _norm(a.behavior_title) == _norm(b.behavior_title):
                    _link_rows(a, b, "OVERLAP")
                    continue
                if a.channel == CHANNEL_EMAIL and b.channel == CHANNEL_EMAIL:
                    _link_rows(a, b, "OVERLAP")
                    _link_rows(b, a, "OVERLAP")
                    continue
                # Sharing an interaction point is not overlap by itself (same add-on, different behaviors).
    return rows


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _link_rows(row: CoverageMatrixRow, other: CoverageMatrixRow, status: str) -> None:
    other_id = other.behavior_key
    if other_id not in row.duplicate_with:
        row.duplicate_with.append(other_id)
    if row.duplicate_risk == "UNIQUE":
        row.duplicate_risk = status  # type: ignore[assignment]
    elif row.duplicate_risk == "OVERLAP" and status == "POSSIBLE_DUPLICATE":
        row.duplicate_risk = "POSSIBLE_DUPLICATE"
