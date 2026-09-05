"""Turn an approved matrix preview TC into executable tester steps.

Does not change coverage, scope, or device expansion. Uses HN/CA text already
present on the preview row.
"""

from __future__ import annotations

import re

from app.schemas.case_generation import CandidateStep
from app.schemas.matrix_preview import PreviewTestCase

_METADATA_STEP_RE = re.compile(
    r"(?:abrir|validar|consultar|menciona(?:r)?(?:\s+que)?(?:\s+se\s+debe)?|acceder\s+a)\s+"
    r"(?:el\s+|la\s+|los\s+)?(?:brf|hn|epc|matriz)|"
    r"\bBRF-\d+|\bHN0\d+|\bEPC-\d+|"
    r"\b(?:brf|hn\d{2,4}|epc-|matriz|caseforge|comportamiento|componente|trazabilidad|"
    r"group id|metadata|id t[eé]cnico)\b|"
    r"validar\s+brf|abrir\s+brf|el dispositivo queda",
    re.IGNORECASE,
)
_METADATA_EXPECTED_RE = re.compile(
    r"sesi[oó]n de prueba queda|permanece en el dispositivo|se mantiene el ecosistema|"
    r"no se modifican (?:puntos de interacci[oó]n|usuarios|mdp)|el brf queda|la hn queda|"
    r"conserva su trazabilidad|pertenece al brf|no se modifica el epc|"
    r"fila de matriz|fila aprobada|abrir\s+brf|validar\s+brf",
    re.IGNORECASE,
)
_TRUNCATED_COUNTRY_RE = re.compile(
    r"Hondur(?!as)|Guatemal(?!a)|Nicarag(?!ua)|Salvado(?!r)|Costa Ric(?!a)|"
    r"\b(?:El Salvador|Guatemala|Honduras|Nicaragua|Costa Rica)\b.{0,12}\.{3}",
    re.IGNORECASE,
)

_NEGATIVE_RE = re.compile(
    r"\bno\s+(?:se\s+)?(?:debe\s+)?(?:ser\s+)?(?:mostrad|mostrar|publicar|liberar|"
    r"habilitar|implementar|encontrar|incluir|permitir|estar presente|disponible)\b|"
    r"\bno\s+debe\s+estar|\bno\s+aparece|\bno\s+se\s+muestra|\bbaja del canal\b|"
    r"\bno\s+permitir",
    re.IGNORECASE,
)

_COUNTRY_RE = re.compile(
    r"^(el salvador|guatemala|honduras|nicaragua|costa rica|panam[aá]|m[eé]xico|mexico|"
    r"colombia|per[uú]|chile|argentina|ecuador|bolivia|paraguay|uruguay|venezuela|"
    r"rep[uú]blica dominicana|dominicana|brasil|brazil)$",
    re.IGNORECASE,
)

_CA_HEADER_RE = re.compile(r"criterios(?:\s+de aceptaci[oó]n)?\s*:?", re.IGNORECASE)
_EXTRACTO_RE = re.compile(r"Extracto:\s*(.*)$", re.DOTALL | re.IGNORECASE)

# Location phrase → tester action. Longest match first. Generic, not BRF-specific.
_LOCATION_SPECS: tuple[tuple[str, str, str], ...] = (
    (
        r"grilla de programaci[oó]n",
        "Consultar la grilla de programación.",
        "en la grilla de programación",
    ),
    (
        r"mosaico de canales|mosaico",
        "Consultar el mosaico de canales.",
        "en el mosaico de canales",
    ),
    (
        r"resultado(?:s)? de b[uú]squedas?|en el buscador|buscador",
        'Buscar "{subject}" en el Buscador.',
        "como resultado de búsqueda",
    ),
    (
        r"carrusel de canales de tv en vivo|carrusel de tv en vivo",
        "Consultar el carrusel de canales de TV en vivo.",
        "en el carrusel de canales de TV en vivo",
    ),
    (
        r"carrusel(?:es)? de categor",
        "Consultar los carruseles de categorías.",
        "en los carruseles de categorías",
    ),
    (
        r"plan selector",
        "Ingresar a Plan Selector.",
        "en Plan Selector",
    ),
    (
        r"landing comercial",
        "Acceder a la Landing Comercial.",
        "en la Landing Comercial",
    ),
    (
        r"player live",
        "Acceder al Player Live.",
        "en el Player Live",
    ),
    (
        r"epg full|epg mini|\bepg\b",
        "Consultar la EPG.",
        "en la EPG",
    ),
    (
        r"correo de bienvenida|correo electr[oó]nico|\bemail\b",
        "Consultar el correo de bienvenida.",
        "en el correo de bienvenida",
    ),
    (
        r"mi cuenta|suscripci[oó]n",
        "Acceder a Mi cuenta/Suscripción.",
        "en Mi cuenta/Suscripción",
    ),
    (
        r"home del add-?on",
        "Acceder al Home del add-on.",
        "en el Home del add-on",
    ),
    (r"\bcheckout\b", "Acceder al Checkout.", "en Checkout"),
    (r"\bticket\b", "Consultar el Ticket.", "en el Ticket"),
    (r"\bvcard\b", "Consultar la vCard.", "en la vCard"),
    (r"tv en vivo", "Acceder a la sección TV en vivo.", "en TV en vivo"),
    (r"\bhome\b", "Acceder al Home.", "en el Home"),
)

