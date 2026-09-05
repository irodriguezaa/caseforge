"""Functional behaviors from a selected BRF. Unit of coverage is the behavior, not the HN."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.operativa_engine.devices import (
    DeviceTarget,
    ECOSYSTEM_IPTV,
    ECOSYSTEM_OTT,
    normalize_blob,
)
from app.services.operativa_engine.facts import FunctionalFacts, extract_functional_facts
from app.services.operativa_engine.families import (
    FAMILY_CAROUSEL,
    FAMILY_CHANNEL,
    FAMILY_GENERIC,
    FAMILY_IDENTITY,
    FAMILY_INFRA,
    FAMILY_MDP,
    FAMILY_OFFER,
    FAMILY_REPORTS,
    FAMILY_SIGNAL_OFF,
    classify_family,
)
from app.services.operativa_engine.hn import HistoriaNegocio, functional_historias, parse_historias


@dataclass
class Behavior:
    key: str
    title: str
    ecosystem: str | None  # None = both/any declared targets
    transactional: bool = False
    user_split: bool = False
    origin: str = "directo"
    rules: list[str] = field(default_factory=list)
    hn_keys: list[str] = field(default_factory=list)
    action: str = ""
    expected: str = ""
    test_data: str | None = None
    requires_condition: bool = False
    observations: str | None = None
    device_targets: list[DeviceTarget] | None = None
    extra_steps: list[tuple[str, str]] = field(default_factory=list)
    group_id: str | None = None
    interaction_points: list[str] = field(default_factory=list)
    hn_source: str = "HN_ABSENT"


def behaviors_for_brf(
    *,
    brf_key: str,
    title: str,
    nota_rte: str | None,
    jira_blob: str,
    alcance_funcional: str | None,
) -> tuple[list[Behavior], list[str]]:
    """Returns behaviors plus skipped-reason notes (infra/reports/dependencies)."""
    notes: list[str] = []
    family_blob = "\n".join(part for part in (title, nota_rte, alcance_funcional) if part)
    evidence = "\n".join(part for part in (title, nota_rte, alcance_funcional, jira_blob) if part)
    family = classify_family(title, family_blob)
    historias = parse_historias(evidence)
    functional = functional_historias(historias)
    facts = extract_functional_facts(title=title, evidence=evidence, historias=historias)

    for item in historias:
        if item.is_report:
            notes.append(f"{item.key}: 65.16 reportes/métricas fuera de QC.")
        if item.is_test_content:
            notes.append(f"{item.key}: 65.17 contenido de prueba = dependencia, no TC.")
        if item.superseded:
            notes.append(f"{item.key}: 65.6 sustituida; se usa el criterio vigente.")
    if facts.hn_source == "HN_ABSENT":
        notes.append("HN/CA no disponible en la fuente; no se inventa HN. Confianza reducida.")

    if family == FAMILY_INFRA:
        notes.append("65.18 dependencia de infraestructura/habilitación: 0 TCs de producto.")
        return [], notes
    if family == FAMILY_REPORTS:
        notes.append("65.16 reportes/métricas: 0 TCs QC.")
        return [], notes

    builders = {
        FAMILY_OFFER: _offer,
        FAMILY_CHANNEL: _channel,
        FAMILY_CAROUSEL: _carousel,
        FAMILY_IDENTITY: _identity,
        FAMILY_SIGNAL_OFF: _signal_off,
        FAMILY_MDP: _mdp_only,
        FAMILY_GENERIC: _generic,
    }
    behaviors = builders[family](brf_key, title, evidence, functional, facts)
    if facts.negatives and not any(row.key.endswith("negative") for row in behaviors):
        behaviors.append(_negative_absence(brf_key, title, functional, facts))
    for row in behaviors:
        row.group_id = facts.group_id
        row.interaction_points = list(facts.interaction_points)
        row.hn_source = facts.hn_source
        if not row.hn_keys:
            row.hn_keys = list(facts.hn_keys)
        if facts.hn_source == "HN_ABSENT" and row.origin == "directo" and not jira_blob.strip():
            row.origin = "inferencia"
            row.observations = (row.observations or "") + " Origen reducido: sólo título/alcance; HN ausente."
    return behaviors, notes


def _hn_keys(items: list[HistoriaNegocio], *predicates: str) -> list[str]:
    keys: list[str] = []
    for item in items:
        lowered = item.text.lower()
        if any(token in lowered for token in predicates) or not predicates:
            keys.append(item.key)
    return keys or [item.key for item in items[:1]]


def _data(facts: FunctionalFacts, *extra: str) -> str | None:
    lines = facts.test_data_lines() + [line for line in extra if line]
    return "\n".join(lines) or None


def _where(facts: FunctionalFacts, fallback: str) -> str:
    if facts.interaction_points:
        return "en " + ", ".join(facts.interaction_points[:5])
    return fallback


def _offer(
    brf_key: str,
    title: str,
    blob: str,
    hns: list[HistoriaNegocio],
    facts: FunctionalFacts,
) -> list[Behavior]:
    label = facts.offer_label or normalize_blob(title)[:80]
    where = _where(facts, "en el catálogo o punto de interacción de contratación")
    price_bit = f" Precio declarado: {'; '.join(facts.prices)}." if facts.prices else ""
    group_bit = f" Group ID {facts.group_id}." if facts.group_id else ""
    rows = [
        Behavior(
            key=f"{brf_key}:offer-available",
            title=f"Disponibilidad de la oferta — {label[:80]}",
            ecosystem=None,
            origin="directo",
            rules=["65.9", "65.4"],
            hn_keys=_hn_keys(hns, "alta", "oferta", "configur", "disponib"),
            action=f"El usuario localiza la oferta {label} {where}.",
            expected=(
                f"La oferta está publicada y visible con la vigencia y condiciones de la HN."
                f"{price_bit}{group_bit}"
            ).strip(),
            test_data=_data(facts),
            extra_steps=_offer_attribute_steps(facts),
        )
    ]
    transactional = (
        any(item.is_transactional or item.is_payment for item in hns)
        or bool(facts.acquisition)
        or any(token in blob.lower() for token in ("contrat", "renta", "medio de pago", "add on", "add-on"))
    )
    if transactional:
        mode = " / ".join(facts.acquisition) if facts.acquisition else "contratación"
        rows.append(
            Behavior(
                key=f"{brf_key}:offer-acquire",
                title=f"Contratación / {mode} de la oferta — {label[:60]}",
                ecosystem=None,
                transactional=True,
                origin="directo",
                rules=["65.9", "65.11"],
                hn_keys=_hn_keys(hns, "pago", "contrat", "adquisic", "renta", "compra", "checkout"),
                action=(
                    f"El usuario suscrito/registrado inicia el flujo de {mode} de {label} "
                    f"{_where(facts, 'desde Plan Selector / Landing / Checkout cuando aplique')}."
                ),
                expected=(
                    "El flujo de adquisición concluye según el medio de pago aplicable y deja la oferta activa. "
                    "No se inventan MDP ni precios ausentes en la fuente."
                ),
                test_data=_data(facts, "MDP según matriz/catálogo del BRF actual. No combinatoria MDP × otros comportamientos."),
            )
        )
    if any(item.is_communication for item in hns) or "comunicaci" in blob.lower():
        rows.append(
            Behavior(
                key=f"{brf_key}:offer-comms",
                title="Comunicación asociada a la oferta",
                ecosystem=None,
                origin="directo",
                rules=["65.13", "65.6"],
                hn_keys=_hn_keys(hns, "comunicaci"),
                action="El usuario recibe o visualiza la comunicación vigente de la oferta.",
                expected="El mensaje corresponde al criterio vigente (HN modificadora si existe), no a una versión sustituida.",
                test_data=_data(facts),
            )
        )
    return rows


def _offer_attribute_steps(facts: FunctionalFacts) -> list[tuple[str, str]]:
    steps: list[tuple[str, str]] = []
    if facts.trailer:
        steps.append(
            (
                "El usuario reproduce el trailer de la oferta en el punto de interacción donde la HN lo habilita.",
                "El trailer se reproduce según lo declarado. No se inventa duración ni dispositivo extra.",
            )
        )
    if facts.download:
        steps.append(
            (
                "El usuario inicia la descarga del contenido cuando la HN habilita descarga.",
                "La descarga queda disponible en las condiciones declaradas (compra/renta/dispositivo de la fuente).",
            )
        )
    if facts.ho:
        steps.append(
            (
                "El usuario verifica la condición HO declarada en la HN.",
                "La restricción u opción HO se comporta exactamente como indica la fuente.",
            )
        )
    return steps


def _channel(
    brf_key: str,
    title: str,
    blob: str,
    hns: list[HistoriaNegocio],
    facts: FunctionalFacts,
) -> list[Behavior]:
    lowered = blob.lower()
    if _negative_overrides_channel(lowered, facts, hns):
        return [_negative_absence(brf_key, title, hns, facts)]
    play_ecosystem = None
    if "ott" in lowered and "iptv" not in lowered:
        play_ecosystem = ECOSYSTEM_OTT
    elif "iptv" in lowered and "ott" not in lowered:
        play_ecosystem = ECOSYSTEM_IPTV
    channel_list = "; ".join(facts.channels) if facts.channels else None
    points = [s for s in facts.interaction_points if s not in {"Timeshift", "NPVR", "TV Everywhere"}]
    where = _where(facts, "en grilla, EPG, Player Live, Panel de Opciones, Mosaico y Buscador cuando apliquen")
    expected_alta = (
        "Los canales declarados quedan dados de alta con número, nombre, logo y categoría coherentes. "
        "Varios canales con la misma validación se cubren en este único comportamiento, no un TC por canal."
    )
    if channel_list:
        expected_alta += f" Canales: {channel_list}."
    rows = [
        Behavior(
            key=f"{brf_key}:channel-alta",
            title=f"Alta / configuración de canales — {normalize_blob(title)[:70]}",
            ecosystem=None,
            rules=["65.4", "50", "65.14"],
            hn_keys=_hn_keys(hns, "alta", "nombre", "número", "numero", "categoría", "categoria", "logo", "canal"),
            action=f"El usuario busca y configura los canales del BRF {where}.",
            expected=expected_alta,
            test_data=_data(facts),
            extra_steps=_channel_interaction_point_steps(points),
        ),
        Behavior(
            key=f"{brf_key}:channel-play",
            title="Disponibilidad / reproducción del canal",
            ecosystem=play_ecosystem,
            rules=["50", "65.8"],
            hn_keys=_hn_keys(hns, "reproduc", "url", "disponib"),
            action="El usuario sintoniza el canal y reproduce el contenido.",
            expected="El canal reproduce de forma estable en el universo aplicable.",
            test_data=_data(facts),
        ),
    ]
    if "timeshift" in lowered or " time shift" in lowered:
        rows.append(
            Behavior(
                key=f"{brf_key}:channel-ts",
                title="Timeshift del canal",
                ecosystem=ECOSYSTEM_IPTV,
                rules=["65.22", "65.8"],
                hn_keys=_hn_keys(hns, "timeshift"),
                action="El usuario usa Timeshift sobre el canal.",
                expected="Timeshift está disponible según el BRF (no se agrupa con NPVR).",
            )
        )
    if "npvr" in lowered:
        rows.append(
            Behavior(
                key=f"{brf_key}:channel-npvr",
                title="NPVR del canal",
                ecosystem=ECOSYSTEM_IPTV,
                rules=["65.22", "65.8"],
                hn_keys=_hn_keys(hns, "npvr"),
                action="El usuario graba / consulta NPVR del canal.",
                expected="NPVR funciona de forma independiente a Timeshift.",
            )
        )
    if "tv everywhere" in lowered or "tve" in lowered:
        rows.append(
            Behavior(
                key=f"{brf_key}:channel-tve",
                title="TV Everywhere",
                ecosystem=None,
                rules=["65.8", "65.23"],
                hn_keys=_hn_keys(hns, "everywhere", "tve"),
                action="El usuario reproduce el canal vía TV Everywhere desde el universo OTT cuando aplica.",
                expected="La reproducción TVE respeta paquetes y permisos del BRF.",
            )
        )
    if "chapita" in lowered:
        rows.append(
            Behavior(
                key=f"{brf_key}:channel-badge",
                title="Ausencia o presencia de chapita",
                ecosystem=ECOSYSTEM_OTT,
                rules=["50"],
                action="El usuario observa la ficha/carrusel del canal.",
                expected="La chapita se muestra o se omite exactamente como indica el BRF.",
            )
        )
    if "carrusel" in lowered:
        rows.append(
            Behavior(
                key=f"{brf_key}:channel-carousel",
                title="Presencia del canal en carrusel",
                ecosystem=ECOSYSTEM_OTT,
                rules=["50"],
                action="El usuario abre el carrusel indicado (p. ej. Locales / Infantil).",
                expected="El canal está en la posición/categoría declarada.",
            )
        )
    return rows


def _channel_interaction_point_steps(points: list[str]) -> list[tuple[str, str]]:
    if not points:
        return []
    joined = ", ".join(points)
    return [
        (
            f"El usuario recorre los canales / puntos de interacción indicados ({joined}) como el mismo alta.",
            "Identidad y publicación son consistentes. Los puntos de interacción no generan TCs separados salvo diferencia funcional.",
        )
    ]


def _negative_overrides_channel(
    lowered: str,
    facts: FunctionalFacts,
    hns: list[HistoriaNegocio],
) -> bool:
    if facts.negatives or any(item.is_negative for item in hns):
        return any(
            token in lowered
            for token in ("no habilitar", "no liberar", "no publicar", "no se encuentre publicado")
        )
    return False


def _carousel(
    brf_key: str,
    title: str,
    blob: str,
    hns: list[HistoriaNegocio],
    facts: FunctionalFacts,
) -> list[Behavior]:
    rows = [
        Behavior(
            key=f"{brf_key}:carousel-main",
            title="Carrusel de contenidos en suscripción",
            ecosystem=None,
            user_split=True,
            rules=["65.12", "65.4"],
            hn_keys=_hn_keys(hns, "carrusel"),
            action="El usuario suscrito abre el carrusel de contenidos disponibles en su suscripción.",
            expected="Nombre, posición, contenido, orden y navegación coinciden con el BRF. Atributos visuales van en el mismo caso.",
            test_data=_data(facts),
        ),
        Behavior(
            key=f"{brf_key}:carousel-unsub",
            title="Carrusel para usuario sin suscripción",
            ecosystem=None,
            user_split=False,
            origin="derivado",
            rules=["65.12"],
            action="Un usuario no suscrito abre el mismo punto de interacción del carrusel.",
            expected="Se observa la restricción o experiencia alternativa sustentada; no se combina con MDP.",
        ),
    ]
    if "premium" in blob.lower():
        rows.append(
            Behavior(
                key=f"{brf_key}:carousel-premium",
                title="Ajuste del carrusel Premium",
                ecosystem=None,
                rules=["65.4"],
                action="El usuario recorre el carrusel Premium.",
                expected="Sólo se muestran add-ons de contratación independiente; se conserva el formato de navegación.",
            )
        )
    return rows


def _identity(
    brf_key: str,
    title: str,
    blob: str,
    hns: list[HistoriaNegocio],
    facts: FunctionalFacts,
) -> list[Behavior]:
    where = _where(facts, "en los canales / puntos de interacción indicados (EPG/Player/Mosaico/Buscador si la HN los nombra)")
    rows = [
        Behavior(
            key=f"{brf_key}:identity",
            title=f"Actualización de identidad — {normalize_blob(title)[:80]}",
            ecosystem=None,
            rules=["65.14", "65.23"],
            hn_keys=_hn_keys(hns, "nombre", "logo"),
            action=f"El usuario verifica nombre y logo del canal {where}.",
            expected="Nombre y logo vigentes se presentan como una sola actualización de identidad.",
            test_data=_data(facts),
        )
    ]
    lowered = blob.lower()
    if any(token in lowered for token in ("timeshift", "npvr", "trickplay", "tv everywhere", "udp")):
        rows.append(
            Behavior(
                key=f"{brf_key}:identity-impact",
                title="Impacto en funcionalidades existentes (TS/NPVR/TVE)",
                ecosystem=None,
                origin="derivado",
                rules=["65.23"],
                action="El usuario ejecuta Timeshift, NPVR y TV Everywhere sobre el canal actualizado.",
                expected="Las capacidades existentes se mantienen. QC decide si conserva cada validación.",
                observations="65.23: no se genera un TC por cada capacidad citada en 'mantener'; se propone cobertura de impacto.",
            )
        )
    return rows


def _signal_off(
    brf_key: str,
    title: str,
    blob: str,
    hns: list[HistoriaNegocio],
    facts: FunctionalFacts,
) -> list[Behavior]:
    return [
        Behavior(
            key=f"{brf_key}:signal-off",
            title=f"Baja de señal / canal — {normalize_blob(title)[:80]}",
            ecosystem=None,
            rules=["65.27", "65.4"],
            hn_keys=[item.key for item in hns] or [],
            action="El usuario busca el canal o señal dado de baja.",
            expected="El canal/señal no está disponible en el line-up ni es sintonizable.",
            test_data=_data(facts),
        )
    ]


def _mdp_only(
    brf_key: str,
    title: str,
    blob: str,
    hns: list[HistoriaNegocio],
    facts: FunctionalFacts,
) -> list[Behavior]:
    if facts.negatives or "no liberar" in blob.lower() or "no habilitar" in blob.lower():
        return [_negative_absence(brf_key, title, hns, facts)]
    return [
        Behavior(
            key=f"{brf_key}:mdp",
            title="Habilitación de medios de pago",
            ecosystem=None,
            transactional=True,
            rules=["65.11"],
            hn_keys=_hn_keys(hns, "pago"),
            action="El usuario suscrito/registrado inicia un flujo de pago en el dispositivo aplicable.",
            expected="Los MDP declarados para ese dispositivo están disponibles. No se combina con usuario no suscrito.",
            test_data=_data(facts, "Catálogo MDP del BRF actual. No inventar Visa/PayPal si el BRF no los nombra."),
        )
    ]


def _generic(
    brf_key: str,
    title: str,
    blob: str,
    hns: list[HistoriaNegocio],
    facts: FunctionalFacts,
) -> list[Behavior]:
    label = normalize_blob(title)[:120] or f"Cobertura funcional {brf_key}"
    where = _where(facts, "en los canales / puntos de interacción que la fuente nombre")
    origin = "directo" if hns else "inferencia"
    action = f"El usuario ejecuta {label} {where}."
    expected = "Se observa el resultado funcional declarado en la HN/alcance, con los datos explícitos de la fuente."
    if facts.hn_source == "HN_ABSENT":
        action = (
            f"El usuario ejecuta el alcance del BRF ({label}) {where}. "
            "HN/CA no está en la fuente; no se inventa el detalle."
        )
        expected = "Se verifica únicamente lo declarado en título/alcance. Confianza reducida por ausencia de HN."
    return [
        Behavior(
            key=f"{brf_key}:functional",
            title=label,
            ecosystem=None,
            rules=["65.4", "65.39"],
            hn_keys=[item.key for item in hns],
            action=action,
            expected=expected,
            test_data=_data(facts),
            observations="Familia no catalogada: QC debe confirmar si la cobertura es suficiente.",
            origin=origin,
        )
    ]


def _negative_absence(
    brf_key: str,
    title: str,
    hns: list[HistoriaNegocio],
    facts: FunctionalFacts | None = None,
) -> Behavior:
    subject = (facts.negatives[0] if facts and facts.negatives else None) or title
    return Behavior(
        key=f"{brf_key}:negative",
        title=f"Ausencia / no publicación — {normalize_blob(subject)[:80]}",
        ecosystem=None,
        origin="directo",
        rules=["65.27", "49"],
        hn_keys=_hn_keys(hns, "no liberar", "no habilitar", "no publicar"),
        action=f"El usuario busca {subject} en line-up, EPG y buscador.",
        expected=f"Validar que {subject} no se encuentre publicado/disponible.",
        test_data=_data(facts) if facts else None,
    )
