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
    r"pulsar|pulsa|confirmar|confirma|cancelar|cancela)\b",
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
_VISIBLE_THEN = re.compile(
    r"se muestra|se visualiza|pantalla|modal|elementos|bot[oó]n|mensaje",
    re.IGNORECASE,
)
_THEN_TECH = re.compile(
    r"\b(API|servicio|par[aá]metro|user_hash|endpoint|se obtiene)\b",
    re.IGNORECASE,
)
_NO_AFECTACION = re.compile(
    r"se ve[n]? igual que antes|mantener comportamiento actual|"
    r"no se (ve|ven) afect|sin afectaci[oó]n|no afectaci[oó]n",
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
    """Verbo de acción del usuario en el Given: pasa a Test Steps, no a precondición."""
    if not text or not _USER_VERBS.search(text):
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
    if _KEY_TITLE.search(title or ""):
        return "verificacion", "llave, configuración o metadata: no es caso QC"
    if _THEN_TECH.search(then) and not _VISIBLE_THEN.search(then):
        return "verificacion", "el Then menciona API, servicio, parámetro o endpoint"
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
    raw = (title or "").strip()
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
    return bool(_PHRASE_TECH.search(text or ""))


def third_person(text: str) -> str:
    raw = re.sub(r"\s+", " ", (text or "").strip())
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
        if line:
            rows.append((kind, line))
    return rows


def _user_action(text: str) -> str:
    if not text or technical_phrase(text) or not given_goes_to_step(text):
        return ""
    from app.services.case_composer import to_infinitive

    quoted = re.search(r"[\"“]([^\"”]+)[\"”]", text)
    if quoted and re.search(r"clic|seleccion|presion", text, re.I):
        return f"Seleccionar {quoted.group(1)}"
    action = to_infinitive(text) or text
    action = re.sub(r"^ingreso\b", "Ingresar", action, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", action).strip()


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
    for body in bodies:
        for kind, text in _walk(body):
            if kind != "then" or technical_phrase(text):
                continue
            listed = readable_elements(text)
            clauses.append(listed or re.sub(r"\s+", " ", text).strip())
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
    found = sum(1 for word in words if word in folded)
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


def finish_case(case, units: list) -> None:
    """Reconstruye el caso desde el escenario: no pierde el Then ni inventa pasos."""
    from app.schemas.case_generation import CandidateStep

    if not units:
        return
    primary = units[0]
    title = clean_title(primary.scenario or case.name or "")
    anon, auth = scenario_stance(primary.scenario or "", "\n".join(unit.body or "" for unit in units))
    actions: list[str] = []
    states: list[str] = []
    outcomes: list[str] = []
    warnings: list[str] = []
    for unit in units:
        story = fold(unit.story_summary or "")
        for source, skip_then in ((unit.feature_background or "", True), (unit.body or "", False)):
            for kind, text in _walk(source):
                if kind == "then" and skip_then:
                    continue
                if kind == "then":
                    continue
                if technical_phrase(text):
                    warnings.append(text[:180])
                    continue
                if story and fold(text) == story:
                    continue
                if skip_then and background_contradicts(text, anon, auth):
                    continue
                action = _user_action(text)
                if action:
                    actions.append(action)
                elif _OUTCOME.search(text):
                    outcomes.append(text)
                elif not given_goes_to_step(text):
                    states.append(text)
    deduped: list[str] = []
    for action in actions:
        if deduped and fold(deduped[-1]) == fold(action):
            continue
        deduped.append(action)
    thens = list(dict.fromkeys([*outcomes, *visible_then_clauses(*(unit.body or "" for unit in units))]))
    steps = [
        CandidateStep(step_number=index, action=action, expected_result="", covered_unit_ids=[primary.coverage_id])
        for index, action in enumerate(deduped, start=1)
    ]
    steps = [step for step in _collapse_entry(steps) if not is_filler_step(step.action, step.expected_result)]
    hidden = bool(thens) and bool(re.search(r"presionar|presiona|da clic|hace clic", thens[0] if len(thens) == 1 else "", re.I))
    if len(thens) == 1 and steps and not hidden:
        steps[-1].expected_result = _sentence(thens[0])
    elif thens:
        for clause in thens:
            action, expected = _event_step(clause)
            steps.append(
                CandidateStep(
                    step_number=len(steps) + 1,
                    action=action,
                    expected_result=expected,
                    covered_unit_ids=[primary.coverage_id],
                )
            )
    for step in steps:
        if technical_phrase(step.action or ""):
            step.action = ""
        if technical_phrase(step.expected_result or ""):
            step.expected_result = ""
        if not (step.expected_result or "").strip() and step.action:
            step.expected_result = _arrival(step.action)
        if _FILLER_RESULT.match((step.expected_result or "").strip()):
            step.expected_result = _arrival(step.action)
    steps = [step for step in steps if (step.action or "").strip() and not is_filler_step(step.action, "")]
    for index, step in enumerate(steps, start=1):
        step.step_number = index
        step.expected_result = _at_word(step.expected_result or "", 500)
    blob = " ".join(step.expected_result or "" for step in steps)
    missing = [clause for clause in thens if not clause_reflected(clause, blob)]
    rules = [rule for rule in (case.applied_rules or []) if not str(rule).startswith("error-then")]
    for clause in missing:
        rules.append(f"error-then:{_at_word(clause, 160)}")
    pre_lines = user_type_lines(primary.scenario or "", "\n".join(unit.body or "" for unit in units))
    for state in states:
        if background_contradicts(state, anon, auth) or technical_phrase(state):
            continue
        line = third_person(state)
        if line and not any(fold(line) in fold(item) or fold(item) in fold(line) for item in pre_lines):
            pre_lines.append(line)
    # El tipo declarado en el escenario no se pierde aunque el Background diga otra cosa.
    case.name = title
    case.precondition = "; ".join(dict.fromkeys(pre_lines)) or None
    case.steps = steps
    case.applied_rules = rules
    if warnings and hasattr(primary, "technical_notes"):
        notes = list(primary.technical_notes or [])
        for warning in warnings:
            note = f"advertencia: {warning}"
            if note not in notes:
                notes.append(note)
        primary.technical_notes = notes
