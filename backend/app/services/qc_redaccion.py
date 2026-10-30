"""Redacción QC determinista: da forma de caso de prueba a un caso ya armado.

No decide elegibilidad, agrupación ni conteo. Solo reescribe nombre, precondición,
pasos y resultados para que un tester los ejecute desde el dispositivo:

- Precondición en lenguaje natural que deja al tester en el punto de partida.
- Pasos = acciones reales del usuario (navegación + acción). Nunca "Abrir aplicación",
  nunca títulos de historia ("Implementar ...", "Construcción de ...") como paso.
- Resultado esperado = lo que se ve en pantalla. Sin llaves, servicios, Figma, nodos,
  enlaces ni formatos internos.
- Nombre = qué se prueba, sin términos técnicos, sin sufijos de historia.

Las superficies son categorías de la app (Player, Guía, panel Más información...),
nunca tickets ni dispositivos. Es idempotente: aplicarla dos veces no cambia el caso.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from app.schemas.case_generation import CandidateStep, GeneratedCaseCandidate

# --------------------------------------------------------------------------- superficies


@dataclass(frozen=True)
class Surface:
    key: str
    label: str  # cómo se nombra en un caso: "el panel Más información"
    short: str  # para nombres: "Panel Más información"
    match: str  # regex sobre nombre/escenario/historia
    precondition: str  # estado de partida, en lenguaje natural
    entry: tuple[str, str] | None = None  # paso para abrir la superficie desde la precondición
    entry_done: str = ""  # regex de acciones que ya abren la superficie
    nav_alias: str = ""  # regex de pasos "Ingresar/Abrir <superficie>" que se reemplazan


_PLAYER_PRE = "El usuario está reproduciendo un canal en vivo en el Player de TV"
_CP_STEP = ("Mover el cursor sobre la reproducción para mostrar el Control Player", "Se muestra el Control Player de TV")
_GUIA_STEP = ('Seleccionar la opción "Guía" en el Control Player', "Se muestra la Guía de programación")

SURFACES: tuple[Surface, ...] = (
    Surface(
        "recordatorio",
        'el modal de "Recordatorio de evento"',
        "Modal de recordatorio",
        r"recordatorio de evento|modal de .?recordatorio|\brecordatorio\b.*\bmodal\b",
        "El usuario tiene un recordatorio programado para un evento próximo a iniciar",
        ("Esperar a que se cumpla el horario del recordatorio", 'Se muestra el modal de "Recordatorio de evento"'),
        r"modal de .?recordatorio|esperar",
        r"modal de .?recordatorio",
    ),
    Surface(
        "filtro-fecha",
        "el Filtro de fecha de la Guía de programación",
        "Filtro de fecha",
        r"filtro de fecha|filtrado por fecha|\bfiltro\b",
        _PLAYER_PRE,
        ("Seleccionar el Filtro de fecha", "Se despliega el listado de fechas"),
        r"filtro|flecha del filtro|fecha",
        r"filtro de fecha",
    ),
    Surface(
        "audio-subtitulos",
        "el panel de Audio y subtítulos",
        "Panel de Audio y subtítulos",
        r"audio y subt[ií]tulos|panel de audio|subt[ií]tulos",
        _PLAYER_PRE,
        ('Seleccionar la opción "Audio y subtítulos" en el Control Player', "Se muestra el panel de Audio y subtítulos"),
        r"audio y subt[ií]tulos|panel de audio",
        r"(panel de )?audio y subt[ií]tulos",
    ),
    Surface(
        "pip",
        "la ventana PIP",
        "Ventana PIP",
        r"\bPIP\b|picture in picture",
        _PLAYER_PRE,
        ('Seleccionar la opción "PIP" en el Control Player', "La reproducción pasa a la ventana PIP"),
        r"\bpip\b|picture in picture",
        r"(la )?ventana (de )?pip",
    ),
    Surface(
        "volumen",
        "el control de volumen",
        "Control de volumen",
        r"control de volumen|\bvolumen\b",
        _PLAYER_PRE,
        ('Seleccionar la opción "Volumen" en el Control Player', "Se despliega el control de volumen"),
        r"volumen",
        r"(el )?control de volumen",
    ),
    Surface(
        "mas-info",
        'el panel "Más información"',
        "Panel Más información",
        r"m[aá]s info(rmaci[oó]n)?\b",
        _PLAYER_PRE,
        ('Seleccionar la opción "Más info" en el Control Player', 'Se muestra el panel "Más información"'),
        r"m[aá]s info",
        r"(el )?panel (de )?\W?m[aá]s informaci[oó]n\W?",
    ),
    Surface(
        "guia",
        "la Guía de programación",
        "Guía de programación",
        r"gu[ií]a de programaci[oó]n|\bgu[ií]a\b|celdas? de (eventos|canales)|timeline|barra lateral de navegaci",
        _PLAYER_PRE,
        ('Seleccionar la opción "Guía" en el Control Player', "Se muestra la Guía de programación"),
        r"\bgu[ií]a\b",
        r"(la )?\W?gu[ií]a( de programaci[oó]n)?\W?",
    ),
    Surface(
        "grabaciones",
        'el carrusel "Mis grabaciones"',
        "Mis grabaciones",
        r"mis grabaciones|grabaciones concluidas",
        "El usuario tiene al menos una grabación concluida",
        ("Ingresar a Mis contenidos > Mis grabaciones", 'Se muestra el carrusel "Mis grabaciones"'),
        r"mis grabaciones",
        r"mis grabaciones",
    ),
    Surface(
        "canal-bloqueado",
        'el modal "Canal bloqueado"',
        "Canal bloqueado",
        r"canal bloqueado",
        "El usuario tiene al menos un canal bloqueado con PIN",
        ("Sintonizar el canal bloqueado", 'Se muestra el modal "Canal bloqueado"'),
        r"sintoniz|canal bloqueado",
        r"(el )?modal .?canal bloqueado",
    ),
    Surface(
        "modal-grabacion",
        "el modal de grabación",
        "Modal de grabación",
        r"modal de grabaci[oó]n",
        "El usuario está en el Player de TV con un evento que permite grabación",
        ('Seleccionar la opción "Grabar"', "Se muestra el modal de grabación"),
        r"grabar",
        r"(el )?modal de grabaci[oó]n",
    ),
    Surface(
        "modal-eliminar-grabacion",
        "el modal de eliminación de grabación",
        "Modal de eliminación de grabación",
        r"modal de eliminaci[oó]n|eliminar esta grabaci[oó]n",
        "El usuario tiene al menos una grabación en Mis grabaciones",
        ('Seleccionar la opción "Eliminar grabación"', "Se muestra el modal de eliminación de grabación"),
        r"eliminar grabaci[oó]n",
        r"(el )?modal de eliminaci[oó]n",
    ),
    Surface(
        "player",
        "el Player de TV",
        "Player de TV",
        r"control player|player de tv|reproductor|progress ?bar|barra de progreso|botonera|chevr[oó]n|"
        r"timeshift|tag de temporalidad|controles de reproducci|metadata del evento|informaci[oó]n del evento|"
        r"cambio de canal|\bplayer\b",
        _PLAYER_PRE,
        _CP_STEP,
        r"cursor|hover|posicion",
        r"(el )?(control )?player( de tv)?|(el )?reproductor( de tv)?",
    ),
    Surface(
        "menu",
        "el Menú de navegación",
        "Menú de navegación",
        r"men[uú] de navegaci[oó]n|men[uú] principal|nodos? del men[uú]|\bmen[uú]\b",
        "El usuario está en el Home de Claro video",
        ("Abrir el Menú de navegación", "Se muestra el Menú de navegación"),
        r"men[uú]",
        r"(el )?men[uú]( de navegaci[oó]n)?",
    ),
    Surface(
        "telcel",
        "el flujo de registro Telcel",
        "Registro Telcel",
        r"telcel|c[oó]digo de vinculaci[oó]n|pantalla de vinculaci[oó]n",
        "El usuario anónimo está en la Landing de Claro video",
        ("Seleccionar el registro con Telcel", 'Se muestra la pantalla "Completa tu registro a Claro video" del flujo Telcel'),
        r"telcel",
        r"(la )?pantalla (del flujo telcel|de vinculaci[oó]n)",
    ),
    Surface(
        "home",
        "el Home",
        "Home",
        r"\bhome\b|nodo inicio",
        "El usuario está en el Home de Claro video",
        None,
        r"",
        r"(el )?home",
    ),
)

_BY_KEY = {surface.key: surface for surface in SURFACES}


def _fold(text: str | None) -> str:
    raw = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in raw if not unicodedata.combining(ch)).lower()


def _surfaces_in(text: str | None) -> list[Surface]:
    if not text:
        return []
    return [surface for surface in SURFACES if re.search(surface.match, text, re.I)]


def resolve_surface(*texts: str | None) -> Surface | None:
    """Superficie más específica del primer texto que nombra alguna (orden de SURFACES = especificidad)."""
    for text in texts:
        found = _surfaces_in(text)
        if found:
            return found[0]
    return None


def nav_target(action: str | None) -> Surface | None:
    """Si el paso es solo navegación ("Abrir/Ingresar <superficie>"), la superficie destino."""
    if not _NAV_VERB.match(action or ""):
        return None
    target = _NAV_VERB.sub("", action or "").strip(" .\"'")
    target = re.sub(r"^(el|la|los|las)\s+", "", target, flags=re.I)
    target = re.sub(r"\s+desde .*$", "", target, flags=re.I)
    if not target:
        return None
    for surface in SURFACES:
        pattern = surface.nav_alias or surface.match
        if re.fullmatch(rf"\W*(?:{pattern})\W*", target, re.I):
            return surface
    return None


def entry_chain(surface: Surface | None, via_guia: bool = False) -> list[tuple[str, str]]:
    """Pasos para llegar a la superficie desde su precondición."""
    if surface is None:
        return []
    if surface.precondition != _PLAYER_PRE:
        return [surface.entry] if surface.entry else []
    if surface.key == "player":
        return [_CP_STEP]
    if surface.key == "guia":
        return [_CP_STEP, _GUIA_STEP]
    if surface.key == "filtro-fecha":
        return [_CP_STEP, _GUIA_STEP, surface.entry]
    if surface.key == "mas-info" and via_guia:
        return [
            _CP_STEP,
            _GUIA_STEP,
            ('Seleccionar "Más info" en la celda de un evento', 'Se muestra el panel "Más información"'),
        ]
    return [_CP_STEP, surface.entry] if surface.entry else [_CP_STEP]


# --------------------------------------------------------------------------- limpieza de texto

_TECH_CLAUSE = re.compile(
    r"\bapa\b|\"apa|\bllaves?\b|\bfigma\b|\bdocumento\b|\bnode-|\?node|\benlace\b|unix ?time|"
    r"\bservicio\b|\bendpoint\b|\bapi\b|\bjson\b|\bpayload\b|\bresponse\b|\bkey_action\b|"
    r"\binsumos? de dise[nñ]o\b|\bse recupera\b|\brecupera del\b|\bla fuente debe\b|"
    r"\bprefijo\b|\bfunci[oó]n\b|\bcontrato\b|\bversi[oó]n instalada\b|\bm[eé]tricas?\b|"
    r"\bel defecto debe detectarse\b|\bno debe darse por correcta\b|\bpar[aá]metro\b|"
    r"^\s*(construcci[oó]n|implementaci[oó]n|implementar)\b",
    re.I,
)
# Única llave que el tester sí ve: el nombre de la llave pintado en lugar del texto.
_VISIBLE_KEY = re.compile(r"debe(n)? mostrarse la llave|mostrarse la llave como texto literal", re.I)
_TABLE_DUMP = re.compile(r"se muestra la pantalla con\s*:?|\bElemento,?\s+(Descripci[oó]n|Valor|Opci[oó]n)\b", re.I)
_TRUE_COND = re.compile(r"\bsi el valor r[e]?[c]?ibido es \W?(true|false)\W?\s*", re.I)
_JUNK_ACTION = re.compile(
    r"^\s*(abrir|ingresar( a)?)\s+(la\s+)?aplicaci[oó]n\s*$|"
    r"^\s*(abrir|ingresar( a)?)\s+(el|la)\s+(se |implementaci|implementar|construcci|nuevo |nueva )|"
    r"^\s*abrir el se muestra|^\s*implementar\b|^\s*construcci[oó]n\b|^\s*implementaci[oó]n\b|"
    r"^\s*mostrar la progress bar\s*$|^\s*se muestra el resultado de|"
    r"^\s*(abrir|ingresar( a)?)\s+(el|la)\s+usuario\b|^\s*(abrir|ingresar( a)?)\b.*\b(est[aá] visible|se encuentra)\b",
    re.I,
)
_NAV_VERB = re.compile(r"^\s*(abrir|ingresar|acceder|navegar|entrar)\b(\s+(a|al|a la|en))?\s*", re.I)
_EMPTY_EXPECTED = re.compile(r"^\s*(—|-|se muestra la pantalla con:?|se muestra el resultado de:?.*)?\s*$", re.I)


def _close_quotes(text: str) -> str:
    out = text.strip()
    if out.count('"') % 2:
        out = f'{out}"'
    if out.count("“") > out.count("”"):
        out = f"{out}”"
    return out


def _grammar(text: str) -> str:
    out = text
    out = re.sub(r"\bse debe de\b", "se debe", out, flags=re.I)
    out = re.sub(r"\bdeben de\b", "deben", out, flags=re.I)
    out = re.sub(r"\bdebe de\b", "debe", out, flags=re.I)
    out = re.sub(r"\bse cancelar\b", "se cancela", out, flags=re.I)
    out = re.sub(r"\bSebe\b", "Se debe", out)
    out = re.sub(r"\bsebe\b", "se debe", out)
    out = re.sub(r"\bMas informaci[oó]n\b", "Más información", out)
    out = re.sub(r"\bmas informaci[oó]n\b", "más información", out)
    out = re.sub(r"\b(\w+) (de )?(evento|del evento) del evento\b", r"\1 del evento", out, flags=re.I)
    out = re.sub(r"\binformaci[oó]n del evento de evento\b", "información del evento", out, flags=re.I)
    out = re.sub(r"\bla del evento\b", "la información del evento", out, flags=re.I)
    out = re.sub(r"\ben la del\b", "en la información del", out, flags=re.I)
    out = re.sub(r"\s+([,;.])", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip(" ;,")


def _cap(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:] if text else text


def _clauses(text: str | None) -> list[str]:
    raw = re.sub(r"^\s*\d+\.\s*", "", text or "")
    return [part.strip() for part in re.split(r";\s*|\n+", raw) if part.strip()]


def clean_expected(text: str | None) -> str:
    kept: list[str] = []
    for clause in _clauses(text):
        clause = _TRUE_COND.sub("", clause)
        if _VISIBLE_KEY.search(clause):
            kept.append("en el espacio del texto se muestra el nombre de la llave en lugar de la leyenda")
            continue
        if _TECH_CLAUSE.search(clause):
            continue
        if _TABLE_DUMP.search(clause):
            # Tabla de diseño volcada: se conserva la intención, no el volcado.
            kept.append("se muestran todos los elementos definidos para la pantalla")
            continue
        if _EMPTY_EXPECTED.match(clause):
            continue
        clause = _grammar(_close_quotes(clause))
        if len(clause) < 4:
            continue
        if _fold(clause) not in {_fold(k) for k in kept}:
            kept.append(clause)
    return _cap("; ".join(kept))


def clean_action(text: str | None) -> str:
    out = re.sub(r"^\s*\d+\.\s*", "", text or "").strip()
    out = re.sub(r"\bel usuario\s+(realice|realiza)\s+", "", out, flags=re.I)
    return _cap(_grammar(_close_quotes(out)))


_PRE_DROP = re.compile(
    r"\brequiere apoyo de dev\b|\bla fuente debe\b|\benlace\b|\bllaves?\b|\bapa\b|\bservicio\b|"
    r"\bprefijo\b|\bversi[oó]n instalada\b|\bfigma\b|\bconfiguraci[oó]n\b.*\b(remota|backend)\b",
    re.I,
)


# Cláusulas de navegación/estado de pantalla: las cubre la precondición de la superficie y los pasos.
_PRE_NAV = re.compile(
    r"\babiert[oa]s?\b|\bactiv[oa]\b|^\s*se (muestra|visualiza|despliega)|\bse encuentra en (el|la)\b|"
    r"\bse encuentra con el cursor|^\s*(el usuario )?(ingresa|ingresar|accede|abre|navega)\b|\bposicion|\bcursor\b|"
    r"^\s*la visualizaci[oó]n de|^\s*visualizaci[oó]n de|\bpantalla con\b|\bmediante el men[uú]\b|"
    r"\best[aá] (en|reproduciendo|visualizando|viendo)\b|\bse encuentra (viendo|reproduciendo|visualizando)\b|"
    r"^\s*ingreso al\b|\bdesplegad[oa]\b",
    re.I,
)


def clean_precondition(text: str | None, surface: Surface | None) -> str:
    kept: list[str] = []
    for clause in _clauses(text):
        clause = re.sub(r"^\s*(dado )?que\s+", "", clause, flags=re.I)
        if _PRE_DROP.search(clause) or _TABLE_DUMP.search(clause):
            continue
        if surface is not None and _PRE_NAV.search(clause):
            continue
        clause = _grammar(_close_quotes(clause))
        if len(clause) < 6:
            continue
        if _fold(clause) in {_fold(k) for k in kept}:
            continue
        kept.append(_cap(clause))
    if not kept and surface:
        kept.append(surface.precondition)
    return "; ".join(kept)


# --------------------------------------------------------------------------- nombres

_NAME_TECH = (
    (r"^valor(es)? de configuraci[oó]n ausente o vac[ií]o.*$", "{s}: texto no configurado no rompe el diseño"),
    (r"^valores no utilizables de la llave.*$", "{s}: valor no válido conserva el manejo de error"),
    (r"^(la )?llave no est[aá] cargada.*$", "{s}: texto no cargado no rompe el diseño"),
    (r"^los flujos vigentes conservan su llave.*$", "{s}: los demás flujos conservan sus textos"),
    (r"^(no|sin) regresi[oó]n(es)?\b.*$", "{s}: funciones existentes sin cambios"),
    (r"^reflejo correcto de configuraciones.*$", "{s}: opciones configuradas se muestran correctamente"),
    (r"^la respuesta del servicio llega incompleta.*$", "{s}: dato faltante no deja elementos vacíos"),
    (r"^el servicio responde con error.*$", "{s}: error al cargar conserva el manejo vigente"),
)
_NAME_LEAD = re.compile(
    r"^\s*(feature\s*:?\s*)?(implementar|implementaci[oó]n de(l| la| las| los)?|construcci[oó]n de(l| la| las| los)?)\s+",
    re.I,
)
_NAME_TECH_WORD = re.compile(r"\b(llaves?|apa|servicio|configuraci[oó]n|regresi[oó]n|figma|\(superficie\))\b", re.I)


def clean_name(name: str | None, surface: Surface | None) -> str:
    raw = (name or "").strip()
    base, _, suffix = raw.partition(" — ")
    base = base.strip()
    label = surface.short if surface else ""
    for pattern, template in _NAME_TECH:
        if re.match(pattern, base, re.I):
            base = template.format(s=label or "Aplicación")
            break
    else:
        if _NAME_LEAD.match(base):
            rest = _NAME_LEAD.sub("", base).strip()
            base = f"Visualización de {rest}" if rest else base
        base = re.sub(r"\(superficie\)", "", base, flags=re.I)
    base = _grammar(_close_quotes(base)).strip(" -—:")
    if suffix and label and label.lower() not in base.lower():
        base = f"{base} ({label})"
    return _cap(base)[:140]


# --------------------------------------------------------------------------- pasos


def _object_from_name(name: str, surface: Surface | None) -> str:
    text = re.sub(r"\s*\(.*\)\s*$", "", name or "").strip()
    text = re.sub(r"^[^:]+:\s*", "", text) if surface and text.lower().startswith(surface.short.lower()) else text
    text = re.sub(
        r"^(visualizaci[oó]n|estructura gr[aá]fica|posici[oó]n|mostrar|elementos|tiempo de visualizaci[oó]n|selecci[oó]n)\s+(de(l| la| las| los)?\s+)?",
        "",
        text,
        flags=re.I,
    )
    text = text.strip(' .')
    if text.count('"') % 2:
        text = text.replace('"', "")
    return text or (surface.label if surface else "la pantalla")


@dataclass
class _Step:
    action: str
    expected: str
    covered: list[str] = field(default_factory=list)


def rebuild_steps(
    case: GeneratedCaseCandidate, surface: Surface | None, name: str, via_guia: bool = False
) -> list[CandidateStep]:
    """Pasos con forma QC: entrada a la superficie + acciones reales + verificación."""
    loose: list[str] = []  # resultados que venían colgados de pasos basura
    loose_cov: list[str] = []
    steps: list[_Step] = []
    for step in case.steps:
        action = clean_action(step.action)
        expected = clean_expected(step.expected_result)
        covered = list(step.covered_unit_ids or [])
        if not action or _JUNK_ACTION.search(action) or nav_target(action) is not None:
            if expected and not re.match(r"^se (muestra|visualiza)\b.{0,60}$", expected, re.I):
                loose.append(expected)
            loose_cov.extend(covered)
            continue
        steps.append(_Step(action, expected, covered))

    chain = entry_chain(surface, via_guia)
    if surface and chain and steps and surface.entry_done and re.search(surface.entry_done, steps[0].action, re.I):
        chain = chain[:-1]  # la primera acción ya abre la superficie
    if chain and steps and re.search(r"cursor|hover|posicion", steps[0].action, re.I):
        chain = [c for c in chain if c != _CP_STEP]
    entry = [_Step(action, expected) for action, expected in chain]

    if loose:
        # Resultado sin acción propia: se verifica al llegar a la pantalla (sin pasos "Verificar ...").
        verify = "; ".join(dict.fromkeys(loose))
        if steps and not steps[-1].expected:
            steps[-1].expected = verify
            steps[-1].covered.extend(loose_cov)
        elif not steps and len(entry) == 1 and surface is not None:
            # Una sola entrada (p. ej. mostrar el Control Player): la revisión va en su propio paso.
            steps.append(_Step(f"Observar {_object_from_name(name, surface)}", verify, loose_cov))
        elif not steps and entry:
            entry[-1].expected = "; ".join(part for part in (entry[-1].expected, verify) if part)
            entry[-1].covered.extend(loose_cov)
        elif steps:
            steps[-1].expected = "; ".join(part for part in (steps[-1].expected, verify) if part)
            steps[-1].covered.extend(loose_cov)
        else:
            # Sin superficie conocida: el arranque de la app es la acción real.
            steps.append(_Step("Abrir la aplicación Claro video", verify, loose_cov))
    steps = entry + steps

    out: list[CandidateStep] = []
    seen: set[str] = set()
    for step in steps:
        key = _fold(f"{step.action}|{step.expected}")
        if key in seen:
            continue
        seen.add(key)
        out.append(
            CandidateStep(
                step_number=len(out) + 1,
                action=step.action,
                expected_result=clean_expected(step.expected) or "—",
                covered_unit_ids=list(dict.fromkeys(step.covered)),
            )
        )
    return out


# --------------------------------------------------------------------------- caso


def redactar(case: GeneratedCaseCandidate, context: str = "") -> GeneratedCaseCandidate:
    """Reescribe el caso con forma QC. `context` = escenario e historia de origen."""
    if not case.steps or "redaccion-qc" in (case.applied_rules or []) or case.generation_origin == "llm":
        return case
    navs = [nav_target(step.action) for step in case.steps]
    navs = [surface for surface in navs if surface is not None]
    via_guia = any(surface.key == "guia" for surface in navs) or bool(
        re.search(r"desde la celda|celda (del|de un) evento", f"{case.name} {context}", re.I)
    )
    candidates = [*_surfaces_in(case.name), *navs]
    surface = None
    for option in SURFACES:  # el más específico entre nombre y navegación
        if option in candidates:
            surface = option
            break
    surface = surface or resolve_surface(case.precondition, context, case.use_case_title, case.related_functionality)
    name = clean_name(case.name, surface)
    steps = rebuild_steps(case, surface, name, via_guia)
    if not steps:
        return case
    case.steps = steps
    case.name = name
    pre = clean_precondition(case.precondition, surface)
    if surface and surface.precondition and _fold(surface.precondition) not in _fold(pre):
        pre = "; ".join(part for part in (surface.precondition, pre) if part)
    case.precondition = pre or None
    case.applied_rules = list(dict.fromkeys([*(case.applied_rules or []), "redaccion-qc"]))
    return case


def unique_names(cases: list[GeneratedCaseCandidate]) -> list[GeneratedCaseCandidate]:
    """Nombres únicos dentro del release: agrega la historia solo si sigue repitiéndose."""
    counts: dict[str, int] = {}
    for case in cases:
        counts[_fold(case.name)] = counts.get(_fold(case.name), 0) + 1
    seen: dict[str, int] = {}
    for case in cases:
        key = _fold(case.name)
        if counts[key] < 2:
            continue
        seen[key] = seen.get(key, 0) + 1
        story = _NAME_LEAD.sub("", (case.use_case_title or "").strip()).strip(" .:-\"")
        story = " ".join(story.split()[:7])
        if story and _fold(story) not in _fold(case.name):
            case.name = f"{case.name} ({_grammar(_close_quotes(story))})"
        elif seen[key] > 1:
            case.name = f"{case.name} ({seen[key]})"
    return cases
