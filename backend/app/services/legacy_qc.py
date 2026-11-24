"""Reglas del motor legacy. No las usa v2 ni v2b.

El glosario vive en qc_glossary.json, al lado de este archivo.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_GLOSSARY_PATH = Path(__file__).with_name("qc_glossary.json")

_USER_VERBS = re.compile(
    r"\b(buscar|busca|seleccionar|selecciona|iniciar sesi[oó]n|inicia sesi[oó]n|"
    r"ingresar|ingresa|ingreso a|es dirigido|"
    r"registrarse|se registra|autenticarse|se autentica|"
    r"dar de alta|da de alta|da clic|hace clic|presiona|presionar|elegir|elige|"
    r"pulsar|pulsa|confirmar|confirma|cancelar|cancela|"
    r"acceder|accede|accionar|acciona|accione|al accionar|"
    r"identificar|identifico|identifica)\b",
    re.IGNORECASE,
)
_LEAD_ACTION = re.compile(
    r"^(?:abre|abrir|desplaza|desplazar|sintoniza|sintonizar|"
    r"navega|navegar|regresa|regresar|reproduce|reproducir)\b",
    re.IGNORECASE,
)
# Tercera persona, en cualquier conjugación, cuando el usuario es el sujeto.
# "se abre" no es una acción. "está" y "tiene" siguen siendo estado.
_ACTOR = r"(?:(?:el|la)\s+)?(?:usuari[oa]|suscriptor)"
_ACTION_VERB = (
    r"abre|abri[oó]|abrir|abra|"
    r"desplaza|desplazar|desplaz[oó]|"
    r"sintoniza|sintonizar|sintoniz[oó]|"
    r"selecciona|seleccionar|seleccion[oó]|seleccionaron|"
    r"ingresa|ingresar|ingres[oó]|ingresaron|"
    r"navega|navegar|naveg[oó]|"
    r"presiona|presionar|presion[oó]|"
    r"regresa|regresar|regres[oó]|"
    r"reproduce|reproducir|reproduj[oó]|"
    r"recorre|recorrer|recorri[oó]|"
    r"deja|dejar|dej[oó]|dejaron|"
    r"completa|completar|complet[oó]|completaron|"
    r"confirma|confirmar|confirm[oó]|"
    r"cancela|cancelar|cancel[oó]|"
    r"pulsa|pulsar|"
    r"elige|elegir|eligi[oó]|"
    r"accede|acceder|acced[aieoó]|"
    r"busca|buscar|"
    r"vuelve a abrir"
)
_USER_SUBJECT_VERB = re.compile(
    rf"\b{_ACTOR}\s+(?:no\s+)?(?:{_ACTION_VERB})\b",
    re.IGNORECASE,
)
# Conjugaciones que el motor viejo no movía a pasos. Llevan su propio resultado
# para no fundirse con la acción siguiente ni perderse.
_SETUP_CLAUSE = re.compile(
    rf"\b{_ACTOR}\s+(?:no\s+)?(?:"
    r"abri[oó]|desplaz[oó]|sintoniz[oó]|seleccion[oó]|ingres[oó]|naveg[oó]|"
    r"presion[oó]|regres[oó]|reproduj[oó]|recorri[oó]|dej[oó]|complet[oó]|"
    r"confirm[oó]|cancel[oó]|eligi[oó]|acced[aieoó]|"
    r"recorre|recorrer|deja|dejar|completa|completar|vuelve a abrir"
    r")\b",
    re.IGNORECASE,
)
_CONJUGATION = (
    (re.compile(r"\bseleccion[oó]\b", re.I), "selecciona"),
    (re.compile(r"\bingres[oó]\b", re.I), "ingresa"),
    (re.compile(r"\babri[oó]\b", re.I), "abre"),
    (re.compile(r"\bdej[oó]\b", re.I), "deja"),
    (re.compile(r"\bcomplet[oó]\b", re.I), "completa"),
    (re.compile(r"\bpresion[oó]\b", re.I), "presiona"),
    (re.compile(r"\bregres[oó]\b", re.I), "regresa"),
    (re.compile(r"\bnaveg[oó]\b", re.I), "navega"),
    (re.compile(r"\bsintoniz[oó]\b", re.I), "sintoniza"),
    (re.compile(r"\brecorri[oó]\b", re.I), "recorre"),
    (re.compile(r"\bconfirm[oó]\b", re.I), "confirma"),
    (re.compile(r"\bcancel[oó]\b", re.I), "cancela"),
    (re.compile(r"\beligi[oó]\b", re.I), "elige"),
    (re.compile(r"\bacced[aieoó]\b", re.I), "accede"),
    (re.compile(r"\breproduj[oó]\b", re.I), "reproduce"),
    (re.compile(r"\bvuelve a abrir\b", re.I), "abre"),
)
_SCREEN_ARRIVAL = re.compile(
    r"\bse presenta(?:n)?\s+(?:la\s+|el\s+|los\s+|las\s+)?(pantalla\b[^.;]*)",
    re.IGNORECASE,
)
_STATE = re.compile(
    r"\b(tiene sesi[oó]n|sin sesi[oó]n|est[aá] (logueado|registrado|suscrito)|"
    r"cuenta con|no cuenta con|tipo de usuario|suscripci[oó]n|m[eé]todo de pago|"
    r"usuario (an[oó]nimo|externo|registrado|suscrito))\b",
    re.IGNORECASE,
)
_TECH_PHRASE = re.compile(
    r"\bAPIs?\b|\bservicios?\b|\bendpoints?\b|\bpar[aá]metros?\b|\buser_hash\b|"
    r"\bmetadata\b|\bpayload\b|\bJSON\b|/services/|https?://|"
    r"\bstatus\s*codes?\b|\bc[oó]digos?\s+de\s+(respuesta|error)\b|"
    r"\bc[oó]digo\s+\d{3}\b|\bllave de configuraci[oó]n\b|\bimplementaci[oó]n\b|"
    r"\bse obtiene\b",
    re.IGNORECASE,
)
_KEY_TITLE = re.compile(
    r"llave (ausente|vac[ií]a|inexistente)|no se logra obtener una llave|"
    r"la llave se encuentra vac[ií]a|mediante la llave|"
    r"\b(configuraci[oó]n|metadata)\b",
    re.IGNORECASE,
)
# Aunque el Then diga que se conserva el comportamiento o que no se muestra el nombre.
_KEY_ABSENT = re.compile(
    r"\bllave\b[^\n]{0,80}\b(?:ausente|vac[ií]a|inexistente|no publicada|no configurada|"
    r"no cargada|no existe|devuelve vac[ií]o)\b"
    r"|\b(?:no publicada|no configurada|no cargada|ausente)\b[^\n]{0,50}\bllave\b"
    r"|\bllave\b[^\n]{0,40}\bno est[aá] (?:publicada|configurada|cargada)\b"
        r"|no se muestra el nombre de la llave"
        r"|nunca muestra el nombre de (?:su |la )?llave"
        r"|\bsin cargar\b[^\n]{0,40}\bllave\b"
        r"|\bllave\b[^\n]{0,40}\bsin cargar\b",
    re.IGNORECASE,
)
_RESULT_LEAD = re.compile(
    r"^(?:puede |se muestra\b|se presenta\b|se visualiza\b|no se muestra\b|no se presenta\b)",
    re.IGNORECASE,
)
_GHERKIN_WORD = re.compile(
    r"\b(?:given|when|then|and|but|dado|cuando|entonces|pero)\b[:\s]*",
    re.IGNORECASE,
)
_FROZEN_ONE_STEP = re.compile(
    r"^(?:seleccionar campo de entrada|"
    r"ingresar un n[uú]mero celular y seleccionar el bot[oó]n|"
    r"ingresar aplicaci[oó]n de claro video|"
    r"ingresar a la home|"
    r"identificar el men[uú] de navegaci[oó]n principal|"
    r"validar el espaciado entre dichos elementos|"
    r"ingresar home de inicio|"
    r"seleccionar el bot[oó]n «ver planes»)",
    re.IGNORECASE,
)
_VISIBLE_THEN = re.compile(
    r"se muestra|se visualiza|pantalla|modal|elementos|bot[oó]n|mensaje|"
    r"redirig|dirige|desplegad|replegad|ocult|ya no aparece|ya no es visible",
    re.IGNORECASE,
)
_THEN_TECH = re.compile(
    r"\b(API|servicio|par[aá]metro|user_hash|endpoint|se obtiene)\b",
    re.IGNORECASE,
)
# El Then depende de esto: el escenario pasa a verificación técnica.
# Si la frase solo está en el Given, se elimina de la precondición y el caso sigue.
_TECH_ACTOR = re.compile(
    r"\b(?:la aplicaci[oó]n|el sistema|el servicio|[A-Z]{2,10}CL)\s+"
    r"(?:obtiene|consulta|resuelve|inicializa)\b"
    r"|query\s*parameters?"
    r"|\barray\b"
    r"|\bprotocolos?\b"
    r"|/user/"
    r"|apa/assets"
    r"|apa/metadata"
    r"|\binsumo\b"
    r"|propiedad\s+enable"
    r"|\bappkey\b"
    r"|no se implementa"
    r"|no se reimplementa"
    r"|se revisa el cambio"
    r"|est[aá] documentad",
    re.IGNORECASE,
)
_NO_AFECTACION = re.compile(
    r"se ve[n]? igual que antes|mantener comportamiento actual|"
    r"no se (ve|ven) afect|sin afectaci[oó]n|no afectaci[oó]n|"
    r"no debe alterarse|no debe modificarse el comportamiento|"
    r"comportamiento funcional actual|mantener la estructura|"
    r"mantener estructura y comportamiento",
    re.IGNORECASE,
)
_PROCESS = re.compile(
    r"deben considerarse [uú]nicamente|ser[aá]n la referencia|"
    r"referencia oficial|conforme a dise[nñ]o oficial",
    re.IGNORECASE,
)
_THEN_LINE = re.compile(r"^\s*(Then|Entonces)\b(.*)$", re.IGNORECASE | re.MULTILINE)
_USER_KIND = re.compile(
    r"\b(usuario an[oó]nimo|usuario externo|usuario registrado|usuario suscrito|"
    r"usuario con sesi[oó]n|usuario sin sesi[oó]n|ip telmex|telmex)\b",
    re.IGNORECASE,
)
_BROKEN_QUOTE = re.compile(r"\"[^\"]*$|'[^']*$")
_DANGLING = re.compile(
    r"\b(de|del|la|el|los|las|y|a|en|con|para|por|un|una|que|se|al)$",
    re.IGNORECASE,
)
_MAIN_FLOW = re.compile(
    r"\b(alta|login|iniciar sesi[oó]n|compra|reproducci[oó]n|reproducir|checkout)\b",
    re.IGNORECASE,
)
_BUSINESS = re.compile(
    r"\b(mostrar|oculta|ocultar|se muestra|no se muestra|error|tipo de usuario)\b",
    re.IGNORECASE,
)
_VISUAL = re.compile(
    r"\b(texto|dise[nñ]o|espaciado|color|tipograf|conformidad visual|pixel|px)\b",
    re.IGNORECASE,
)
_ECHO = re.compile(
    r"^(se muestra un perfil|se muestra la pantalla de partida|—|-)$",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def glossary() -> dict[str, str]:
    raw = json.loads(_GLOSSARY_PATH.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in raw.items()}


def _compact(text: str) -> str:
    """EXTERNALREGISTER y EXTERNAL_REGISTER comparan igual."""
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def _glossary_hits(text: str) -> list[str]:
    blob = _compact(text)
    if not blob:
        return []
    hits: list[str] = []
    for key, value in sorted(glossary().items(), key=lambda item: len(_compact(item[0])), reverse=True):
        token = _compact(key)
        if token and token in blob:
            hits.append(value)
    return list(dict.fromkeys(hits))


def _unknown_user_codes(text: str) -> list[str]:
    found: list[str] = []
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_]{3,}\b", text or ""):
        letters = re.sub(r"[^A-Za-z]", "", token)
        if not letters or letters != letters.upper():
            continue
        compact = _compact(token)
        if not re.search(r"REGISTER|LOGIN", compact):
            continue
        if any(_compact(key) == compact or _compact(key) in compact or compact in _compact(key) for key in glossary()):
            continue
        found.append(token)
    return list(dict.fromkeys(found))


def gloss_precondition(text: str) -> tuple[str | None, list[str]]:
    """Traduce con el glosario. Un tipo de usuario sin traducción no se borra en silencio."""
    warnings: list[str] = []
    raw = text or ""
    hits = _glossary_hits(raw)
    unknown = _unknown_user_codes(raw)
    for token in unknown:
        warnings.append(f"tipo de usuario sin traducción: {token}")
    out = re.sub(r"[\"“”'`]", "", raw)
    out = re.sub(r"\s*=\s*", "=", out)
    if technical_phrase(out) or _TECH_PHRASE.search(out):
        warnings.append(re.sub(r"\s+", " ", out).strip()[:180])
        kept = list(hits)
        kept.extend(f"El usuario corresponde a {token}" for token in unknown)
        if kept:
            return "; ".join(dict.fromkeys(kept)), warnings
        return None, warnings
    if hits:
        return "; ".join(dict.fromkeys(hits)), warnings
    if unknown:
        return "; ".join(f"El usuario corresponde a {token}" for token in unknown), warnings
    stripped = re.sub(
        r"^(?:el |la |los |las )?usuarios? (?:es|son)\s+",
        "",
        out,
        flags=re.IGNORECASE,
    ).strip(" .")
    for value in glossary().values():
        if stripped.lower() == value.lower():
            return value, warnings
    cleaned = re.sub(r"\s+", " ", out).strip(" ;.")
    return (cleaned or None), warnings


def given_goes_to_step(text: str) -> bool:
    """Verbo de acción del usuario en el Given: pasa a Test Steps, no a precondición.

    Incluye la tercera persona ("el usuario abre") y "se presenta la pantalla".
    """
    if not text:
        return False
    if _SCREEN_ARRIVAL.search(text):
        return True
    if _USER_SUBJECT_VERB.search(text) or _LEAD_ACTION.search(text):
        return True
    if not _USER_VERBS.search(text):
        return False
    if _STATE.search(text) and not _USER_VERBS.search(text):
        return False
    return True


def legacy_disposition(title: str, body: str = "") -> tuple[str, str]:
    """caso | verificacion | regresion, y el motivo para el ledger."""
    blob = f"{title}\n{body}"
    then = " ".join(match.group(2) or "" for match in _THEN_LINE.finditer(body or ""))
    if _NO_AFECTACION.search(blob):
        return "regresion", "no afectación: lo cubre la regresión por componente"
    if _PROCESS.search(blob) and not _VISIBLE_THEN.search(then):
        return "nota", "criterio de proceso: no es un caso de prueba"
    if _KEY_TITLE.search(title or "") or _KEY_ABSENT.search(blob):
        return "verificacion", "llave ausente, no publicada o no cargada: no es caso QC"
    then_block_match = re.search(
        r"\b(?:then|entonces)\b(?P<rest>.*)\Z", body or "", re.IGNORECASE | re.DOTALL
    )
    then_block = then_block_match.group("rest") if then_block_match else then
    if (_THEN_TECH.search(then_block) or _TECH_ACTOR.search(then_block)) and not _VISIBLE_THEN.search(then_block):
        return "verificacion", "el Then menciona API, servicio, parámetro o endpoint"
    if (
        _TECH_ACTOR.search(blob)
        and re.search(r"\bla aplicaci[oó]n\b", then_block, re.IGNORECASE)
        and not _VISIBLE_THEN.search(then_block)
    ):
        return "verificacion", "el Then depende de un comportamiento técnico de la aplicación"
    return "caso", ""


def bare_scenario_name(title: str) -> str:
    text = _USER_KIND.sub(" ", title or "")
    text = re.sub(r"[^0-9A-Za-zÁÉÍÓÚáéíóúÑñ ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def same_repeated_scenario(left_title: str, right_title: str, left_then: str, right_then: str) -> bool:
    """Mismo comportamiento en historias distintas: solo cambia el tipo de usuario."""
    if not bare_scenario_name(left_title) or bare_scenario_name(left_title) != bare_scenario_name(right_title):
        return False
    return _norm(left_then) == _norm(right_then) and bool(_norm(left_then) or _norm(left_title))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _clip_words(text: str, limit: int) -> str:
    words = [word for word in re.split(r"\s+", (text or "").strip()) if word][:limit]
    while words and words[-1].lower() in {
        "de", "del", "la", "el", "los", "las", "y", "a", "en", "con", "para", "por", "un", "una", "que", "se", "al",
    }:
        words.pop()
    return " ".join(words).strip(" ;.")


def clean_title(title: str, user: str = "", action: str = "", result: str = "") -> str:
    """El título es el nombre del escenario. No se arma con los pasos."""
    del user, action, result
    raw = _strip_md(title or "")
    text = _BROKEN_QUOTE.sub("", raw)
    text = re.sub(r"[\"“”']", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -:")
    while _DANGLING.search(text):
        text = _DANGLING.sub("", text).strip(" -:")
    return _at_word(text, 180) or "Caso QC"


def classify_legacy_priority(title: str, steps_blob: str) -> str:
    blob = f"{title}\n{steps_blob}"
    if _MAIN_FLOW.search(blob):
        return "BLOCKER"
    if _VISUAL.search(blob) and not _BUSINESS.search(blob):
        return "MAJOR"
    return "CRITICAL"


def is_echo_result(action: str, expected: str) -> bool:
    left = _norm(re.sub(r"^\s*\d+\.\s*", "", action or ""))
    right = _norm(re.sub(r"^\s*\d+\.\s*", "", expected or ""))
    if not right or right in {"—", "-", "se muestra un perfil"}:
        return True
    if _ECHO.match(right):
        return True
    return bool(left and right and (left[:40] == right[:40] or left == right))


_PHRASE_TECH = re.compile(
    r"\bpar[aá]metros?\b|\bbody\b|\benable\b|\b(true|false)\b|\bgroup\s*id\b|"
    r"\bpropiedad(es)?\b|\bvalor a\b|\blista\s*\[\]|\[\]|\bse obtiene[n]?\b|"
    r"\bAPIs?\b|\bservicios?\b|\bendpoints?\b|/services/|https?://|\bfigma\b|"
    r"\bstatus\s*codes?\b|\bllave de configuraci[oó]n\b",
    re.IGNORECASE,
)
_ENTRY_STEP = re.compile(
    r"^(abrir|ingresar|acceder|entrar|navegar)\b.{0,40}\b("
    r"aplicaci[oó]n|home|nodo de inicio|pantalla de inicio|pantalla principal)\b",
    re.IGNORECASE,
)
_FILLER_ACTION = re.compile(r"^verificar lo que muestra\b", re.IGNORECASE)
_FILLER_RESULT = re.compile(r"^se muestra la pantalla\.?$", re.IGNORECASE)
_ANON = re.compile(
    r"an[oó]nim|sin sesi[oó]n|no (est[aá] )?(registrado|logueado)|usuario no registrado",
    re.IGNORECASE,
)
_AUTH = re.compile(
    r"autentific|autenticad|sesi[oó]n iniciada|est[aá] logueado|"
    r"m[eé]todo de pago|suscrip",
    re.IGNORECASE,
)
_FIRST_PERSON = re.compile(r"\b(yo|estoy|soy|nosotros|mi)\b", re.IGNORECASE)
_STOP = {
    "para", "como", "esta", "este", "esto", "desde", "donde", "cuando", "sobre",
    "tiene", "tener", "haber", "debe", "deben", "sera", "esta", "estan",
    "usuario", "contenido", "plataforma", "claro", "video",
}


def _at_word(text: str, limit: int) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if len(raw) <= limit:
        return raw
    cut = raw[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.strip(" -:")


def fold(text: str) -> str:
    table = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    return re.sub(r"\s+", " ", (text or "").translate(table)).strip().lower()


def technical_phrase(text: str) -> bool:
    return bool(_PHRASE_TECH.search(text or "") or _TECH_ACTOR.search(text or ""))


def _strip_md(text: str) -> str:
    """Quita negritas y código. No borra máscaras de dígitos como ****3456."""
    out = re.sub(r"`([^`]*)`", r"\1", text or "")
    out = re.sub(r"\*\*([^*]+)\*\*", r"\1", out)
    return re.sub(r"\s+", " ", out).strip()


def _without_tech_clauses(text: str) -> str:
    parts = re.split(r"\s*;\s*|(?<=\.)\s+", text or "")
    kept = [part.strip(" .") for part in parts if part.strip(" .") and not technical_phrase(part)]
    return ". ".join(kept)


def third_person(text: str) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip())
    raw = re.sub(r"\bque tengo\b", "el usuario tiene", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\bme encuentro\b", "el usuario se encuentra", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\bidentifico\b", "el usuario identifica", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\bconsulto\b", "el usuario consulta", raw, flags=re.IGNORECASE)
    raw = _FIRST_PERSON.sub("el usuario", raw)
    raw = re.sub(r"^ingreso\b", "El usuario ingresa", raw, flags=re.IGNORECASE)
    if re.match(r"^(se |no se |al |ocurre\b|existe\b)", raw, re.I):
        if raw[0].islower():
            raw = raw[0].upper() + raw[1:]
        if not raw.endswith("."):
            raw += "."
        return raw
    if raw and not re.match(r"^(el |la |los |las )", raw, re.I):
        if re.match(r"^(est[aá]|tiene|cuenta|se encuentra|no se|no tiene)\b", raw, re.I):
            raw = "El usuario " + raw[0].lower() + raw[1:]
    if raw and raw[0].islower():
        raw = raw[0].upper() + raw[1:]
    if raw and not raw.endswith("."):
        raw += "."
    return raw


def scenario_stance(title: str, body: str) -> tuple[bool, bool]:
    blob = f"{title}\n{body}"
    return bool(_ANON.search(blob)), bool(_AUTH.search(blob))


def background_contradicts(clause: str, anon: bool, auth: bool) -> bool:
    """Si el Background contradice al escenario, gana el escenario."""
    if auth and not anon and _ANON.search(clause or ""):
        return True
    if anon and not auth and _AUTH.search(clause or ""):
        return True
    return False


def is_entry_action(action: str) -> bool:
    return bool(_ENTRY_STEP.search(action or ""))


def is_filler_step(action: str, expected: str) -> bool:
    if _FILLER_ACTION.search(action or ""):
        return True
    return bool(_FILLER_RESULT.match((expected or "").strip())) and not (action or "").strip()


def _attach_tables(body: str) -> str:
    """Pega la tabla de la frase al paso que la introduce, fila por fila."""
    lines: list[str] = []
    pending: list[str] = []
    in_doc = False

    def flush() -> None:
        if pending and lines:
            lines[-1] = f"{lines[-1].rstrip()} || {' || '.join(pending)}"
        pending.clear()

    for raw in (body or "").splitlines():
        stripped = raw.strip()
        if in_doc:
            if stripped in {'"""', "'''"}:
                in_doc = False
            continue
        if stripped in {'"""', "'''"}:
            in_doc = True
            continue
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            cells = [cell for cell in cells if cell and not re.fullmatch(r"[-: ]+", cell)]
            if cells:
                pending.append(" | ".join(cells))
            continue
        flush()
        lines.append(raw)
    flush()
    return "\n".join(lines)


