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


def gloss_precondition(text: str) -> tuple[str | None, list[str]]:
    """Traduce con el glosario. Si queda técnica y no hay traducción, se elimina."""
    warnings: list[str] = []
    out = re.sub(r"[\"“”'`]", "", text or "")
    out = re.sub(r"\s*=\s*", "=", out)
    table = glossary()
    hits: list[str] = []
    for key in sorted(table, key=len, reverse=True):
        if key.lower() in out.lower():
            hits.append(table[key])
            out = re.sub(re.escape(key), " ", out, flags=re.IGNORECASE)
    if _TECH_PHRASE.search(out):
        warnings.append(re.sub(r"\s+", " ", out).strip()[:180])
        if hits:
            return "; ".join(dict.fromkeys(hits)), warnings
        return None, warnings
    if hits:
        return "; ".join(dict.fromkeys(hits)), warnings
    stripped = re.sub(
        r"^(?:el |la |los |las )?usuarios? (?:es|son)\s+",
        "",
        out,
        flags=re.IGNORECASE,
    ).strip(" .")
    for value in table.values():
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


def clean_title(title: str, user: str, action: str, result: str) -> str:
    """Conserva el nombre del escenario. Lo reconstruye si quedó cortado o sin sentido."""
    raw = (title or "").strip()
    broken = bool(_BROKEN_QUOTE.search(raw))
    text = _BROKEN_QUOTE.sub("", raw)
    text = re.sub(r"[\"“”']", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -:")
    dangling = bool(_DANGLING.search(text)) or text.endswith(("…", "...", "-", "/"))
    words = [
        word
        for word in re.findall(r"[0-9A-Za-zÁÉÍÓÚáéíóúÑñ]+", text)
        if len(word) > 2 and word.lower() not in {"del", "los", "las", "para", "con", "por", "una", "que"}
    ]
    if text and not broken and not dangling and len(words) >= 2:
        return text[:120]
    action_bit = _clip_words(re.split(r"[;]", action or "")[0], 6)
    result_bit = _clip_words(re.split(r"[;]", result or "")[0], 8)
    user_bit = _clip_words(user, 6) if user and len(user.split()) <= 8 else ""
    built = " ".join(part for part in (user_bit, action_bit, result_bit) if part).strip()
    if len([word for word in built.split() if len(word) > 2]) >= 4:
        return built[:120]
    return (text or built or "Caso QC")[:120]


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