_INTERACTION_POINT_ACTIONS: dict[str, tuple[str, str]] = {
    "Buscador": ('Buscar "{subject}" en el Buscador.', "como resultado de búsqueda"),
    "Mosaico": ("Consultar el mosaico de canales.", "en el mosaico de canales"),
    "Plan Selector": ("Ingresar a Plan Selector.", "en Plan Selector"),
    "Landing Comercial": ("Acceder a la Landing Comercial.", "en la Landing Comercial"),
    "Player Live": ("Acceder al Player Live.", "en el Player Live"),
    "EPG Full": ("Consultar la EPG Full.", "en la EPG Full"),
    "EPG Mini": ("Consultar la EPG Mini.", "en la EPG Mini"),
    "Correo de bienvenida": ("Consultar el correo de bienvenida.", "en el correo de bienvenida"),
    "Checkout": ("Acceder al Checkout.", "en Checkout"),
    "Ticket": ("Consultar el Ticket.", "en el Ticket"),
    "vCard": ("Consultar la vCard.", "en la vCard"),
    "Mi cuenta/Suscripción": ("Acceder a Mi cuenta/Suscripción.", "en Mi cuenta/Suscripción"),
    "Home del add-on": ("Acceder al Home del add-on.", "en el Home del add-on"),
    "Carrusel Premium": ("Consultar el carrusel Premium.", "en el carrusel Premium"),
    "Carrusel Locales": ("Consultar el carrusel de canales locales.", "en el carrusel de canales locales"),
}


def source_text(preview: PreviewTestCase) -> str:
    evidence = preview.evidence or ""
    match = _EXTRACTO_RE.search(evidence)
    excerpt = (match.group(1) if match else evidence).strip()
    extras = "\n".join(
        part
        for part in (preview.behavior_title, preview.test_data, excerpt)
        if part
    )
    return extras


def is_negative_source(preview: PreviewTestCase, blob: str | None = None) -> bool:
    if preview.polarity == "negative":
        return True
    if preview.polarity == "positive":
        return False
    text = blob if blob is not None else source_text(preview)
    title = preview.behavior_title or ""
    return bool(_NEGATIVE_RE.search(text) or _NEGATIVE_RE.search(title))


def extract_subject(preview: PreviewTestCase) -> str | None:
    blob = source_text(preview)
    patterns = (
        r"canal\s+([A-ZÁÉÍÓÚÑ0-9][A-Za-zÁÉÍÓÚÑáéíóúñ0-9 .+-]{1,80}?)\s*\((\d+)\)",
        r"(?:baja|alta|retirar|agregar|incluir|publicar)\s+del canal\s+([A-ZÁÉÍÓÚÑ0-9][A-Za-zÁÉÍÓÚÑáéíóúñ0-9 .+-]{1,80})",
        r"canal\s+([A-ZÁÉÍÓÚÑ0-9][A-Za-zÁÉÍÓÚÑáéíóúñ0-9 .+-]{1,80}?)\s+(?:de la grilla|en la grilla)",
        r"add[ -]?on\s+([A-ZÁÉÍÓÚÑ0-9][A-Za-zÁÉÍÓÚÑáéíóúñ0-9 .+-]{1,80})",
        r"oferta\s+([A-ZÁÉÍÓÚÑ0-9][A-Za-zÁÉÍÓÚÑáéíóúñ0-9 .+-]{1,80})",
        r"logotipo del canal\s+([A-ZÁÉÍÓÚÑ0-9][A-Za-zÁÉÍÓÚÑáéíóúñ0-9 .+-]{1,80})",
    )
    for pattern in patterns:
        match = re.search(pattern, blob, re.IGNORECASE)
        if match:
            name = match.group(1).strip(" .,-")
            if len(match.groups()) > 1 and match.group(2):
                return f"{name} ({match.group(2)})"
            return name
    quoted = re.search(r"[«\"']([^\"'»]{2,80})[\"'»]", blob)
    if quoted:
        return quoted.group(1).strip()
    title = (preview.behavior_title or "").strip()
    title = re.sub(
        r"^(realizar|implementar|integrar|configurar|actualizar|habilitar|publicar)\s+",
        "",
        title,
        flags=re.I,
    )
    return title[:80] or None