_ELEMENT_LABEL = re.compile(
    r"(?:^|\s)("
    r"Elementos?|Assets?|Textos?|Bot[oó]n(?:es)?|Logos?|T[ií]tulos?|Inputs?|"
    r"Chevr[oó]n(?:es)?|Alertas?|[IÍ]conos?|Overlays?|Im[aá]genes?"
    r")([^,]{0,40}?)\s*,\s*"
)
_OUTCOME = re.compile(
    r"^(no se tiene|se valida|se mantiene|queda asociado|ocurre un error)\b",
    re.IGNORECASE,
)


def _listed_pairs(data: str) -> list[tuple[str, str]]:
    """Parte 'Etiqueta, valor Etiqueta, valor' usando las etiquetas de la tabla."""
    pairs: list[tuple[str, str]] = []
    pos = 0
    if not _ELEMENT_LABEL.match(data):
        free = re.match(r"([^,]{2,60}?)\s*,\s*", data)
        if free:
            nxt = _ELEMENT_LABEL.search(data, free.end())
            value = data[free.end() : nxt.start() if nxt else None].strip(" .")
            if value:
                pairs.append((free.group(1).strip(), value))
            pos = nxt.start() if nxt else len(data)
    while pos < len(data):
        match = _ELEMENT_LABEL.search(data, pos)
        if not match:
            break
        label = f"{match.group(1)}{match.group(2)}".strip()
        nxt = _ELEMENT_LABEL.search(data, match.end())
        value = data[match.end() : nxt.start() if nxt else None].strip(" .")
        if value and fold(label) not in {"elemento", "elementos", "descripcion"}:
            pairs.append((label, value))
        pos = nxt.start() if nxt else len(data)
    return pairs


