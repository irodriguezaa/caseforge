"""Positive QC filter: end-user actor, visible surface, device-verifiable result.

Roles and surfaces are categories. Never ticket, device, region, or key names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas.case_generation import CoverageUnit, GeneratedCaseCandidate, GenerationStats

_WHEN = re.compile(r"^\s*(When|Cuando)\b(.*)$", re.IGNORECASE | re.MULTILINE)
_THEN = re.compile(r"^\s*(Then|Entonces|And|Y|Pero|But)\b(.*)$", re.IGNORECASE | re.MULTILINE)

_NON_USER_ACTOR = re.compile(
    r"\b(tech lead|\btl\b|desarrollador|\bdevs?\b|arquitectura|f[aá]brica|"
    r"pipeline|administrador|\bapa\b|\bgco\b)\b",
    re.IGNORECASE,
)
_USER_ACTOR = re.compile(
    r"\b((el|la|los|las|un|una) usuari[oa]s?|el cliente|el espectador|el perfil)\b",
    re.IGNORECASE,
)
_STORY_NON_USER = re.compile(
    r"como (tech lead|\btl\b|desarrollador|equipo de desarrollo|f[aá]brica|"
    r"arquitectura|plataforma)\b",
    re.IGNORECASE,
)
_APP_PRESENTS = re.compile(
    r"\b(arranca|se presenta(n)?|se muestra(n)?|se pinta(n)?|"
    r"se abre(n)?|se visualiza(n)?)\b",
    re.IGNORECASE,
)
_OFF_DEVICE = re.compile(
    r"se revisa(n)? (el |la |los |las )?(c[oó]digo|manifiesto|contenido del build|"
    r"listado|inventario|cat[aá]logo|llamadas|eventos)|"
    r"herramienta (de )?(medici[oó]n|monitoreo)|"
    r"\ben logs\b|"
    r"requiere herramienta|"
    r"se entrega(r)?|"
    r"\bpipeline\b|"
    r"formaliz|"
    r"datadog|"
    r"empaquetar|"
    r"queda registrada en (la lista|el inventario|apa|gco)|"
    r"evidencia en apa",
    re.IGNORECASE,
)
_VISIBLE_THEN = re.compile(
    r"\b(se muestra(n)?|se visualiza(n)?|se pinta(n)?|se abre(n)?|se oculta(n)?|"
    r"no se muestra(n)?|deben? mostrar(se)?|debe visualizarse|redirige|se reproduce|"
    r"mensaje de error|se cierra|se reanuda|se ven\b|"
    r"contin[uú]a la reproducci[oó]n|se aplica(n)?|"
    r"permanece en la pantalla|errores de renderizado|layout aprobado|"
    r"no debe presentar errores|no se rompe|transiciona|renderiza|"
    r"deja de mostrar|primera pantalla|se presenta(n)?|pantalla vac[ií]a|"
    r"ve (el|la|los|las)|muestra el|muestra la|inicia sesi[oó]n|"
    r"reflej|sincroniz|icono|ícono|estructura|texto de error|"
    r"espacio donde|elementos|se pausa|se solicita|se mueve|"
    r"vinculaci[oó]n no se completa|se permite)\b",
    re.IGNORECASE,
)
_CONSUMED = re.compile(
    r"\b(llaves?|textos?|traducci[oó]n|configuraci[oó]n|assets?)\b",
    re.IGNORECASE,
)
_GENERIC_REGRESSION = re.compile(
    r"sin regresiones|comportamiento de la aplicaci[oó]n|"
    r"no altera nada m[aá]s|se ven igual|versi[oó]n anterior",
    re.IGNORECASE,
)
_DOCUMENT_SURFACE = re.compile(
    r"\b(listado|inventario|manifiesto|documentaci[oó]n|"
    r"cat[aá]logo de pantallas|cat[aá]logo entregado|"
    r"entrega a arquitectura|cierre de ficha|"
    r"queda registrada|registro del tama[nñ]o)\b",
    re.IGNORECASE,
)

# Screen/flow families. Same key = same bug. Categories, not ticket names.
_SURFACES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("marca-placeholder", re.compile(r"placeholders?", re.I)),
    ("marca-ausente", re.compile(r"sin .{0,40}cargado|pantalla no se rompe", re.I)),
    ("marca-cambio", re.compile(r"no requiere publicar|sin (un )?despliegue", re.I)),
    ("marca-operacion", re.compile(r"operaciones distintas|distintos por operaci[oó]n", re.I)),
    ("marca-modales", re.compile(r"modal.{0,60}pin|modal de perfil", re.I)),
    ("marca-chrome", re.compile(
        r"identidad visual|imagen de (la )?marca|logotipo|en cada ubicaci[oó]n|nodo del men[uú]|"
        r"se visualiza(n)? con su dimensi[oó]n",
        re.I,
    )),
    ("first-paint", re.compile(r"se pinta|ocurre en paralelo|pinta con recursos", re.I)),
    ("primera-sin-sesion", re.compile(
        r"pantallas iniciales|textos e im[aá]genes iniciales|im[aá]genes iniciales|"
        r"imagen de landing|landing sigue siendo|"
        r"va a landing|va a onboarding|landing u onboarding",
        re.I,
    )),
    ("sesion-vencida", re.compile(r"no autorizado|renovaci[oó]n falla|renovaci[oó]n fall", re.I)),
    ("error-arranque", re.compile(r"error de pa[ií]s", re.I)),
    ("texto-ui", re.compile(r"espacio al (final|inicio)|lectura mal formada|texto.{0,60}cat[aá]logo", re.I)),
    ("autologin", re.compile(r"vinculaci[oó]n autom[aá]tica|auto-?login", re.I)),
    ("landing", re.compile(r"\blanding\b|\bonboarding\b", re.I)),
    ("seleccion-perfil", re.compile(r"selecci[oó]n de perfil", re.I)),
    ("migracion", re.compile(r"migraci[oó]n", re.I)),
    ("error-ui", re.compile(r"pantalla(s)? de error|mensaje de error", re.I)),
    ("boton", re.compile(r"\bbot[oó]n\b", re.I)),
    ("home", re.compile(r"\bhome\b|brandheader|background comercial", re.I)),
    ("player", re.compile(r"\bplayer\b|reproducci[oó]n", re.I)),
    ("checkout", re.compile(r"\bcheckout\b|\bcompra\b|\bpago\b", re.I)),
    ("guia", re.compile(r"gu[ií]a de programaci[oó]n|\bla gu[ií]a\b", re.I)),
    ("modal", re.compile(r"\bmodal\b", re.I)),
    ("pantalla", re.compile(r"\bpantalla\b|\bcarrusel\b|\bficha\b|\bbanner\b", re.I)),
)

_CRITERIO_ACTOR = "actor no es el usuario final de la app"
_CRITERIO_SUPERFICIE = "no hay superficie visible en el dispositivo"
_CRITERIO_VERIFICACION = "el resultado no se verifica mirando el dispositivo"


@dataclass
class Eligibility:
    ok: bool
    pending: bool
    actor_ok: bool | None
    surface_ok: bool | None
    device_ok: bool | None
    surface: str | None
    consumed: bool
    generic_regression: bool
    reasons: list[str] = field(default_factory=list)

    @property
    def ledger_estado(self) -> str:
        if self.pending:
            return "pendiente de revisión QC"
        if self.ok:
            return "caso ejecutable"
        return "verificación técnica"

    @property
    def ledger_motivo(self) -> str:
        if self.reasons:
            return "; ".join(self.reasons)
        return _CRITERIO_THEN


def _clauses(body: str, pattern: re.Pattern[str]) -> str:
    return " ".join(match.group(2) or "" for match in pattern.finditer(body or ""))


def has_end_user_actor(text: str) -> bool:
    return bool(_USER_ACTOR.search(text or ""))


def detect_surface(title: str, body: str) -> str | None:
    then = _clauses(body, _THEN)
    when = _clauses(body, _WHEN)
    blob = f"{title}\n{then}"
    if _VISIBLE_THEN.search(then) and not _OFF_DEVICE.search(when):
        blob = f"{title}\n{when}\n{then}"
    if _DOCUMENT_SURFACE.search(title or "") or _OFF_DEVICE.search(title or ""):
        return None
    if _DOCUMENT_SURFACE.search(then):
        return None
    if _OFF_DEVICE.search(when) and not _VISIBLE_THEN.search(then):
        return None
    if re.search(r"se ven igual que en la versi[oó]n anterior", blob, re.I):
        return "impacto-app"
    if _GENERIC_REGRESSION.search(blob):
        return "impacto-app"
    for key, pattern in _SURFACES:
        if pattern.search(blob):
            if key == "marca-placeholder" and re.search(r"logotipo", blob, re.I):
                continue
            return key
    return None


_NON_OBSERVABLE = re.compile(
    r"\b(servicio|api\b|petici[oó]n|endpoint|llaves?|"
    r"apa/metadata|apa/assets|manifiesto|"
    r"m[eé]trica|\bdat\b|datadog|\blogs?\b|build|pipeline|c[oó]digo|"
    r"inventario|hash|formaliz|consultar la llave|valor (efectivo|por defecto)|"
    r"evento[s]? (de telemetr|\w+\.\w+)|se recupera del|consulta de pa[ií]s|"
    r"gco|backend|embebido|remot[oa]s?|documentaci[oó]n)\b",
    re.IGNORECASE,
)
_ROBUST_CONSUMPTION = re.compile(
    r"no se logra obtener|se encuentra vac[ií]a",
    re.IGNORECASE,
)
_UNREADABLE_THEN = re.compile(
    r"demo mostrar|siguientes elementos\s*:?\s*$|<\s*>|^\s*[.:;,-]*\s*$",
    re.IGNORECASE,
)
_CRITERIO_THEN = "Then vacío, ilegible o contradictorio"


def result_clauses(body: str) -> list[str]:
    """Then and the And/But that follow it, not Given/When And."""
    clauses: list[str] = []
    capturing = False
    for raw in (body or "").splitlines():
        line = raw.strip()
        if re.match(r"^\s*(Then|Entonces)\b", line, re.I):
            capturing = True
            clauses.append(re.sub(r"^\s*(Then|Entonces)\s*", "", line, flags=re.I).strip())
        elif capturing and re.match(r"^\s*(And|Y|Pero|But)\b", line, re.I):
            clauses.append(re.sub(r"^\s*(And|Y|Pero|But)\s*", "", line, flags=re.I).strip())
        elif capturing and re.match(r"^\s*(Given|Dado|When|Cuando|Scenario)\b", line, re.I):
            capturing = False
    return [item for item in clauses if item]


def _normalize_verbs(text: str) -> str:
    out = text or ""
    out = re.sub(r"\bno\s+deben?\s+mostrarse\b", "no se muestra", out, flags=re.I)
    out = re.sub(r"\bdeben?\s+mostrarse\b", "se muestra", out, flags=re.I)
    out = re.sub(r"\bmostrarse\b", "se muestra", out, flags=re.I)
    out = re.sub(r"\bno\s+mostrar\b", "no se muestra", out, flags=re.I)
    out = re.sub(r"\bdebe mostrar\b", "se muestra", out, flags=re.I)
    out = re.sub(r"\bredirigir\b", "redirige", out, flags=re.I)
    out = re.sub(r"\bpermitir\s+", "se permite ", out, flags=re.I)
    out = re.sub(r"\bocultarse\b", "se oculta", out, flags=re.I)
    return out


def _clause_kind(text: str) -> str:
    blob = _normalize_verbs(text or "")
    tech = bool(_NON_OBSERVABLE.search(blob) or _OFF_DEVICE.search(blob))
    ui = bool(_VISIBLE_THEN.search(blob) or _APP_PRESENTS.search(blob))
    if tech and not ui:
        return "tech"
    if tech and ui and re.search(
        r"\b(backend|embebido|remot[oa]s?|valor por defecto compilado)\b", blob, re.I
    ):
        return "tech"
    return "visible"


def _then_is_broken(clauses: list[str]) -> str:
    text = " ".join(clauses).strip()
    if not text:
        return _CRITERIO_THEN
    if _UNREADABLE_THEN.search(text):
        return _CRITERIO_THEN
    positives = {
        re.sub(r"\bno\s+", "", _normalize_verbs(item), flags=re.I).lower()
        for item in clauses
        if not re.search(r"\bno\s+", item, re.I)
    }
    for item in clauses:
        if not re.search(r"\bno\s+", item, re.I):
            continue
        core = re.sub(r"\bno\s+", "", _normalize_verbs(item), flags=re.I).lower()
        if core in positives:
            return _CRITERIO_THEN
    return ""


def is_robust_consumption(title: str, body: str = "") -> bool:
    return bool(_ROBUST_CONSUMPTION.search(f"{title}\n{body}"))


def split_visible_technical(body: str, title: str = "") -> tuple[list[str], list[str]]:
    clauses = result_clauses(body)
    if not clauses and title:
        clauses = [title]
    visible = [item for item in clauses if _clause_kind(item) == "visible"]
    technical = [item for item in clauses if _clause_kind(item) == "tech"]
    return visible, technical


def evaluate_scenario(title: str, body: str, summary: str = "") -> Eligibility:
    blob = f"{summary}\n{title}\n{body}"
    when = _clauses(body, _WHEN) or title
    then_parts = result_clauses(body)
    then_norm = _normalize_verbs(" ".join(then_parts))
    visible_cs, tech_cs = split_visible_technical(body, title)
    surface = detect_surface(title, body)
    if not surface and visible_cs:
        surface = "ui-visible"
    if surface == "regresion-generica":
        surface = "impacto-app"
    specific = bool(surface) and surface not in {"regresion-generica", "impacto-app", "ui-visible"}
    consumed = bool(_CONSUMED.search(blob))
    generic = bool(_GENERIC_REGRESSION.search(blob)) or surface in {"regresion-generica", "impacto-app"}

    non_user = bool(
        _NON_USER_ACTOR.search(when)
        or _NON_USER_ACTOR.search(title)
        or _STORY_NON_USER.search(summary or "")
        or _STORY_NON_USER.search(when)
    )
    user = bool(_USER_ACTOR.search(when) or _USER_ACTOR.search(title))
    ui_then = bool(_VISIBLE_THEN.search(then_norm) or _APP_PRESENTS.search(then_norm))
    ui_hit = any(
        _VISIBLE_THEN.search(_normalize_verbs(item)) or _APP_PRESENTS.search(item)
        for item in visible_cs
    )
    visible = bool(ui_hit) or (bool(visible_cs) and not tech_cs)
    if _OFF_DEVICE.search(when) and not ui_then:
        visible = False
        visible_cs = []
    if non_user and not user:
        actor_ok: bool | None = True if (
            ui_then or _APP_PRESENTS.search(when) or generic
        ) else False
    else:
        actor_ok = True

    all_tech = bool(tech_cs) and not visible_cs
    broken = _then_is_broken(then_parts)
    if broken:
        surface_ok: bool | None = False
        device_ok: bool | None = False
        reasons = [broken]
        return Eligibility(
            ok=False,
            pending=True,
            actor_ok=actor_ok,
            surface_ok=surface_ok,
            device_ok=device_ok,
            surface=surface,
            consumed=consumed,
            generic_regression=generic,
            reasons=reasons,
        )

    if _DOCUMENT_SURFACE.search(title or "") and all_tech:
        surface_ok = False
    elif visible or specific:
        surface_ok = True
    elif generic and all_tech:
        surface_ok = False
    elif all_tech:
        surface_ok = False
    else:
        surface_ok = True

    device_ok = True if visible else False

    reasons: list[str] = []
    if actor_ok is False:
        reasons.append(_CRITERIO_ACTOR)
    if surface_ok is False:
        reasons.append(_CRITERIO_SUPERFICIE)
    if device_ok is False:
        reasons.append(_CRITERIO_VERIFICACION)

    ok = actor_ok is True and surface_ok is True and device_ok is True
    pending = False
    return Eligibility(
        ok=ok,
        pending=pending,
        actor_ok=actor_ok,
        surface_ok=surface_ok,
        device_ok=device_ok,
        surface=surface,
        consumed=consumed,
        generic_regression=generic,
        reasons=reasons,
    )


def evaluate_candidate(candidate: GeneratedCaseCandidate) -> Eligibility:
    steps = "\n".join(
        f"When {step.action}\nThen {step.expected_result}" for step in candidate.steps
    )
    return evaluate_scenario(candidate.name, steps, candidate.use_case_title or "")


_SAME_BUG_SURFACES = {
    "first-paint",
    "primera-sin-sesion",
    "landing",
    "autologin",
    "seleccion-perfil",
    "sesion-vencida",
    "error-arranque",
    "migracion",
    "error-ui",
    "marca-chrome",
    "marca-modales",
    "marca-operacion",
    "marca-cambio",
    "marca-ausente",
    "marca-placeholder",
    "texto-ui",
    "impacto-app",
}


_ENTRY = (
    ("sesion-vencida", re.compile(r"no autorizado|renovaci[oó]n", re.I)),
    ("sin-sesion", re.compile(r"sin identificador", re.I)),
    ("con-sesion", re.compile(r"identificador local|con sesi[oó]n", re.I)),
    ("red", re.compile(r"vinculaci[oó]n autom[aá]tica|auto-?login|acceso por ip", re.I)),
    ("config-ausente", re.compile(r"sin .{0,40}cargado|no tiene .{0,40}cargado", re.I)),
    ("config-cambio", re.compile(r"no requiere publicar|cambia (el|la)|tras el cambio", re.I)),
    ("config-on", re.compile(r"habilitad", re.I)),
    ("otra-operacion", re.compile(r"operaciones distintas|otra operaci", re.I)),
    ("placeholder", re.compile(r"placeholders?", re.I)),
)


def detect_entry(title: str, body: str, surface: str | None = None) -> str:
    blob = f"{title}\n{body}"
    for key, pattern in _ENTRY:
        if pattern.search(blob):
            if key == "con-sesion" and re.search(r"sin identificador|sin sesi[oó]n", blob, re.I):
                continue
            if key == "placeholder" and re.search(r"logotipo", blob, re.I):
                continue
            return key
    if surface == "primera-sin-sesion":
        return "sin-sesion"
    return "default"


def surface_group_key(
    epic_key: str, surface: str | None, scenario: str, story_key: str = "", body: str = ""
) -> str:
    """Same bug: same surface and same entry condition (session, network, config)."""
    entry = detect_entry(scenario, body, surface)
    if surface in _SAME_BUG_SURFACES:
        return f"{epic_key}|{surface}|{entry}"
    return f"{epic_key}|{story_key}|scenario|{scenario}"


def collapse_redundant_surfaces(units: list[CoverageUnit]) -> list[CoverageUnit]:
    """Same named surface in a story absorbs generic regression of that story."""
    by_story: dict[str, list[CoverageUnit]] = {}
    for unit in units:
        by_story.setdefault(unit.story_key or unit.coverage_id, []).append(unit)

    def _tail(unit: CoverageUnit) -> str:
        return (unit.scenario_group or "").split("|")[-1]

    def _set_family(unit: CoverageUnit, family: str) -> None:
        epic = unit.artifact_key or unit.rn_key or ""
        unit.scenario_group = f"{epic}|{family}"

    for rows in by_story.values():
        named = {
            (unit.scenario_group or "").split("|")[1]
            for unit in rows
            if len((unit.scenario_group or "").split("|")) >= 2
            and (unit.scenario_group or "").split("|")[1] in _SAME_BUG_SURFACES
        } - {"impacto-app"}
        if len(named) != 1:
            continue
        only = next(iter(named))
        sibling_entries = {
            (unit.scenario_group or "").split("|")[2]
            for unit in rows
            if len((unit.scenario_group or "").split("|")) >= 3
            and (unit.scenario_group or "").split("|")[1] == only
        }
        join_entry = next(iter(sibling_entries)) if len(sibling_entries) == 1 else "default"
        for unit in rows:
            parts = (unit.scenario_group or "").split("|")
            family = parts[1] if len(parts) >= 2 else _tail(unit)
            if family not in _SAME_BUG_SURFACES or family in {
                "impacto-app",
                "regresion-generica",
                "ui-visible",
                "pantalla",
            }:
                epic = unit.artifact_key or unit.rn_key or ""
                unit.scenario_group = f"{epic}|{only}|{join_entry}"
    return units


_NAMED_IMPACT_SURFACES = (_SAME_BUG_SURFACES | {"boton", "home", "player", "checkout", "guia"}) - {
    "impacto-app",
    "pantalla",
}


def is_consumed_device_impact(elig: Eligibility) -> bool:
    """Technical Then on a consumed config that still names a user-visible surface."""
    return (
        elig.device_ok is False
        and elig.surface_ok is True
        and elig.consumed
        and (elig.surface or "") in _NAMED_IMPACT_SURFACES
    )


@dataclass
class SelectedGherkin:
    story_key: str
    title: str
    body: str
    group: str
    kind: str


def select_qc_gherkin(
    epic_key: str,
    rows: list[tuple[str, str, str, str]],
) -> tuple[list[SelectedGherkin], list[dict]]:
    """Shared gate: direct pass, one impact per surface, rest to ledger. No engine-specific rules."""
    kept: list[SelectedGherkin] = []
    dropped: list[dict] = []
    direct_groups: set[str] = set()
    classified: list[tuple[str, str, str, str, Eligibility]] = []
    any_consumed = False
    for story_key, title, body, summary in rows:
        elig = evaluate_scenario(title, body, summary)
        classified.append((story_key, title, body, summary, elig))
        blob = f"{summary}\n{title}\n{body}"
        if elig.consumed or _CONSUMED.search(blob):
            any_consumed = True
        group = surface_group_key(epic_key, elig.surface, title, story_key, body)
        if elig.ok:
            kept.append(SelectedGherkin(story_key, title, body, group, "directo"))
            direct_groups.add(group)
            continue
        dropped.append(
            {
                "story": story_key,
                "epic": epic_key,
                "scenario": title,
                "estado": elig.ledger_estado,
                "motivo": elig.ledger_motivo,
                "case_id": "",
                "surface_group": group,
            }
        )

    impact_groups: set[str] = set()
    revived: list[SelectedGherkin] = []
    note = "cubierto por el caso de la misma superficie y condición de entrada"
    still_dropped: list[dict] = []
    for story_key, title, body, summary, elig in classified:
        if elig.ok:
            continue
        group = surface_group_key(epic_key, elig.surface, title, story_key, body)
        row = next(
            (item for item in dropped if item["story"] == story_key and item["scenario"] == title),
            None,
        )
        blob = f"{summary}\n{title}\n{body}"
        if is_consumed_device_impact(elig):
            if group in direct_groups or group in impact_groups:
                if row is not None:
                    row["motivo"] = f"{row.get('motivo')}; {note}".strip("; ")
                    still_dropped.append(row)
                continue
            action, then = impact_user_view(elig.surface or "", title)
            revived.append(
                SelectedGherkin(
                    story_key,
                    title,
                    f"When {action}\nThen {then}",
                    group,
                    "impacto",
                )
            )
            impact_groups.add(group)
            continue
        surface = detect_surface(title, body)
        generic = elig.generic_regression or bool(
            re.search(r"comportamiento de la aplicaci[oó]n|sin regresiones", blob, re.I)
        )
        if (
            any_consumed
            and generic
            and (not surface or surface in {"regresion-generica", "ui-visible", "impacto-app", None})
        ):
            group = f"{epic_key}|impacto-app"
            if group in direct_groups:
                if row is not None:
                    row["motivo"] = f"{row.get('motivo')}; {note}".strip("; ")
                    still_dropped.append(row)
                continue
            revived.append(
                SelectedGherkin(
                    story_key,
                    title,
                    "When el usuario abre las pantallas afectadas\n"
                    "Then se ven igual que en la versión anterior",
                    group,
                    "impacto",
                )
            )
            continue
        if row is not None:
            still_dropped.append(row)
    kept.extend(revived)
    drop_keys = {(item.story_key, item.title) for item in kept}
    leftover = [
        row for row in dropped if (row["story"], row["scenario"]) not in drop_keys
    ]
    return kept, leftover


def impact_user_view(surface: str, title: str) -> tuple[str, str]:
    """When/Then the tester can see on the device. Categories, not key names."""
    blob = f"{surface} {title}"
    if surface == "marca-placeholder" or re.search(r"placeholders?", blob, re.I):
        return (
            "el usuario abre las tarjetas",
            "se muestra el placeholder correcto según la forma de la tarjeta",
        )
    if surface.startswith("marca-") or re.search(r"logotipo|logo", blob, re.I):
        return ("el usuario abre la pantalla", "se muestra el logotipo en esa pantalla")
    if surface == "texto-ui" or re.search(r"textos?", blob, re.I):
        return ("el usuario abre la pantalla", "se muestra el texto vigente")
    return ("el usuario abre la pantalla afectada", "se ve el efecto del cambio en el dispositivo")


def _annotate_covered_surface(stats: GenerationStats, story_key: str, title: str) -> None:
    note = "cubierto por el caso de la misma superficie y condición de entrada"
    for row in stats.scenario_ledger:
        if row.get("story") == story_key and row.get("scenario") == title:
            motivo = str(row.get("motivo") or "")
            if note not in motivo:
                row["motivo"] = f"{motivo}; {note}".strip("; ")
            break


def synthesize_impact_units(
    *,
    epic_key: str,
    blocks: list[tuple[dict, dict]],
    rn_filename: str,
    seq_holder: list[int],
    stats: GenerationStats,
    existing_units: list[CoverageUnit] | None = None,
) -> list[CoverageUnit]:
    """One impact case per affected user surface when consumed config is not device-verifiable."""
    existing_groups = {
        (unit.scenario_group, unit.story_key)
        for unit in (existing_units or [])
        if unit.scenario_group
    }
    consumed = False
    want_named: dict[str, list[tuple[dict, dict]]] = {}
    want_generic: dict[str, list[tuple[dict, dict]]] = {}
    for story, block in blocks:
        title = str(block.get("title") or "")
        body = str(block.get("body") or "")
        summary = str(story.get("summary") or "")
        story_key = str(story.get("key") or epic_key)
        elig = evaluate_scenario(title, body, summary)
        blob = f"{summary}\n{title}\n{body}"
        if elig.consumed or _CONSUMED.search(blob):
            consumed = True
        if elig.ok:
            continue
        if _DOCUMENT_SURFACE.search(title) and not _VISIBLE_THEN.search(body):
            continue
        if is_consumed_device_impact(elig):
            group = surface_group_key(epic_key, elig.surface, title, story_key, body)
            if (group, story_key) in existing_groups:
                _annotate_covered_surface(stats, story_key, title)
                continue
            want_named.setdefault(group, []).append((story, block))
            continue
        surface = detect_surface(title, body)
        if surface and surface not in {"regresion-generica", "ui-visible", "impacto-app", None}:
            continue
        if elig.generic_regression or re.search(
            r"comportamiento de la aplicaci[oó]n|sin regresiones",
            blob,
            re.I,
        ):
            want_generic.setdefault("app", []).append((story, block))
    if not consumed:
        return []
    units: list[CoverageUnit] = []
    for group, rows in want_named.items():
        story, block = rows[0]
        title = str(block.get("title") or "")
        body = str(block.get("body") or "")
        summary = str(story.get("summary") or "")
        elig = evaluate_scenario(title, body, summary)
        action, then = impact_user_view(elig.surface or "", title)
        seq_holder[0] += 1
        story_key = str(story.get("key") or epic_key)
        for extra_story, extra_block in rows[1:]:
            _annotate_covered_surface(
                stats,
                str(extra_story.get("key") or epic_key),
                str(extra_block.get("title") or ""),
            )
        units.append(
            CoverageUnit(
                coverage_id=f"COV-{seq_holder[0]:03d}",
                role="G",
                behavior=then,
                scenario=title,
                evidence=f"{story_key}: {title}",
                jira_key=story_key,
                rn_key=epic_key,
                feature_story=story_key,
                body=f"When {action}\nThen {then}",
                description=then,
                rn_filename=rn_filename,
                artifact_key=epic_key,
                story_key=story_key,
                observable_then=[then],
                test_intent=then,
                qc_relevance="QC_REGRESSION",
                user_action=action,
                source_origin="gherkin",
                applied_rules=["impacto-superficie"],
                scenario_group=group,
                story_summary=summary,
                traceability=f"RN={epic_key}; impacto={elig.surface}",
            )
        )
        existing_groups.add(group)
    body_gherkin = (
        "When el usuario abre las pantallas afectadas\n"
        "Then se ven igual que en la versión anterior"
    )
    for _key, rows in want_generic.items():
        for story, block in rows:
            title = str(block.get("title") or "")
            seq_holder[0] += 1
            story_key = str(story.get("key") or epic_key)
            units.append(
                CoverageUnit(
                    coverage_id=f"COV-{seq_holder[0]:03d}",
                    role="G",
                    behavior=title,
                    scenario=title,
                    evidence=f"{story_key}: {title}",
                    jira_key=story_key,
                    rn_key=epic_key,
                    feature_story=story_key,
                    body=body_gherkin,
                    description=title,
                    rn_filename=rn_filename,
                    artifact_key=epic_key,
                    story_key=story_key,
                    observable_then=["se ven igual que en la versión anterior"],
                    test_intent=title,
                    qc_relevance="QC_REGRESSION",
                    user_action="el usuario abre las pantallas afectadas",
                    source_origin="gherkin",
                    applied_rules=["impacto-superficie"],
                    scenario_group=f"{epic_key}|impacto-app",
                    story_summary=str(story.get("summary") or ""),
                    traceability=f"RN={epic_key}; impacto=app",
                )
            )
    return units