def subject_label(subject: str | None) -> str:
    if not subject:
        return "el contenido declarado"
    return re.sub(r"\s*\(\d+\)\s*$", "", subject).strip() or subject


def extract_frequency(blob: str) -> str | None:
    match = re.search(r"frecuencia\s+(\d{1,5})", blob, re.I)
    return match.group(1) if match else None


def extract_prices(blob: str) -> list[str]:
    found = re.findall(r"(?:RD\$|US\$|\$)\s*\d[\d.,]*", blob)
    return list(dict.fromkeys(found))


def extract_countries(blob: str) -> list[str]:
    found: list[str] = []
    for line in re.split(r"[\n,;]+", blob or ""):
        for part in line.split(":"):
            text = re.sub(r"^[\-\*\d\.\)\s]+", "", part).strip().rstrip(".").strip()
            if _COUNTRY_RE.match(text):
                found.append(_canonical_country(text))
    return list(dict.fromkeys(found))


def _canonical_country(text: str) -> str:
    aliases = {
        "el salvador": "El Salvador",
        "guatemala": "Guatemala",
        "honduras": "Honduras",
        "nicaragua": "Nicaragua",
        "costa rica": "Costa Rica",
        "panamá": "Panamá",
        "panama": "Panamá",
        "méxico": "México",
        "mexico": "México",
    }
    return aliases.get(text.casefold(), text.strip())


def _join_es(values: list[str]) -> str:
    if not values:
        return ""
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + " y " + values[-1]


def extract_declared_list(blob: str, header: str) -> list[str]:
    match = re.search(rf"(?:^|\n){header}:\s*(.+)", blob, re.IGNORECASE)
    if not match:
        return []
    return [part.strip() for part in re.split(r"[;/]", match.group(1)) if part.strip()]


def execution_sets(preview: PreviewTestCase) -> list[tuple[str, list[str], str, str]]:
    """Dimensions with 2+ values stay on the same TC; the tester must repeat the checks.

    Does not create extra TCs. Does not invent a selector UI.
    """
    blob = source_text(preview)
    sets: list[tuple[str, list[str], str, str]] = []
    if not preview.user_type:
        users = [item for item in (preview.relevant_users or []) if item.strip()]
        if len(users) >= 2:
            listed = _join_es(users)
            sets.append(
                (
                    "usuario",
                    users,
                    (
                        f"Ejecutar los pasos siguientes para cada tipo de usuario declarado: {listed}. "
                        "La fuente no define un flujo de cambio de usuario; usar el contexto de cada perfil."
                    ),
                    "El resultado observable de cada paso siguiente se cumple para cada usuario del conjunto.",
                )
            )
    named_channels = extract_declared_list(preview.test_data or blob, "Canales")
    if len(named_channels) >= 2:
        listed = _join_es(named_channels)
        sets.append(
            (
                "canal",
                named_channels,
                (
                    f"Ejecutar los pasos siguientes para cada canal declarado: {listed}. "
                    "La fuente no define un selector adicional; usar el catálogo de cada canal."
                ),
                "El resultado observable de cada paso siguiente se cumple para cada canal del conjunto.",
            )
        )
    return sets


def atomic_criteria(blob: str) -> list[str]:
    after = blob
    header = _CA_HEADER_RE.search(blob)
    if header:
        after = blob[header.end() :]
    chunks: list[str] = []
    numbered = re.split(r"(?:^|\n)\s*\d+[.)]\s+", after)
    if len(numbered) > 1:
        chunks = [part.strip() for part in numbered[1:] if part.strip()]
    else:
        bullets = re.split(r"(?:^|\n)\s*[-•*]\s+", after)
        chunks = [part.strip() for part in bullets if part.strip()] if len(bullets) > 1 else []
    if not chunks:
        sentences = re.split(r"(?<=[.;])\s+", after)
        chunks = [part.strip() for part in sentences if len(part.strip()) > 20]
    expanded: list[str] = []
    for chunk in chunks:
        expanded.extend(_split_ni_locations(chunk))
    return [item for item in expanded if item and not _COUNTRY_RE.match(_strip_list_prefix(item))]