def readable_elements(text: str) -> str:
    """Tabla Elementos | Descripción → lista legible."""
    raw = re.sub(r"\s+", " ", text or "").strip()
    if "||" in raw and re.search(r"elemento", raw, re.I):
        rows = []
        for chunk in raw.split("||"):
            if "|" not in chunk:
                continue
            cells = [cell.strip() for cell in chunk.split("|")]
            cells = [cell for cell in cells if cell]
            if cells:
                rows.append(cells)
        if len(rows) >= 2:
            items = _element_items(rows[0], rows[1:])
            if items:
                return "Se muestran: " + ", ".join(items) + "."
    marker = re.search(r"elementos?\s*,\s*descripci[oó]n\s*", raw, re.I)
    if not marker:
        return ""
    pairs = _listed_pairs(raw[marker.end() :])
    items = [_element_phrase(label, value) for label, value in pairs]
    if not items:
        return ""
    return "Se muestran: " + ", ".join(items) + "."


def _element_items(headers: list[str], rows: list[list[str]]) -> list[str]:
    label_at = 0
    value_at = 1 if len(headers) > 1 else 0
    items = []
    for row in rows:
        label = row[label_at] if label_at < len(row) else ""
        value = row[value_at] if value_at < len(row) else ""
        if label and value:
            items.append(_element_phrase(label, value))
    return items


def _element_phrase(label: str, value: str) -> str:
    low = fold(label)
    if low.startswith("texto"):
        return f"texto «{value}»"
    if low.startswith("bot"):
        return f"botón «{value}»"
    if "logo" in low:
        if fold(value).startswith("logo"):
            return value[0].lower() + value[1:]
        return f"logo de {value}"
    if low.startswith("asset") or "icono" in fold(value):
        return value[0].lower() + value[1:] if value else value
    return f"{label[:1].lower() + label[1:]} «{value}»"


def _walk(body: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    kind = "given"
    for line in _attach_tables(body or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if re.match(r"^(Feature|Background|Scenario|Escenario|Examples|Ejemplos)\b", line, re.I):
            kind = "given"
            continue
        if re.match(r"^(Given|Dado)\b", line, re.I):
            kind = "given"
            line = re.sub(r"^(Given|Dado que|Dado)\s+", "", line, flags=re.I)
        elif re.match(r"^(When|Cuando)\b", line, re.I):
            kind = "when"
            line = re.sub(r"^(When|Cuando)\s+", "", line, flags=re.I)
        elif re.match(r"^(Then|Entonces)\b", line, re.I):
            kind = "then"
            line = re.sub(r"^(Then|Entonces)\s+", "", line, flags=re.I)
        elif re.match(r"^(And|Y|But|Pero)\b", line, re.I):
            line = re.sub(r"^(And|Y|But|Pero)\s+", "", line, flags=re.I)
        else:
            continue
        line = line.strip()
        if not line:
            continue
        pieces = _split_action_clauses(line) if kind != "then" else [line]
        for piece in pieces:
            if piece:
                rows.append((kind, piece))
    return rows


def _split_action_clauses(text: str) -> list[str]:
    """Parte 'el usuario abre X y el usuario selecciona Y' en acciones ordenadas."""
    parts = re.split(
        r"\s+y\s+(?=(?:(?:el|la)\s+)?(?:usuari[oa]|suscriptor)\b|se presenta\b|"
        r"(?:seleccion|ingres|abr|dej|complet|presion|regres|naveg|sintoniz|"
        r"recorr|confirm|reprodu|vuelve)\w*)",
        text or "",
        flags=re.IGNORECASE,
    )
    return [part.strip(" .") for part in parts if part.strip(" .")]


_KEY_STATE = re.compile(
    r"valor de la llave|llave de configuraci[oó]n|\bllave\b[^.]{0,40}\bindica|"
    r"mediante la llave|home_cdn_config",
    re.IGNORECASE,
)
_ERROR_CODE = re.compile(
    r"\bPGS_[A-Z0-9_]+\b|la respuesta contiene|c[oó]digo de error|"
    r"\bcode distinto\b|status code",
    re.IGNORECASE,
)
_VISIBLE_ASSERT = re.compile(
    r"distancia|componente|se muestra|pantalla|modal|bot[oó]n|elemento|"
    r"overlay|[ií]cono|alerta|redirig|dirige|mensaje|texto|espaciado|"
    r"desplegad|replegad|ocult|ya no aparece",
    re.IGNORECASE,
)
_OBSERVABLE = re.compile(
    r"se muestra|se visualiza|muestra la pantalla|pantalla de|"
    r"se redirige|es dirigido|se dirige|dirige al|"
    r"desplegad|replegad|debe ocultarse|se oculta|oculto|"
    r"ya no aparece|ya no es visible|modal",
    re.IGNORECASE,
)
_TEMPORAL = re.compile(r"^al (finalizar|terminar|concluir|cerrar el tiempo)\b", re.IGNORECASE)
_ENABLED = "La funcionalidad está habilitada para la operación del usuario."
_JUNK_PRE = re.compile(r"^(y|and)\.?$", re.IGNORECASE)


def visible_remainder(text: str) -> str:
    """Quita la referencia técnica y conserva la afirmación visible."""
    raw = re.sub(r"\s+", " ", text or "").strip()
    if not raw:
        return ""
    cleaned = re.sub(r"https?://\S+", " ", raw)
    cleaned = re.sub(r"\b(en\s+)?figma\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;.")
    if _ERROR_CODE.search(cleaned) and not _VISIBLE_ASSERT.search(cleaned):
        return ""
    if _KEY_STATE.search(cleaned) and not _VISIBLE_ASSERT.search(cleaned):
        return ""
    if technical_phrase(cleaned):
        return ""
    if technical_phrase(raw) and not _VISIBLE_ASSERT.search(cleaned):
        return ""
    return cleaned


def _named_button(text: str, history: list[str]) -> str:
    quoted = re.search(r"[\"“]([^\"”]+)[\"”]", text or "")
    if quoted and not re.search(r"accionable", quoted.group(1), re.I):
        if re.search(r"bot[oó]n", text or "", re.I):
            return quoted.group(1).strip()
    if re.search(r"bot[oó]n accionable", text or "", re.I):
        for prev in reversed(history):
            match = re.search(
                r"bot[oó]n accionable(?:\s*\d+)?\s*[\"“]([^\"”]+)[\"”]",
                prev,
                re.I,
            )
            if match:
                return match.group(1).strip()
    return ""


def _setup_result(text: str) -> str:
    line = re.sub(
        r"^(?:and|y|given|dado que|dado|when|cuando)\s+",
        "",
        text or "",
        flags=re.IGNORECASE,
    ).strip(" .")
    if not line:
        return "Queda hecha la acción."
    line = line[0].upper() + line[1:]
    if not line.endswith("."):
        line += "."
    return f"Queda hecha la acción: {line}"


def _audio_panel(text: str) -> list[dict[str, object]]:
    """El criterio de audio y subtítulo son dos acciones, no una comprobación."""
    match = re.search(
        r"acced\w*\s+al\s+(panel de audio y subt[ií]tulos).{0,160}?cambiar el (audio|subt[ií]tulo)",
        text or "",
        re.IGNORECASE,
    )
    if not match:
        return []
    panel = re.sub(r"\s+", " ", match.group(1)).strip()
    kinds = list(
        dict.fromkeys(re.findall(r"cambiar el (audio|subt[ií]tulo)", text or "", re.IGNORECASE))
    ) or [match.group(2)]
    rows: list[dict[str, object]] = [
        {
            "action": f"Acceder al {panel}",
            "results": ["Se muestra el panel de audio y subtítulos."],
        }
    ]
    for what in kinds:
        rows.append(
            {
                "action": f"Cambiar el {what} del contenido en reproducción",
                "results": [f"El contenido en reproducción usa el {what} elegido."],
            }
        )
    return rows


def _user_action(text: str, history: list[str] | None = None) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw or (technical_phrase(raw) and not visible_remainder(raw)):
        return ""
    actionable = given_goes_to_step(raw)
    arrival = _SCREEN_ARRIVAL.search(raw)
    if arrival:
        dest = re.sub(r"\s+", " ", arrival.group(1)).strip(" .")
        return f"Ingresar a la {dest}"
    for pattern, replacement in _CONJUGATION:
        raw = pattern.sub(replacement, raw)
    raw = re.sub(
        rf"^(?:.*?)\b({_ACTOR}\s+(?:no\s+)?(?:{_ACTION_VERB})\b)",
        r"\1",
        raw,
        count=1,
        flags=re.IGNORECASE,
    )
    raw = re.sub(rf"^{_ACTOR}\s+", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^(que\s+)?identifico\b", "identificar", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^(que\s+)?consulto\b", "consultar", raw, flags=re.IGNORECASE)
    raw = re.sub(r"^(que\s+)?valido\b", "validar", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\baccede\b", "acceder", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\baccione\b", "accionar", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\bacciona\b", "accionar", raw, flags=re.IGNORECASE)
    if re.match(r"^me encuentro\b", raw, re.I):
        return ""
    if _DEV_OR_CODE.search(raw):
        return ""
    if re.search(r"comienza a corregir", raw, re.I):
        return "Corregir el número ingresado"
    if re.search(r"\bal ser accionado\b", raw, re.I):
        return ""
    if not actionable and not given_goes_to_step(raw) and not re.search(
        r"\b(identificar|consultar|validar)\b", raw, re.I
    ):
        return ""
    if re.search(r"\bse autentica\b", raw, re.I):
        rest = re.sub(r"^.*\bse autentica\b", "", raw, flags=re.IGNORECASE).strip()
        return re.sub(r"\s+", " ", f"Autenticarse {rest}").strip()
    button = _named_button(raw, history or [])
    if button and re.search(r"seleccion|clic|presion|accion", raw, re.I):
        return f"Seleccionar el botón «{button}»"
    quoted = re.search(r"[\"“]([^\"”]+)[\"”]", raw)
    if quoted and re.search(r"bot[oó]n", raw, re.I):
        return f"Seleccionar el botón «{quoted.group(1).strip()}»"
    if quoted and re.search(r"seleccion|clic|presion|accion", raw, re.I):
        return f"Seleccionar «{quoted.group(1).strip()}»"
    from app.services.case_composer import to_infinitive

    action = to_infinitive(raw) or raw
    action = re.sub(r"^ingreso\b", "Ingresar", action, flags=re.IGNORECASE)
    action = re.sub(r"\bbot[oó]n accionable(?:\s*\d+)?\b", "el botón", action, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", action).strip()


def _embedded_press(text: str) -> tuple[str, str]:
    if not re.search(r"\b(al presionar|presionar|presiona|da clic|hace clic)\b", text or "", re.I):
        return "", ""
    if re.search(r"\bal ser accionado\b", text or "", re.I):
        return "", ""
    if not re.search(r"se muestra|se redirige|se dirige", text or "", re.I):
        return "", ""
    quoted = re.search(r"[\"“]([^\"”]+)[\"”]", text or "")
    name = quoted.group(1).strip() if quoted else ""
    if not name:
        match = re.search(r"bot[oó]n\s+([A-Za-zÁÉÍÓÚáéíóúñÑ0-9]+)", text or "")
        name = match.group(1) if match else ""
    verb = "Presionar" if re.search(r"presion", text or "", re.I) else "Seleccionar"
    shown = re.search(r"(se muestra\s+.+|se redirige\s+.+|se dirige\s+.+)$", text or "", re.I)
    result = shown.group(1).strip() if shown else ""
    if name and re.search(r"bot[oó]n", text or "", re.I):
        return f"{verb} el botón «{name}»", result
    return f"{verb} {name or 'el control indicado'}".strip(), result


def echo_pair(action: str, expected: str) -> bool:
    """Seleccionar X → Se muestra X, o un resultado que repite la acción."""
    folded_expected = fold(expected)
    folded_action = fold(action)
    if not folded_expected:
        return True
    if re.match(r"^se muestra se\b", folded_expected):
        return True
    shown = re.sub(r"^se muestra\s+", "", folded_expected).strip(" .«»\"")
    if shown and shown == folded_action:
        return True
    match = re.match(
        r"^(seleccionar|presionar|dar clic en)\s+(el boton\s+|la\s+|el\s+|un\s+|una\s+)?(.+)$",
        folded_action,
    )
    target = ""
    if match:
        target = match.group(3).strip(" .«»\"")
    quoted = re.search(r"«([^»]+)»", action or "")
    if quoted:
        target = fold(quoted.group(1))
    if target and shown in {target, f"el {target}", f"la {target}", f"un {target}", f"una {target}"}:
        return True
    return False


_FILLER_EXPECTED = re.compile(
    r"la pantalla queda en el estado siguiente|queda seleccionado|queda realizada la selecci",
    re.IGNORECASE,
)
_DEV_OR_CODE = re.compile(
    r"\bse implementan\b|\bse realiza la actualizaci[oó]n\b|\bc[oó]digo\s*200\b|\bcode\s*200\b",
    re.IGNORECASE,
)
_GHERKIN_LEAD = re.compile(
    r"^(and|y|given|dado que|dado|when|cuando|then|entonces)\b[:\s]*",
    re.IGNORECASE,
)


def then_has_visible_outcome(body: str) -> bool:
    """El Then se ve en pantalla: navegación, estado o elemento. Si no, no es caso."""
    then = " ".join(match.group(2) or "" for match in _THEN_LINE.finditer(body or ""))
    return bool(_VISIBLE_THEN.search(then))


def _observable_clause(text: str) -> bool:
    return bool(_OBSERVABLE.search(text or ""))


def is_entry_flow(action: str) -> bool:
    """Abrir la app, autenticarse o elegir perfil: cada uno es un paso."""
    low = fold(action)
    if re.search(r"^(ingresar|abrir|acceder|entrar)\b", low) and re.search(
        r"aplicaci|claro video|home\b|nodo", low
    ):
        return True
    if re.search(r"^autentic", low):
        return True
    if re.search(r"seleccionar (un )?perfil", low):
        return True
    return False


_KEEP_RESULT = re.compile(
    r"redirig|dirige|desplegad|replegad|ocult|ya no aparece|ya no es visible|"
    r"pantalla de perfiles|pantalla de ingreso|pantalla de checkout|modal",
    re.IGNORECASE,
)


def is_filler_expected(action: str, expected: str) -> bool:
    """Resultado inventado: no está en el Gherkin."""
    folded = fold(expected)
    if not folded:
        return True
    if _KEEP_RESULT.search(expected) and not echo_pair(action, expected):
        return False
    if re.search(r"^(ingresar|acceder|abrir|entrar)\b", fold(action)) and re.search(
        r"\bpantalla\b|\bhome\b|\bnodo\b", fold(expected)
    ):
        return False
    if _FILLER_EXPECTED.search(folded):
        return True
    if echo_pair(action, expected):
        return True
    shown = re.sub(r"^se muestra\s+", "", folded).strip(" .«»\"")
    act = re.sub(
        r"^(ingresar|acceder|abrir|buscar|seleccionar|presionar)( a| al| el boton| el)?\s+",
        "",
        fold(action),
    ).strip(" .«»\"")
    if shown and act and shown == act:
        return True
    folded = re.sub(r"\bel usuario\b", " ", folded)
    words = [word for word in re.findall(r"[a-z0-9]{4,}", folded) if word not in _STOP and word != "usuario"]
    if words and len(words) <= 6 and all(word[:5] in fold(action) for word in words):
        return True
    return False


def _account_lines(title: str, body: str) -> list[str]:
    blob = f"{title}\n{body}"
    lines: list[str] = []
    if re.search(r"sin suscripciones", blob, re.I):
        lines.append("El usuario no tiene suscripciones asociadas al método de pago.")
    if re.search(r"con suscripciones asociadas", blob, re.I):
        lines.append("El usuario tiene suscripciones asociadas al método de pago.")
    if re.search(r"no cuenta con un n[uú]mero|sin (un )?m[eé]todo de pago registrado", blob, re.I):
        lines.append("El usuario no tiene un método de pago registrado.")
    if re.search(r"cuenta con un n[uú]mero|tiene un m[eé]todo de pago registrado", blob, re.I):
        lines.append("El usuario tiene un método de pago registrado.")
    if re.search(r"sesi[oó]n iniciada|tiene sesi[oó]n", blob, re.I):
        lines.append("El usuario tiene la sesión iniciada.")
    if re.search(r"gesti[oó]n de m[eé]todos de pago|consulta de n[uú]mero|eliminar el m[eé]todo", blob, re.I):
        if not re.search(
            r"no cuenta con un n[uú]mero|sin (un )?m[eé]todo de pago registrado|no tiene un m[eé]todo",
            blob,
            re.I,
        ):
            lines.append("El usuario tiene un método de pago registrado.")
    return lines


def _visible_removal(text: str) -> str:
    if not re.search(r"proceder con la eliminaci[oó]n|queda eliminad", text or "", re.I):
        return text
    match = re.search(r"[\"“]([^\"”]+)[\"”]", text or "")
    if not match:
        match = re.search(r"m[eé]todo de pago\s+([A-Za-zÁÉÍÓÚáéíóúñÑ0-9]+)", text or "", re.I)
    name = match.group(1).strip() if match else ""
    if not name:
        return text
    return f"Se procede con la eliminación del método de pago «{name}» y ya no aparece."


def _fallback_result(action: str) -> str:
    if re.search(r"^seleccionar|^presionar", action or "", re.I):
        match = re.search(r"«([^»]+)»", action or "")
        target = match.group(1) if match else re.sub(
            r"^(Seleccionar|Presionar)(?: el botón)?\s+", "", action or "", flags=re.I
        )
        target = target.strip(" «».")
        return f"Queda seleccionado «{target}»." if target else "Queda realizada la selección."
    if re.search(r"^(ingresar|abrir|acceder)", action or "", re.I):
        dest = re.sub(r"^(Ingresar|Abrir|Acceder)(?: a| al)?\s+", "", action or "", flags=re.I).strip()
        if dest:
            return f"Se muestra {dest}."
    if re.search(r"^autenticarse", action or "", re.I):
        return "El usuario queda autenticado."
    if re.search(r"^identificar", action or "", re.I):
        return "Quedan identificados los elementos de la pantalla."
    return "La pantalla queda en el estado siguiente."


def _join_results(parts: list[str]) -> str:
    merged: list[str] = []
    pending = False
    for part in parts:
        piece = visible_remainder(part) or re.sub(r"\s+", " ", part).strip()
        if not piece or (_ERROR_CODE.search(piece) and not _VISIBLE_ASSERT.search(piece)):
            continue
        if _TEMPORAL.match(piece):
            pending = True
            continue
        sentence = _sentence(_visible_removal(piece))
        if pending and sentence:
            body = sentence[0].lower() + sentence[1:]
            sentence = f"Al terminar el tiempo del modal, {body}"
            pending = False
        if sentence:
            merged.append(sentence)
    if pending:
        merged.append("Al terminar el tiempo del modal.")
    return " ".join(merged)


def _arrival(action: str) -> str:
    dest = re.sub(
        r"^(buscar|seleccionar|ingresar a|ingresar|abrir|dar clic en|acceder a)\s+",
        "",
        action or "",
        count=1,
        flags=re.IGNORECASE,
    ).strip(" .\"")
    if re.search(r"\bperfil\b", dest or "", re.I):
        return "Se muestra el perfil elegido."
    if not dest or re.fullmatch(r"(la |el |un |una )?(pantalla|aplicaci[oó]n)", dest, re.I):
        return "Se muestra el destino de la acción."
    return f"Se muestra {dest}."


def _sentence(text: str) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip())
    if not raw:
        return ""
    # Un Scenario Outline "Then se aplica <resultado>" pega el verbo al valor del ejemplo.
    raw = re.sub(
        r"^(?:se aplica|el resultado es)\s+[\"“”']*((?:no\s+)?se\b[^\"“”']*)[\"“”']*$",
        r"\1",
        raw,
        count=1,
        flags=re.IGNORECASE,
    )
    raw = raw[0].upper() + raw[1:]
    if raw[-1] not in ".!?":
        raw += "."
    return raw


def _event_step(clause: str) -> tuple[str, str]:
    listed = readable_elements(clause)
    if listed:
        return "Verificar los elementos de la pantalla", listed
    low = fold(clause)
    expected = _sentence(clause)
    if re.search(r"da clic|hace clic|presiona|presionar", clause or "", re.I):
        quoted = re.search(r"[\"“]([^\"”]+)[\"”]", clause or "")
        button = re.search(r"bot[oó]n\s+[\"“]?([^\"”,.]+)", clause or "", re.I)
        target = (quoted.group(1) if quoted else (button.group(1).strip() if button else "el control indicado"))
        verb = "Presionar" if re.search(r"presion", clause or "", re.I) else "Seleccionar"
        return f"{verb} {target}", expected
    if re.search(r"\bpin\b", low):
        return "Ingresar el PIN", expected
    if re.search(r"cierre del modal|se cierra el modal", low):
        return "Esperar el cierre del modal", expected
    if re.search(r"redirig|dirige|vcard", low):
        return "Verificar la redirección", expected
    if "alerta" in low:
        return "Verificar la alerta", expected
    if "modal" in low:
        return "Verificar el modal", expected
    if "overlay" in low and re.search(r"icono|candado", low):
        return "Verificar el ícono y el overlay", expected
    if re.search(r"icono|candado|overlay", low):
        return "Verificar lo indicado en pantalla", expected
    if "reproduc" in low:
        if re.search(r"\bno\b", low):
            return "Verificar el resultado", expected
        return "Verificar la reproducción", expected
    if "valid" in low:
        return "Verificar la validación", expected
    return "Verificar el resultado", expected


def visible_then_clauses(*bodies: str) -> list[str]:
    """Cláusulas visibles del Then. La parte técnica de la frase no cuenta."""
    clauses: list[str] = []
    pending = False
    for body in bodies:
        for kind, text in _walk(body):
            if kind != "then":
                continue
            listed = readable_elements(text)
            kept = listed or visible_remainder(text)
            if not kept:
                continue
            if _TEMPORAL.match(kept):
                pending = True
                continue
            if pending:
                sentence = _sentence(kept)
                body_text = sentence[0].lower() + sentence[1:] if sentence else kept
                clauses.append(f"Al terminar el tiempo del modal, {body_text}")
                pending = False
                continue
            clauses.append(kept)
    if pending:
        clauses.append("Al terminar el tiempo del modal.")
    return list(dict.fromkeys(clause for clause in clauses if clause))


def clause_reflected(clause: str, blob: str) -> bool:
    words = [
        word
        for word in re.findall(r"[0-9a-záéíóúñ]{4,}", fold(clause))
        if word not in _STOP
    ]
    if not words:
        return fold(clause) in fold(blob) if clause else True
    folded = fold(blob)
    tokens = re.findall(r"[0-9a-z]{4,}", folded)

    def seen(word: str) -> bool:
        if word in folded:
            return True
        stem = word[:5]
        return any(token.startswith(stem) or word.startswith(token[:5]) for token in tokens if len(token) >= 5)

    found = sum(1 for word in words if seen(word))
    return found == len(words) if len(words) <= 3 else found / len(words) >= 0.7


def user_type_lines(title: str, body: str) -> list[str]:
    lines: list[str] = []
    blob = f"{title}\n{body}"
    for hit in _glossary_hits(blob):
        lines.append(third_person(hit))
    for token in _unknown_user_codes(blob):
        lines.append(f"El usuario corresponde a {token}.")
    named = (
        (r"usuarios? an[oó]nimos?", "El usuario es anónimo."),
        (r"usuarios? no registrados?", "El usuario no está registrado."),
        (r"usuarios? externos?", "El usuario es externo."),
        (r"usuarios? con sesi[oó]n", "El usuario tiene la sesión iniciada."),
        (r"telmex fuera de casa", "El usuario es Telmex fuera de casa."),
        (r"\bip telmex\b", "El usuario es IP Telmex."),
    )
    for pattern, line in named:
        if re.search(pattern, blob, re.I) and not any(fold(line) in fold(item) for item in lines):
            lines.append(line)
    return list(dict.fromkeys(lines))


def screen_label(*texts: str) -> str:
    for text in texts:
        match = re.search(
            r"pantalla(?: de)? [\"“]?([^\"”\n.]{3,60})",
            text or "",
            re.I,
        )
        if match:
            return match.group(1).strip()
        match = re.search(r"\b(modal|home|player|checkout|men[uú])\b", text or "", re.I)
        if match:
            return match.group(1)
    return "la pantalla"


def _collapse_entry(steps: list) -> list:
    out: list = []
    bucket: list = []

    def flush() -> None:
        if not bucket:
            return
        specific = [step for step in bucket if not re.search(r"aplicaci[oó]n", step.action or "", re.I)]
        out.append((specific or bucket)[-1])
        bucket.clear()

    for step in steps:
        if is_entry_action(step.action or ""):
            bucket.append(step)
            continue
        flush()
        out.append(step)
    flush()
    return out


def _same_scenario(units: list) -> bool:
    names = {bare_scenario_name(unit.scenario or "") for unit in units}
    return len(units) > 1 and len(names) == 1 and bool(next(iter(names)))


def _entry_form(unit) -> str:
    bits: list[str] = []
    history: list[str] = []
    for _kind, text in _walk(unit.feature_background or ""):
        if technical_phrase(text) or _KEY_STATE.search(text) or _ERROR_CODE.search(text):
            history.append(text)
            continue
        action = _user_action(text, history)
        if action:
            bits.append(action)
        history.append(text)
    return "; ".join(dict.fromkeys(bits))


def _dedupe_pre(lines: list[str]) -> list[str]:
    ranked = sorted(lines, key=lambda line: 0 if fold(line).startswith("el usuario") else 1)
    kept: list[str] = []
    cores: list[str] = []
    for line in ranked:
        if _JUNK_PRE.match(line.strip(" .")):
            continue
        core = re.sub(
            r"^(el usuario (es|esta|está|tiene|corresponde a)\s+|usuario\s+)",
            "",
            fold(line),
        ).strip(" .")
        if any(core == other or (len(core) > 8 and (core in other or other in core)) for other in cores):
            continue
        cores.append(core)
        kept.append(line)
    return kept


def _flow(units: list) -> tuple[list[dict[str, object]], list[str], list[str], bool]:
    """Pasos en el orden del Gherkin: cada acción seguida de sus resultados."""
    repeated = _same_scenario(units)
    primary = units[0]
    story = fold(primary.story_summary or "")
    anon, auth = scenario_stance(primary.scenario or "", primary.body or "")
    states: list[str] = []
    warnings: list[str] = []
    segments: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    history: list[str] = []

    def close() -> None:
        nonlocal current
        if current and current.get("action") and not current.get("results"):
            source = str(current.get("_source") or "")
            action = str(current.get("action") or "")
            if source and _SETUP_CLAUSE.search(source) and not is_entry_flow(action):
                current["results"] = [_setup_result(source)]
        if current and (current.get("action") or current.get("results")):
            segments.append(current)
        current = None

    sources: list[tuple[str, bool]] = []
    if repeated:
        sources.append((primary.body or "", False))
    else:
        for unit in units:
            sources.append((unit.feature_background or "", True))
            sources.append((unit.body or "", False))
    for source, from_background in sources:
        for kind, text in _walk(source):
            if from_background and kind == "then" and not _observable_clause(text):
                history.append(text)
                continue
            if story and fold(text) == story:
                continue
            if from_background and background_contradicts(text, anon, auth):
                continue
            if _KEY_STATE.search(text) and not _VISIBLE_ASSERT.search(text):
                warnings.append(text[:180])
                history.append(text)
                continue
            if (_ERROR_CODE.search(text) or technical_phrase(text)) and not visible_remainder(text):
                warnings.append(text[:180])
                history.append(text)
                continue
            panel = _audio_panel(text)
            if panel:
                close()
                segments.extend(panel)
                history.append(text)
                continue
            embedded, embedded_result = ("", "")
            if kind == "then":
                embedded, embedded_result = _embedded_press(text)
            listed = readable_elements(text)
            action = "" if listed or re.match(r"^se muestra\b", text, re.I) else embedded or _user_action(text, history)
            if action and re.search(r"\b(es dirigido|se redirige|se dirige)\b", fold(text)) and not re.search(
                r"bot[oó]n|clic|presion", text or "", re.I
            ):
                action = ""
            if _DEV_OR_CODE.search(text) or re.search(r"c[oó]digo\s*200", text, re.I):
                history.append(text)
                continue
            if kind == "then" and not embedded and _RESULT_LEAD.search(text or ""):
                action = ""
            if action and (kind != "then" or embedded or given_goes_to_step(text)):
                if current and current.get("action") and not current.get("results"):
                    close()
                elif current and (current.get("action") or current.get("results")):
                    close()
                current = {"action": action, "results": [], "_source": text}
                arrival = _SCREEN_ARRIVAL.search(text)
                if arrival and kind != "then":
                    shown = re.sub(r"^Ingresar a la\s+", "Se muestra la ", action, flags=re.IGNORECASE).strip(" .")
                    if shown:
                        current["results"].append(shown if shown.endswith(".") else shown + ".")
                if kind == "then" and not embedded_result:
                    current["results"].append(text)
                elif embedded_result:
                    current["results"].append(embedded_result)
                history.append(text)
                continue
            visible = (
                kind == "then"
                or bool(_OUTCOME.search(text))
                or (
                    current is not None
                    and current.get("action")
                    and (bool(re.match(r"^se muestra\b", text, re.I)) or _observable_clause(text))
                )
            )
            if visible:
                piece = readable_elements(text) or visible_remainder(text)
                if piece:
                    if current is None:
                        current = {"action": "", "results": []}
                    results = current["results"]
                    assert isinstance(results, list)
                    results.append(piece)
                history.append(text)
                continue
            if not given_goes_to_step(text):
                states.append(text)
            history.append(text)
    close()
    _fill_entry_results(segments)
    return segments, states, warnings, repeated


def _leading_action(units: list) -> str:
    blob = "\n".join(f"{unit.scenario or ''}\n{unit.body or ''}" for unit in units)
    if re.search(r"\bpin\b|n[uú]mero celular|m[eé]todo de pago", blob, re.I) and re.search(
        r"modal|exitos|error|agreg", blob, re.I
    ):
        return "Ingresar el PIN"
    return ""


def _action_count(action: str) -> int:
    return len([part for part in re.split(r"\s+y\s+", action or "") if part.strip()])


def _changes_screen(action: str) -> bool:
    if is_entry_flow(action):
        return True
    return bool(re.search(r"\b(reproduc|checkout|nodo|home|alta|validaci|vincular)\b", fold(action)))


def _same_screen(left: str, right: str) -> bool:
    """Solo se encadenan acciones que ocurren en la misma pantalla."""
    if _changes_screen(left) or _changes_screen(right):
        return False
    return True


def _merge_filler_steps(steps: list) -> list:
    """Una acción sin resultado se une a la siguiente, como máximo dos, y en la misma pantalla."""
    merged: list = []
    for step in steps:
        nxt = step.action or ""
        if (
            merged
            and is_filler_expected(merged[-1].action, merged[-1].expected_result)
            and nxt
            and (step.expected_result or "").strip()
            and not is_filler_expected(nxt, step.expected_result)
            and _action_count(merged[-1].action) < 2
            and _action_count(nxt) == 1
            and _same_screen(merged[-1].action, nxt)
        ):
            merged[-1].action = f"{merged[-1].action} y {nxt[0].lower()}{nxt[1:]}"
            merged[-1].expected_result = step.expected_result
            continue
        merged.append(step)
    return merged


def _fill_entry_results(segments: list[dict[str, object]]) -> None:
    """El ingreso usa el estado del Given o la pantalla destino, sin encadenar acciones."""
    for index, segment in enumerate(segments):
        if segment.get("results") or not segment.get("action"):
            continue
        action = str(segment.get("action") or "")
        if not is_entry_flow(action):
            continue
        nxt = ""
        if index + 1 < len(segments):
            nxt = str(segments[index + 1].get("action") or "")
        if re.search(r"perfil", fold(nxt)):
            segment["results"] = ["Se muestra la pantalla de perfiles"]
            continue
        if re.search(r"perfil", fold(action)):
            segment["results"] = ["Se muestra el perfil elegido"]
            continue
        if re.search(r"^(ingresar|acceder|abrir|entrar)\b", fold(action)) and re.search(
            r"pantalla|home|nodo|principal", fold(action)
        ):
            dest = re.sub(
                r"^(Ingresar|Acceder|Abrir|Entrar)(?: a| al)?\s+",
                "",
                action,
                count=1,
                flags=re.IGNORECASE,
            ).strip(" .")
            if dest:
                segment["results"] = [f"Se muestra {dest}"]
                continue
        if re.search(r"^autentic", fold(action)):
            segment["results"] = ["El usuario queda autenticado"]
            continue
        named = re.search(r"pantalla principal|pantalla de|nodo|home|checkout|gesti", fold(action))
        if named:
            continue
        if re.search(r"aplicaci|claro video", fold(action)):
            segment["results"] = ["Se muestra la pantalla de ingreso"]


def _order_cancel_before_removal(steps: list) -> list:
    """Tras cancelar se reabre el modal y después se confirma la eliminación."""
    from app.schemas.case_generation import CandidateStep

    removal = next(
        (
            index
            for index, step in enumerate(steps)
            if re.search(r"ya no aparece|proceder con la eliminaci", step.expected_result or "", re.I)
        ),
        None,
    )
    if removal is None:
        return steps
    later = [step for step in steps[removal + 1 :] if re.search(r"\bcancelar\b", step.action or "", re.I)]
    if later:
        rest = [step for step in steps[removal + 1 :] if step not in later]
        steps = [*steps[:removal], *later, steps[removal], *rest]
        removal = next(
            index
            for index, step in enumerate(steps)
            if re.search(r"ya no aparece|proceder con la eliminaci", step.expected_result or "", re.I)
        )
    cancel_at = max(
        (
            index
            for index, step in enumerate(steps[:removal])
            if re.search(r"\bcancelar\b", step.action or "", re.I)
        ),
        default=None,
    )
    if cancel_at is None:
        return steps
    opener = next(
        (
            step
            for step in steps[:cancel_at]
            if re.search(r"eliminar", step.action or "", re.I)
            and re.search(r"modal|se muestran|seguro de eliminar", step.expected_result or "", re.I)
        ),
        None,
    )
    if opener is None:
        return steps
    following = steps[cancel_at + 1] if cancel_at + 1 < len(steps) else None
    if (
        following
        and re.search(r"eliminar", following.action or "", re.I)
        and re.search(r"modal|se muestran|seguro de eliminar", following.expected_result or "", re.I)
        and not re.search(r"ya no aparece", following.expected_result or "", re.I)
    ):
        return steps
    parts = [part.strip() for part in re.split(r"\s+y\s+", opener.action or "") if part.strip()]
    action = next((part for part in reversed(parts) if re.search(r"eliminar", part, re.I)), "")
    if not action:
        action = "Seleccionar el botón «Eliminar»"
    elif action[0].islower():
        action = action[0].upper() + action[1:]
    clone = CandidateStep(
        step_number=0,
        action=action,
        expected_result=opener.expected_result,
        covered_unit_ids=list(opener.covered_unit_ids or []),
    )
    return [*steps[: cancel_at + 1], clone, *steps[cancel_at + 1 :]]


def _ensure_pin(steps: list) -> list:
    from app.schemas.case_generation import CandidateStep

    if any(re.search(r"\bpin\b", step.action or "", re.I) for step in steps):
        return steps
    out: list = []
    inserted = False
    for step in steps:
        text = step.expected_result or ""
        if inserted or not re.search(r"validaci[oó]n de l[ií]nea", text, re.I):
            out.append(step)
            continue
        if not re.search(r"exitos|no se concret|modal de error|modal de confirm", text, re.I):
            out.append(step)
            continue
        parts = [part.strip() for part in re.split(r"(?<=\.)\s+", text) if part.strip()]
        screen: list[str] = []
        outcome: list[str] = []
        seen = False
        for part in parts:
            if not seen and re.search(r"validaci[oó]n de l[ií]nea", part, re.I):
                screen.append(part)
                seen = True
                continue
            (outcome if seen else screen).append(part)
        step.expected_result = " ".join(screen).strip()
        out.append(step)
        out.append(
            CandidateStep(
                step_number=0,
                action="Ingresar el PIN",
                expected_result=" ".join(outcome).strip(),
                covered_unit_ids=[],
            )
        )
        inserted = True
    return out


def _action_from_clause(text: str) -> str:
    raw = re.sub(r"^(?:se muestra|se visualiza)\s+", "", text or "", flags=re.IGNORECASE).strip(" .")
    if not raw:
        return ""
    return f"Comprobar {raw[:160]}"


def _entry_screen(units: list) -> str:
    """Primera pantalla nombrada en el Given, cuando no quedó otra acción."""
    blob = "\n".join(
        f"{unit.feature_background or ''}\n{unit.body or ''}" for unit in units
    )
    match = _SCREEN_ARRIVAL.search(blob)
    if match:
        dest = re.sub(r"\s+", " ", match.group(1)).strip(" .")
        return f"Ingresar a la {dest}"
    named = re.search(
        r"\bpantalla\s+(?:de\s+|del\s+|principal\b|de\s+inicio\b)[^.;]{0,60}",
        blob,
        re.IGNORECASE,
    )
    if named and re.search(r"\b(given|dado)\b", blob, re.I):
        dest = re.sub(r"\s+", " ", named.group(0)).strip(" .")
        return f"Ingresar a la {dest}"
    return ""


def _plain_step(text: str) -> str:
    out = _GHERKIN_WORD.sub(" ", text or "")
    return re.sub(r"\s+", " ", out).strip()


def _presented_entry(units: list) -> str:
    blob = "\n".join(f"{unit.body or ''}" for unit in units)
    match = re.search(
        r"(?:la\s+|el\s+)?(pantalla\b[^.;]{0,70}?)\s+est[aá]\s+presentad",
        blob,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(r"\best[aá] en la (pantalla\b[^.;]{0,70})", blob, re.IGNORECASE)
    if not match:
        return ""
    dest = re.sub(r"\s+", " ", match.group(1)).strip(" .")
    return f"Ingresar a la {dest}"


def _present_screen_first(steps: list, units: list) -> list:
    """La pantalla intermedia del Given es el primer paso, antes de la acción."""
    from app.schemas.case_generation import CandidateStep

    entry = _presented_entry(units)
    if not entry or not steps:
        return steps
    if len(steps) == 1 and _FROZEN_ONE_STEP.match(steps[0].action or ""):
        return steps
    if fold(steps[0].action).startswith("ingresar a la pantalla"):
        return steps
    dest = re.sub(r"^Ingresar a la\s+", "", entry, flags=re.IGNORECASE).strip(" .")
    intro = CandidateStep(
        step_number=1,
        action=entry,
        expected_result=f"Se muestra la {dest}.",
        covered_unit_ids=list(steps[0].covered_unit_ids or []),
    )
    return [intro, *steps]


def _observation_target(expected: str, title: str) -> str:
    """El objeto que Luminia pondría en «Observar …», sacado del Then o del título."""
    first = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", expected or "").strip())
    cut = first[0] if first else ""
    cut = re.sub(
        r"^(?:(?:WEB|WIN|STV|ADT)CL|la aplicación)\s+(?:no\s+)?(?:presenta|muestra)\s+",
        "",
        cut,
        flags=re.IGNORECASE,
    )
    shown = re.search(
        r"^((?:el|la|los|las)\s+\S+(?:\s+\S+){0,4})\s+se muestra\b",
        cut,
        flags=re.IGNORECASE,
    )
    if shown:
        cut = shown.group(1)
    else:
        cut = re.sub(
            r"^(?:se muestra|se presenta|se visualiza|no se muestra|no se presenta)\s+",
            "",
            cut,
            flags=re.IGNORECASE,
        )
    cut = re.sub(
        r"\s+(?:con|conforme|según|segun|para|actualmente|mediante|cuando)\b.*",
        "",
        cut,
        flags=re.IGNORECASE,
    )
    cut = cut.strip(" .\"“”")
    words = cut.split()
    if (
        2 <= len(words) <= 6
        and re.match(r"^(?:el|la|los|las|un|una)\b", cut, re.IGNORECASE)
        and not re.search(r"\b(se\s+\w+|sigue|queda|presenta|muestra|da|falla|conserva)\b", cut, re.IGNORECASE)
    ):
        return cut[0].lower() + cut[1:]
    named = re.search(
        r"\b(?:del|de la|de los|de las)\s+([A-Za-zÁ-úáéíóúñ][^.]{2,40})$",
        title or "",
        re.IGNORECASE,
    )
    if not named:
        return ""
    phrase = named.group(1).strip(" .")
    if not 1 <= len(phrase.split()) <= 6:
        return ""
    if re.search(r"\b(se\s+\w+|sigue|queda|presenta|muestra|falla|conserva)\b", phrase, re.IGNORECASE):
        return ""
    return phrase[0].lower() + phrase[1:]


def _check_after_action(steps: list, title: str = "") -> list:
    """Separa el ingreso de la observación cuando el Then nombra lo que hay que mirar."""
    from app.schemas.case_generation import CandidateStep

    if len(steps) != 1:
        return steps
    step = steps[0]
    if (
        _FROZEN_ONE_STEP.match(step.action or "")
        or re.match(r"^(?:comprobar|observar)\b", step.action or "", re.I)
        or re.search(r"\bpin\b", step.action or "", re.I)
    ):
        return steps
    expected = (step.expected_result or "").strip()
    if not expected or _RESULT_LEAD.search(step.action or "") or _RESULT_LEAD.search(expected):
        return steps
    target = _observation_target(expected, title)
    if not target:
        return steps
    action = step.action or ""
    if re.search(r"credencial", action, re.I):
        echo = "Las credenciales quedan ingresadas."
    else:
        head = re.split(r"\s+y\s+", action, maxsplit=1, flags=re.IGNORECASE)[0]
        named = re.match(
            r"^(?:Ingresar|Acceder|Abrir|Entrar)\s+(?:a\s+|al\s+)?(.+)$",
            head,
            re.IGNORECASE,
        )
        echo = f"Se muestra {named.group(1).strip(' .')}." if named else ""
        if not echo:
            fallback = _fallback_result(action)
            if fallback != "La pantalla queda en el estado siguiente.":
                echo = fallback
    if not echo or fold(expected) == fold(echo):
        return steps
    step.expected_result = echo
    return [
        step,
        CandidateStep(
            step_number=2,
            action=f"Observar {target}",
            expected_result=expected,
            covered_unit_ids=list(step.covered_unit_ids or []),
        ),
    ]


def finish_case(case, units: list) -> None:
    """Reconstruye el caso desde el escenario: no pierde el Then ni inventa pasos."""
    from app.schemas.case_generation import CandidateStep

    if not units:
        return
    primary = units[0]
    title = clean_title(primary.scenario or case.name or "")
    segments, states, warnings, repeated = _flow(units)
    steps = []
    for segment in segments:
        action = str(segment.get("action") or "")
        results = segment.get("results") or []
        expected = _join_results([str(part) for part in results])
        if not action and expected and steps and is_entry_flow(steps[-1].action):
            steps[-1].expected_result = f"{steps[-1].expected_result} {expected}".strip()
            continue
        if not action and expected:
            source = "\n".join(f"{unit.body or ''}\n{unit.feature_background or ''}" for unit in units)
            if re.search(r"\bhome\b|pantalla principal", f"{expected}\n{source}", re.I) and re.search(
                r"renderiza|ingresa|abre|accede", source, re.I
            ):
                action = "Ingresar a la Home"
            else:
                action = _leading_action(units) or _entry_screen(units)
        if not action:
            continue
        if is_filler_expected(action, expected):
            expected = ""
        if not expected and re.search(r"^buscar\b", action, re.I):
            expected = "Se muestra el resultado de la búsqueda."
        steps.append(
            CandidateStep(
                step_number=len(steps) + 1,
                action=action,
                expected_result=expected,
                covered_unit_ids=[primary.coverage_id],
            )
        )
    steps = [step for step in _collapse_entry(steps) if not is_filler_step(step.action, step.expected_result)]
    # Unir verificaciones seguidas de la misma pantalla en un solo paso.
    folded: list = []
    for step in steps:
        if (
            folded
            and fold(step.action) == fold(folded[-1].action) == fold("Verificar lo indicado en pantalla")
        ):
            folded[-1].expected_result = f"{folded[-1].expected_result} {step.expected_result}".strip()
            continue
        folded.append(step)
    steps = _merge_filler_steps(_order_cancel_before_removal(_ensure_pin(folded)))
    if len(steps) == 1 and fold(steps[0].action).startswith("verificar"):
        leading = _leading_action(units) or _entry_screen(units)
        if leading:
            steps[0].action = leading
        else:
            steps = []
    for index, step in enumerate(steps, start=1):
        step.step_number = index
        step.expected_result = _at_word(step.expected_result or "", 2000)
        if technical_phrase(step.expected_result or ""):
            step.expected_result = visible_remainder(step.expected_result) or ""
        if is_filler_expected(step.action, step.expected_result):
            step.expected_result = ""
    steps = _merge_filler_steps(steps)
    kept = [step for step in steps if (step.expected_result or "").strip()]
    if kept:
        steps = kept
    criterion = any("criterio-epica" in (unit.applied_rules or []) for unit in units)
    topic = "\n".join(f"{unit.scenario or ''}\n{unit.body or ''}" for unit in units)
    visible_topic = bool(
        re.search(r"audio|subt[ií]tulo|pantalla|bot[oó]n|mensaje|modal", topic, re.IGNORECASE)
    )
    if not steps and (
        any(then_has_visible_outcome(unit.body or "") for unit in units)
        or (criterion and visible_topic)
    ):
        visible = _join_results(visible_then_clauses(*(unit.body or "" for unit in units)))
        if not visible and criterion:
            visible = _strip_md(re.sub(r"^(?:then|entonces)\s+", "", primary.body or "", flags=re.I))
        action = _leading_action(units) or _entry_screen(units)
        if not action and criterion:
            action = _action_from_clause(visible)
        if visible and action:
            steps = [
                CandidateStep(
                    step_number=1,
                    action=action,
                    expected_result=visible,
                    covered_unit_ids=[primary.coverage_id],
                )
            ]
    steps = _present_screen_first(steps, units)
    steps = _check_after_action(steps, title)
    for index, step in enumerate(steps, start=1):
        step.step_number = index
        step.action = _plain_step(_strip_md(step.action or ""))
        step.expected_result = _plain_step(_strip_md(step.expected_result or ""))
    bodies = [primary.body or ""] if repeated else [unit.body or "" for unit in units]
    thens = visible_then_clauses(*bodies)
    blob = " ".join(f"{step.action} {step.expected_result}" for step in steps)
    missing = [clause for clause in thens if not clause_reflected(clause, blob)]
    rules = [rule for rule in (case.applied_rules or []) if not str(rule).startswith("error-then")]
    for clause in missing:
        rules.append(f"error-then:{_at_word(clause, 160)}")
    enabled = False
    for unit in units:
        for source in (unit.feature_background or "", unit.body or ""):
            if _KEY_STATE.search(source):
                enabled = True
    pre_lines: list[str] = []
    pre_lines.extend(
        _account_lines(
            primary.scenario or "",
            "\n".join(
                (unit.feature_background or "") + "\n" + (unit.body or "") + "\n" + (unit.scenario or "")
                for unit in units
            ),
        )
    )
    if not repeated:
        pre_lines.extend(user_type_lines(primary.scenario or "", "\n".join(unit.body or "" for unit in units)))
    if enabled:
        pre_lines.append(_ENABLED)
    anon, auth = scenario_stance(primary.scenario or "", primary.body or "")
    for state in states:
        if background_contradicts(state, anon, auth) or _KEY_STATE.search(state) or _ERROR_CODE.search(state):
            continue
        if _KEY_ABSENT.search(state):
            continue
        if technical_phrase(state) and not visible_remainder(state):
            continue
        if given_goes_to_step(state):
            continue
        line = _GHERKIN_LEAD.sub("", third_person(visible_remainder(state) or state)).strip()
        line = _without_tech_clauses(line)
        if not line or _JUNK_PRE.match(line.strip(" .")) or _DEV_OR_CODE.search(line):
            continue
        if re.search(r"comienza a corregir", line, re.I):
            continue
        pre_lines.append(line if line.endswith(".") else line + ".")
    case.name = title
    case.precondition = "; ".join(_dedupe_pre(pre_lines)) or None
    case.steps = steps
    case.applied_rules = rules
    if repeated:
        rows = ["Tipo de usuario | Forma de entrada"]
        seen: set[str] = set()
        for unit in units:
            summary = (unit.story_summary or "").strip()
            if summary and len(summary.split()) <= 6 and re.search(
                r"usuario|telmex|an[oó]nim", summary, re.I
            ):
                label = summary
            else:
                label = (
                    user_type_lines(unit.story_summary or "", unit.story_summary or "")
                    or ["El usuario del escenario."]
                )[0]
            entry = _entry_form(unit) or "Ingreso según su tipo de usuario."
            row = f"{label} | {entry}"
            if row in seen:
                continue
            seen.add(row)
            rows.append(row)
        if len(rows) > 1:
            case.variant_table = "\n".join(rows)
    if warnings and hasattr(primary, "technical_notes"):
        notes = list(primary.technical_notes or [])
        for warning in warnings:
            note = f"advertencia: {warning}"
            if note not in notes:
                notes.append(note)
        primary.technical_notes = notes


def prepend_sister_paths(cases: list, inventory: list) -> None:
    """Si el caso empieza en el PIN, antepone el camino de la historia hermana."""
    from app.schemas.case_generation import CandidateStep

    by_id = {unit.coverage_id: unit for unit in inventory}

    def units_of(case):
        return [by_id[cid] for cid in (case.covers or case.covered_unit_ids or []) if cid in by_id]

    def epic_of(case) -> str:
        rows = units_of(case)
        if not rows:
            return ""
        return rows[0].artifact_key or rows[0].story_key or ""

    grouped: dict[str, list] = {}
    for case in cases:
        grouped.setdefault(epic_of(case), []).append(case)
    for bucket in grouped.values():
        for case in bucket:
            if not case.steps or not re.search(r"\bpin\b", case.steps[0].action or "", re.I):
                continue
            sister = None
            best = 0
            for other in bucket:
                if other is case or not other.steps:
                    continue
                pin_at = next(
                    (index for index, step in enumerate(other.steps) if re.search(r"\bpin\b", step.action or "", re.I)),
                    None,
                )
                if pin_at is None or pin_at < 1 or pin_at <= best:
                    continue
                best = pin_at
                sister = other
            if sister is None:
                continue
            prefix = [step.model_copy(deep=True) for step in sister.steps[:best]]
            blob = "\n".join(
                f"{unit.feature_background or ''}\n{unit.body or ''}" for unit in units_of(sister)
            )
            if re.search(r"pantalla de checkout", blob, re.I) and not any(
                "checkout" in fold(step.action) for step in prefix
            ):
                prefix.insert(
                    0,
                    CandidateStep(
                        step_number=1,
                        action="Ingresar a la pantalla de Checkout",
                        expected_result="Se muestra la pantalla de Checkout.",
                        covered_unit_ids=[],
                    ),
                )
            case.steps = prefix + list(case.steps)
            for index, step in enumerate(case.steps, start=1):
                step.step_number = index


_QA_LABEL = re.compile(r"QA\s*Validations?\b|QA\s*Validaci[oó]n\b", re.IGNORECASE)
_GLUE_PARTICLE = (
    "para", "como", "del", "las", "los", "una", "con", "por", "que", "sus",
    "se", "el", "la", "de", "al", "un", "en", "es", "lo", "su", "no", "y", "a",
)
_GLUE_KEEP = {
    "servicio", "segundo", "selector", "semana", "serie", "sesion", "sesión",
    "siguiente", "siempre", "sentido", "servidor", "contenido", "contenidos",
    "continuar", "validacion", "validación", "aplicacion", "aplicación",
    "reproduccion", "reproducción", "navegacion", "navegación", "transaccion",
    "transacción", "categoria", "categoría", "resultado", "resultados",
    "bloqueante", "critical", "grabacion", "grabación",
}
_GLUE_LEXEME = {
    "pantalla", "visualizan", "visualiza", "metodo", "método", "pago", "pagina",
    "página", "google", "contenido", "contenidos", "categoria", "categoría",
    "tiempo", "inicio", "busqueda", "búsqueda", "búsquedas", "mostrar",
    "resultados", "plan", "selector", "error", "botones", "carrusel",
    "recomendados", "transaccion", "transacción", "codigo", "código", "negro",
    "live", "despues", "después",
}


def _unglue_token(token: str) -> str:
    body = token.strip(".,;:")
    if body.lower() in _GLUE_KEEP:
        return token
    if body[:1].isupper() and not re.search(r"[a-záéíóúñ][A-ZÁÉÍÓÚÑ]", body):
        return token
    body = re.sub(r"([a-záéíóúñ])([A-ZÁÉÍÓÚÑ])", r"\1 \2", body)
    body = re.sub(r"([A-ZÁÉÍÓÚÑ]{2,})([a-záéíóúñ])", r"\1 \2", body)
    return " ".join(_unglue_piece(piece) for piece in body.split(" "))


def _unglue_piece(token: str) -> str:
    raw = token.strip(".,;:")
    low = raw.lower()
    if len(low) < 5 or low in _GLUE_KEEP or low in _GLUE_LEXEME:
        return token
    for particle in sorted(_GLUE_PARTICLE, key=len, reverse=True):
        if len(particle) < 2 or not low.startswith(particle) or len(low) <= len(particle) + 2:
            continue
        rest = low[len(particle):]
        if rest in _GLUE_LEXEME or rest in _GLUE_PARTICLE or re.search(
            r"(ar|er|ir|an|en|ado|ada|ción|sion)$", rest
        ):
            return raw[: len(particle)] + " " + _unglue_piece(raw[len(particle) :])
    for particle in sorted(_GLUE_PARTICLE, key=len, reverse=True):
        if len(particle) < 2 or not low.endswith(particle) or len(low) - len(particle) < 4:
            continue
        head = low[: -len(particle)]
        if head in _GLUE_KEEP or head in _GLUE_LEXEME or len(head) >= 6:
            return _unglue_piece(raw[: -len(particle)]) + " " + raw[-len(particle) :]
    return token


def clean_incident_title(ticket_id: str, cell: str) -> str:
    raw = _strip_md(re.sub(r"\s+", " ", cell or "")).strip()
    raw = re.sub(rf"^\s*{re.escape(ticket_id)}\s*:?\s*", "", raw, flags=re.IGNORECASE).strip(" -:")
    raw = _QA_LABEL.sub("", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" -:")
    if not raw or re.fullmatch(r"\[?\s*ticket jira\s*\]?", raw, re.IGNORECASE):
        return ""
    return " ".join(_unglue_token(part) for part in raw.split(" "))


def incident_retest_cases(tickets: dict | None, rn_filename: str) -> list:
    """Un caso de reprueba por incidencia corregida (sección 2.2)."""
    from app.schemas.case_generation import CandidateStep, GeneratedCaseCandidate

    cases = []
    seen: set[str] = set()
    for ticket_id, cell in (tickets or {}).get("qa_qc") or []:
        key = (ticket_id or "").strip().upper()
        if not key or key in seen:
            continue
        raw = clean_incident_title(ticket_id, cell or "")
        if not raw:
            continue
        seen.add(key)
        summary = raw[:180]
        cases.append(
            GeneratedCaseCandidate(
                name=summary,
                description=raw[:2000],
                steps=[
                    CandidateStep(
                        step_number=1,
                        action=f"Reproducir el escenario: {_plain_step(raw[:700])}",
                        expected_result="Se alcanza el punto en el que ocurría el defecto.",
                    ),
                    CandidateStep(
                        step_number=2,
                        action="Completar el flujo descrito en la incidencia.",
                        expected_result="El defecto ya no ocurre.",
                    ),
                ],
                related_jira=ticket_id,
                related_rn=rn_filename or None,
                related_functionality="Reprueba de incidencias",
                component="Reprueba de incidencias",
                evidence=(cell or "")[:2000],
                justification=f"Reprueba de la incidencia corregida {ticket_id}.",
                confidence="medium",
                review_required=True,
                priority="CRITICAL",
                generation_origin="reprueba-incidencia",
                source_type="qa_qc",
                applied_rules=["reprueba-incidencia"],
            )
        )
    return cases