def _strip_list_prefix(text: str) -> str:
    return re.sub(r"^[\-\*\d\.\)\s]+", "", text).strip()


def _split_ni_locations(text: str) -> list[str]:
    """One CA naming two places becomes two checks on the same TC."""
    spans: list[tuple[int, int, str]] = []
    for pattern, _action, _loc in _LOCATION_SPECS:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        start, end = match.span()
        if any(start < prev_end and end > prev_start for prev_start, prev_end, _ in spans):
            continue
        spans.append((start, end, match.group(0)))
    if len(spans) >= 2:
        return [piece for _start, _end, piece in spans]
    return [text]


def _match_location(text: str) -> tuple[str, str] | None:
    lowered = text.lower()
    for pattern, action, location in _LOCATION_SPECS:
        if re.search(pattern, lowered):
            return action, location
    return None


def _subject_for_expected(subject: str | None, *, keep_freq: bool) -> str:
    if keep_freq and subject:
        return subject
    return subject_label(subject)


def _expected_for(text: str, *, subject: str | None, location: str, negative: bool) -> str:
    search = "resultado" in (location or "") or "búsqueda" in (location or "")
    name = _subject_for_expected(subject, keep_freq=not search)
    freq_value = extract_frequency(text)
    if not freq_value and subject:
        match = re.search(r"\((\d{1,5})\)\s*$", subject)
        freq_value = match.group(1) if match else None
    if freq_value and re.search(r"frecuencia", text, re.I):
        label = subject_label(subject)
        if negative:
            return f"La frecuencia {freq_value} correspondiente a {label} no está presente en Claro video."
        return f"La frecuencia {freq_value} correspondiente a {label} está presente en Claro video."
    if negative:
        loc = location
        if "categor" in location:
            loc = "en ningún carrusel de categoría"
        if "resultado" in loc:
            return f"{name} no aparece {loc}."
        return f"{name} no se muestra {loc}."
    cleaned = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if len(cleaned) > 20 and not _METADATA_EXPECTED_RE.search(cleaned):
        return cleaned + "."
    return f"{name} se muestra {location}."


def build_executable_steps(preview: PreviewTestCase) -> tuple[list[CandidateStep], list[str]]:
    warnings: list[str] = []
    blob = source_text(preview)
    negative = is_negative_source(preview, blob)
    subject = extract_subject(preview)
    criteria = atomic_criteria(blob)
    pairs: list[tuple[str, str]] = []
    used_actions: set[str] = set()
    for _dimension, _values, action, expected in execution_sets(preview):
        pairs.append((action, expected))
        used_actions.add(action)

    for criterion in criteria:
        if extract_frequency(criterion) and re.search(r"frecuencia", criterion, re.I):
            action = f"Verificar la frecuencia {extract_frequency(criterion)}."
            expected = _expected_for(criterion, subject=subject, location="", negative=negative)
            pairs.append((action, expected))
            used_actions.add(action)
            continue
        loc = _match_location(criterion)
        if loc:
            action_tpl, location = loc
            action = action_tpl.format(subject=subject_label(subject))
            expected = _expected_for(criterion, subject=subject, location=location, negative=negative)
            if action not in used_actions:
                pairs.append((action, expected))
                used_actions.add(action)
            continue
        if re.search(r"\b(?:mostrar|contratar|reproduc|logo|precio|oferta|medio de pago)\b", criterion, re.I):
            action = "Ejecutar el flujo descrito en el criterio de aceptación."
            if "logo" in criterion.lower():
                action = "Consultar el logo declarado en el punto de interacción indicado."
            if "precio" in criterion.lower() or "iva" in criterion.lower():
                action = "Consultar el precio mostrado en la oferta."
            if "medio de pago" in criterion.lower() or "mdp" in criterion.lower():
                action = "Seleccionar un medio de pago declarado."
            if "contratar" in criterion.lower():
                action = "Confirmar la contratación."
            expected = _expected_for(criterion, subject=subject, location="en la aplicación", negative=negative)
            key = action + expected
            if key not in used_actions:
                pairs.append((action, expected))
                used_actions.add(key)

    if not pairs:
        for point in preview.interaction_points:
            spec = _INTERACTION_POINT_ACTIONS.get(point)
            if not spec:
                action = f"Acceder a {point}."
                location = f"en {point}"
            else:
                action = spec[0].format(subject=subject_label(subject))
                location = spec[1]
            expected = _expected_for(preview.behavior_title, subject=subject, location=location, negative=negative)
            if action not in used_actions:
                pairs.append((action, expected))
                used_actions.add(action)

    if preview.channel == "Email" and not pairs:
        pairs.append(
            (
                "Consultar el correo de bienvenida.",
                _expected_for(blob or preview.behavior_title, subject=subject, location="en el correo de bienvenida", negative=negative),
            )
        )

    if preview.transactional and preview.mdp:
        action = "Seleccionar un medio de pago."
        expected = "El medio de pago seleccionado permite completar la contratación."
        if action not in used_actions:
            pairs.append((action, expected))

    if not pairs:
        warnings.append(
            f"{preview.brf_key} {preview.behavior_key}: HN/CA sin acciones ejecutables suficientes."
        )
        observation = (preview.behavior_title or "el comportamiento declarado").rstrip(".")
        if negative:
            expected = f"Se observa la ausencia declarada: {observation}."
        else:
            expected = f"Se observa en la aplicación: {observation}."
        pairs.append(("Ingresar a Claro video.", expected))

    steps: list[CandidateStep] = []
    for index, (action, expected) in enumerate(pairs, start=1):
        if _METADATA_STEP_RE.search(action) or _METADATA_EXPECTED_RE.search(expected):
            warnings.append(f"{preview.brf_key}: se omitió un paso de metadata ({action[:80]}).")
            continue
        steps.append(
            CandidateStep(
                step_number=len(steps) + 1,
                action=action[:2000],
                expected_result=expected[:4000],
            )
        )
    if not steps:
        warnings.append(f"{preview.brf_key} {preview.behavior_key}: 0 pasos ejecutables tras filtrar metadata.")
        steps.append(
            CandidateStep(
                step_number=1,
                action="Ingresar a Claro video.",
                expected_result="QC debe completar el criterio observable; la fuente no alcanzó para un paso específico.",
            )
        )
    # renumber
    for index, step in enumerate(steps, start=1):
        step.step_number = index
    return steps, warnings


def build_tester_test_data(preview: PreviewTestCase) -> str:
    blob = source_text(preview)
    lines: list[str] = []
    countries: list[str] = []
    if preview.country:
        countries = [preview.country]
    else:
        extracted = extract_countries(blob)
        if len(extracted) == 1:
            countries = extracted
    if countries:
        lines.append("País: " + countries[0])
    subject = extract_subject(preview)
    if subject:
        label = subject_label(subject)
        if extract_frequency(blob) or re.search(r"\bcanal\b", blob, re.I):
            lines.append("Canal: " + label)
        else:
            lines.append("Dato: " + label)
    freq = extract_frequency(blob)
    if freq:
        lines.append(f"Frecuencia: {freq}")
    prices = extract_prices(blob)
    if prices:
        lines.append("Precio: " + "; ".join(prices))
    if preview.device:
        lines.append(f"Dispositivo: {preview.device}")
    points = list(preview.interaction_points)
    if preview.channel == "Email" and "Email" not in points and "Correo de bienvenida" not in points:
        points.append("Email")
    if points:
        lines.append("Canal / Punto de interacción: " + ", ".join(points))
    if preview.user_type:
        lines.append("Usuario: " + preview.user_type)
    elif preview.relevant_users:
        users = [item for item in preview.relevant_users if item.strip()]
        if len(users) >= 2:
            lines.append("Usuario (conjunto, mismo TC): " + "; ".join(users))
            lines.append(
                "Ejecución usuario: repetir los pasos funcionales para cada usuario. "
                "La fuente no declara flujo de cambio de usuario."
            )
        elif users:
            lines.append("Usuario: " + users[0])
    if preview.access_path:
        lines.append("Camino de acceso: " + preview.access_path)
    if preview.mdp:
        lines.append("MDP: " + "; ".join(preview.mdp))
    if preview.test_data:
        for raw in preview.test_data.splitlines():
            text = raw.strip()
            if not text:
                continue
            lowered = text.lower()
            if lowered.startswith(
                ("brf:", "hn:", "epc", "behavior:", "id program", "id programa", "país", "superficies", "canal / punto")
            ) or lowered == "canal: email":
                continue
            if text not in lines:
                lines.append(text)
    return "\n".join(lines)


def execution_precondition(preview: PreviewTestCase) -> str:
    bits = ["Ingresar a Claro video"]
    if preview.device:
        bits.append(f"en {preview.device}")
    if preview.country:
        bits.append(f"con catálogo/cuenta de {preview.country}")
    if preview.user_type:
        bits.append("con usuario " + preview.user_type)
    elif preview.relevant_users:
        bits.append("con usuario " + ", ".join(preview.relevant_users))
    if preview.access_path:
        bits.append("iniciando la suscripción desde " + preview.access_path)
    return " ".join(bits) + "."
