"""Per-scenario LLM rewrite from Gherkin (FASE 8 FIX)."""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.config import settings
from app.schemas.case_generation import CandidateStep, CoverageUnit, GeneratedCaseCandidate
from app.services.case_composer import _QUOTED
from app.services.coverage_quality import normalize_precondition
from app.services.scenario_cases import (
    TECH_VERIFY_MARK,
    _navigation_steps,
    _walk_gwt,
    scenario_group_key,
    visible_outcome,
)

logger = logging.getLogger(__name__)

_GENERIC = re.compile(
    r"se observa el comportamiento|comportamiento (definido|esperado)|se verifica que\s*$",
    re.I,
)
_INFINITIVE = re.compile(
    r"^\s*(el usuario\s+)?(([a-záéíóúñ]+(ar|er|ir))|ir)\b",
    re.I,
)
_API = re.compile(r'"/[a-z]|/v\d/|status code|"\d{3}"|[A-Z][a-z]+_[A-Z][A-Za-z]+_', re.I)
_CAMEL = re.compile(r"[a-z]+[A-Z]")
_MARKERS = re.compile(r"[@<>]")
_FILLER_ACTION = re.compile(
    r"^\s*(el usuario\s+)?(observar|confirmar|verificar|validar|revisar|comprobar)\b",
    re.I,
)
_TECH_CLAUSE = re.compile(
    r"\b(status code|http|api|endpoint|header|json|response|request|payload|"
    r"GET|POST|PUT|PATCH|DELETE|authorization|content-type|flag|llave)\b|"
    r"/[a-z]",
    re.I,
)
_UX_CLAUSE = re.compile(
    r"\b(muestra|mostrar|bot[oó]n|pantalla|mensaje|tooltip|opci[oó]n|modal|men[uú]|"
    r"seleccion|presion|clic|ingresa|t[ií]tulo|texto visible)\b",
    re.I,
)
_JSON_LIT = {"true", "false", "null"}
_HEADER_NAME = re.compile(r"^[A-Z][A-Za-z]+(?:-[A-Z][A-Za-z]+)+$|^(Authorization|Accept)$")

_REWRITE_SYSTEM = """Eres analista QC. Redactas UN caso ejecutable a partir del Gherkin de UN escenario.
No decidas cobertura: no elimines el escenario. No copies el borrador determinista; es solo referencia opcional.

Plantilla del caso:
- Navegación: si el Background o los Given de la Feature tienen varios pasos de pantalla sin resultado propio, unifícalos en un paso "Ingresar a A > B > C".
- Acción: infinitivo (Seleccionar, Ingresar, Presionar, Completar). Una acción de usuario por paso.
- Resultado: observable en pantalla. Prohibido "Se observa el comportamiento…", "Se verifica que…" de relleno.
- Precondición: solo estados (sesión, perfil, contenido ya presente). Sin "Feature", sin API, sin endpoints.
- Referencia técnica: APIs, eventos, status, nombres de llave, identificadores con `_`, puntos o backticks. El identificador va completo, nunca recortado. Nunca en el título, la precondición, los pasos ni el resultado.
- Datos de prueba: solo de ESTE escenario. Si falta un dato que Jira no da, escribe exactamente `Definir por QC: <qué dato se necesita>`. No inventes valores.
- Textos entre comillas: solo si ese texto aparece literal en el Gherkin, la Feature o las tablas. No inventes textos.
- Un Then que describe un estado (fue, queda, está) se redacta como estado, sin comillas y sin "Se muestra el mensaje".
- Si el When es del usuario y el Then es un evento, el resultado es el comportamiento visible tomado del título, la Feature o la historia. El evento va en technical_reference con "verificación técnica: requiere herramienta (logs/monitoreo)".
- La precondición solo lleva estados del usuario o del contenido. Inicialización de SDK, contexto técnico y el título de la Feature van en technical_reference.
- Si el título se repite, distingue con " — " y una frase de hasta 6 palabras del título de la historia o de la Feature. Si no se repite, no agregues nada. No pegues la precondición.
- Si el Background o un Given de la Feature describe cómo llegar (abrir, ingresar, navegar, seleccionar), el primer paso es esa navegación y su resultado es la pantalla a la que se llega.

Textos de UI entre comillas: copia el literal exacto del Gherkin en la acción o en el resultado.
Si ui_phrases trae textos de más de una palabra, inclúyelos en algún paso (acción o resultado).
Sin APIs, endpoints, status ni nombres de llave en pasos o resultados.
No agregues pasos Observar/Confirmar/Verificar que repiten el resultado anterior.
No uses el título del escenario como resultado. Distingue casos con el mismo nombre añadiendo la condición en el título.
El resultado no debe copiar el título.

Si el Then es técnico (evento, servicio, API) y el When es del usuario, redacta regresión funcional: la acción del usuario y lo visible; el evento o servicio va en technical_reference con "verificación técnica: requiere herramienta (logs/monitoreo)".
Si el escenario enumera condiciones (Examples, lista de variantes), devuelve variants: [{condition, expected}].

Ejemplo 1 — navegación (dominio inventado: biblioteca municipal):
{"name": "Ver ficha del título reservado", "precondition": "El socio tiene una reserva activa.", "test_data": "", "technical_reference": "", "variants": [], "steps": [
  {"action": "Ingresar a Inicio > Catálogo > Reservas", "expected_result": "Se muestra la lista de reservas del socio."},
  {"action": "Seleccionar el título reservado", "expected_result": "Se muestra la ficha del título con el estado \\"Reservado\\"."}
]}

Ejemplo 2 — rama negativa recuperable:
{"name": "Registrar préstamo con carnet inválido y válido", "precondition": "El socio está en el mostrador de préstamos.", "test_data": "carnet inválido: 0000; carnet válido: 4821", "technical_reference": "", "variants": [
  {"condition": "carnet inválido", "expected": "Se muestra \\"Carnet no vigente\\"."},
  {"condition": "carnet válido", "expected": "Se muestra \\"Préstamo registrado\\"."}
], "steps": [
  {"action": "Completar el campo \\"Número de carnet\\" con un valor inválido", "expected_result": "Se muestra el mensaje \\"Carnet no vigente\\"."},
  {"action": "Completar el campo \\"Número de carnet\\" con un valor válido y seleccionar \\"Confirmar\\"", "expected_result": "Se muestra \\"Préstamo registrado\\"."}
]}

Ejemplo 3 — regresión funcional desde Then técnico:
{"name": "Devolver un título desde el mostrador", "precondition": "El socio tiene un préstamo abierto.", "test_data": "", "technical_reference": "evento loan.returned; verificación técnica: requiere herramienta (logs/monitoreo)", "variants": [], "steps": [
  {"action": "Seleccionar \\"Devolver\\" en el préstamo abierto", "expected_result": "Se muestra \\"Devolución registrada\\" y el título deja de aparecer en préstamos abiertos."}
]}

Responde JSON:
{"name": "...", "precondition": "...", "test_data": "...", "technical_reference": "...", "variants": [{"condition": "...", "expected": "..."}], "steps": [{"action": "...", "expected_result": "..."}]}
"""


def _is_ui_literal(text: str, clause: str = "", kind: str = "") -> bool:
    raw = (text or "").strip()
    if len(raw) <= 1:
        return False
    if "/" in raw or "=" in raw:
        return False
    if _MARKERS.search(raw) or "_" in raw or "." in raw:
        return False
    if _CAMEL.search(raw):
        return False
    if re.fullmatch(r"\d+", raw):
        return False
    if raw.lower() in _JSON_LIT:
        return False
    if raw.islower() and " " not in raw and re.fullmatch(r"[a-z]+", raw):
        return False
    if _HEADER_NAME.match(raw):
        return False
    if clause and _TECH_CLAUSE.search(clause) and not _UX_CLAUSE.search(clause):
        return False
    if kind == "then" and _TECH_CLAUSE.search(clause or "") and not _UX_CLAUSE.search(clause or ""):
        return False
    return True


def required_ui_literals(gherkin: str) -> list[str]:
    """Quoted UI text from When/Then of this scenario only."""
    found: list[str] = []
    for kind, clause in _walk_gwt(gherkin or ""):
        if kind not in {"given", "when", "then"}:
            continue
        for quote in _QUOTED.findall(clause):
            if _is_ui_literal(quote, clause, kind):
                found.append(quote.strip())
    return list(dict.fromkeys(found))


def validate_llm_case(
    llm: GeneratedCaseCandidate,
    gherkin: str,
    sibling_data: list[str],
    own_data: str = "",
    source: str = "",
) -> list[str]:
    reasons: list[str] = []
    if not llm.steps:
        return ["el caso no tiene pasos"]
    step_blob = " ".join(f"{step.action} {step.expected_result}" for step in llm.steps)
    corpus = source or gherkin or ""
    corpus_norm = _norm_text(corpus)
    source_quotes = {item.strip() for item in re.findall(r'["“]([^"”\n]+)["”]', corpus)}
    for index, step in enumerate(llm.steps, start=1):
        if not _INFINITIVE.match(step.action or ""):
            reasons.append(f"el paso {index} no empieza con verbo en infinitivo")
        if _GENERIC.search(step.expected_result or ""):
            reasons.append(f"el resultado del paso {index} es genérico")
        if _API.search(step.expected_result or ""):
            reasons.append(f"el resultado del paso {index} contiene un endpoint")
        if index > 1 and _FILLER_ACTION.match(step.action or ""):
            prev = _norm_text(llm.steps[index - 2].expected_result or "")
            current = _norm_text(step.expected_result or "")
            overlap = len(set(current.split()) - set(prev.split())) <= 2 if prev and current else False
            if prev and current and (current in prev or prev in current or overlap):
                reasons.append(f"el paso {index} es de relleno")
        if re.sub(r"\W+", " ", (step.expected_result or "").lower()).strip() == re.sub(
            r"\W+", " ", (llm.name or "").lower()
        ).strip():
            reasons.append(f"el resultado del paso {index} copia el título")
        reasons.extend(_visible_residue(f"{step.action} {step.expected_result}", corpus_norm, source_quotes))
    reasons.extend(_visible_residue(llm.precondition or "", corpus_norm, source_quotes))
    if _GLUED_TITLE.search(llm.name or "") and " — " not in (llm.name or ""):
        reasons.append("el título pega dos frases sin separador")
    for quote in required_ui_literals(gherkin):
        if quote.lower() not in step_blob.lower():
            reasons.append(f'falta el texto literal "{quote}" en algún paso')
    own = (own_data or "").lower()
    llm_data = (llm.test_data or "").lower()
    for other in sibling_data:
        token = (other or "").strip().lower()
        if len(token) < 4 or token in own:
            continue
        if token in llm_data:
            reasons.append("datos de prueba de otro escenario")
            break
    return list(dict.fromkeys(reasons))


_ANY_QUOTE = re.compile(r'["“]([^"”\n]*)["”]')
# Two phrases glued without " — ": a word and then a new sentence (El/La/Se…).
# A proper noun ("Apple Pay", "pantalla Ticket") is not this pattern.
_GLUED_TITLE = re.compile(r"[a-záéíóúñ]{3,}\s+(?=(?:El|La|Los|Las|Un|Una|Se)\s)")
_MESSAGE_WRAP = re.compile(
    r"\bse muestra el mensaje\s*[\"“]([^\"”\n]+)[\"”]",
    re.I,
)
_CUT_TAIL = re.compile(
    r"\s+(?!(?:el|la|los|las|un|una|de|del|al|en|con|por|para|que|si|no|se|su|"
    r"sus|es|ya|o|y|a|lo|le|les|mi|tu|mas|más|sin|como|este|esta|eso|esa)\b)"
    r"[a-záéíóúñ]{2,4}$",
    re.I,
)


def _visible_residue(text: str, corpus_norm: str, source_quotes: set[str]) -> list[str]:
    reasons: list[str] = []
    if "=" in (text or ""):
        reasons.append("un campo visible contiene '='")
    if ". ." in (text or ""):
        reasons.append("un campo visible contiene '. .'")
    message = bool(re.search(r"se muestra el mensaje", text or "", re.I))
    for quote in _ANY_QUOTE.findall(text or ""):
        if not quote:
            continue
        if quote[:1] in " ." or quote[-1:] in " .":
            reasons.append(f'comillas con resto "{quote}"')
        if len(quote.strip()) <= 2:
            reasons.append(f'texto entre comillas demasiado corto "{quote.strip()}"')
        if _norm_text(quote) and _norm_text(quote) not in corpus_norm:
            reasons.append(
                f'el texto entre comillas "{quote.strip()}" no existe en el Gherkin, la Feature ni las tablas'
            )
        if message and quote.strip() not in source_quotes:
            reasons.append(f'el resultado convierte un estado en el mensaje "{quote.strip()}"')
    return reasons


def _norm_text(text: str) -> str:
    return re.sub(r"\W+", " ", (text or "").lower()).strip()


def _repair_visible(text: str, corpus_norm: str, source_quotes: set[str]) -> str:
    """Drop invented quotes and rewrite a state Then that was turned into a UI message."""

    def _state(inner: str) -> str:
        state = inner.strip(" .")
        if not state:
            return ""
        return state[:1].upper() + state[1:] + ("" if state.endswith(".") else ".")

    def _message(match: re.Match[str]) -> str:
        inner = match.group(1).strip()
        if inner in source_quotes:
            return match.group(0)
        if _norm_text(inner) and _norm_text(inner) in corpus_norm:
            return _state(inner)
        return ""

    def _quote(match: re.Match[str]) -> str:
        inner = (match.group(1) or "").strip(" .")
        if len(inner) <= 2:
            return ""
        if inner in source_quotes or (_norm_text(inner) and _norm_text(inner) in corpus_norm):
            return f'"{inner}"'
        return ""

    cleaned = _MESSAGE_WRAP.sub(_message, text or "")
    cleaned = _ANY_QUOTE.sub(_quote, cleaned)
    cleaned = cleaned.replace(". .", " ")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([.;,])", r"\1", cleaned)
    return cleaned.strip(" ;,")


def _repair_llm_case(
    llm: GeneratedCaseCandidate,
    source: str,
    unit: CoverageUnit | None = None,
) -> None:
    corpus_norm = _norm_text(source)
    source_quotes = {item.strip() for item in re.findall(r'["“]([^"”\n]+)["”]', source or "")}
    name = llm.name or ""
    if " — " not in name:
        match = _GLUED_TITLE.search(name)
        if match:
            name = _CUT_TAIL.sub("", name[: match.end()].strip()).strip()
            llm.name = name
    for step in llm.steps or []:
        step.action = _repair_visible(step.action or "", corpus_norm, source_quotes)
        step.expected_result = _repair_visible(step.expected_result or "", corpus_norm, source_quotes)
    if llm.precondition:
        llm.precondition = _repair_visible(llm.precondition, corpus_norm, source_quotes)
    _repair_event_results(llm, unit)
    _dedupe_consecutive_actions(llm)


_EVENT_RESULT = re.compile(r"\b((?:no )?se emite|debe emitirse)\b", re.I)


def _repair_event_results(llm: GeneratedCaseCandidate, unit: CoverageUnit | None) -> None:
    if unit is None:
        return
    outcome = visible_outcome(getattr(unit, "scenario", None), getattr(unit, "story_summary", None))
    lifted: list[str] = []
    for step in llm.steps or []:
        expected = step.expected_result or ""
        if not _EVENT_RESULT.search(expected):
            continue
        lifted.append(expected.strip(" ;"))
        if outcome:
            step.expected_result = outcome
    if not lifted:
        return
    current = [part.strip() for part in (llm.technical_reference or "").split(";") if part.strip()]
    llm.technical_reference = "; ".join(dict.fromkeys([*current, *lifted, TECH_VERIFY_MARK]))


def _dedupe_consecutive_actions(llm: GeneratedCaseCandidate) -> None:
    kept: list[CandidateStep] = []
    for step in llm.steps or []:
        if kept and _norm_text(kept[-1].action or "") == _norm_text(step.action or ""):
            extra = (step.expected_result or "").strip()
            if extra and extra not in (kept[-1].expected_result or ""):
                kept[-1].expected_result = "; ".join(
                    part for part in (kept[-1].expected_result, extra) if part
                )
            continue
        kept.append(step)
    for index, step in enumerate(kept, start=1):
        step.step_number = index
    llm.steps = kept


def _ensure_navigation(candidate: GeneratedCaseCandidate, unit: CoverageUnit | None) -> None:
    if unit is None or not candidate.steps:
        return
    existing = {_norm_text(step.action or "") for step in candidate.steps}
    prefix: list[CandidateStep] = []
    for action, result in _navigation_steps(getattr(unit, "feature_background", None) or ""):
        if _norm_text(action) in existing:
            continue
        prefix.append(
            CandidateStep(
                step_number=1,
                action=action,
                expected_result=result,
                covered_unit_ids=list(candidate.covers or []),
            )
        )
        existing.add(_norm_text(action))
    if not prefix:
        return
    candidate.steps = [*prefix, *candidate.steps]
    for index, step in enumerate(candidate.steps, start=1):
        step.step_number = index


def strip_filler_steps(candidate: GeneratedCaseCandidate) -> None:
    kept: list[CandidateStep] = []
    for step in candidate.steps:
        if kept and _FILLER_ACTION.match(step.action or ""):
            continue
        if _norm_text(step.expected_result or "") == _norm_text(candidate.name or "") and step.action:
            step.expected_result = f"Se muestra el resultado de: {step.action}".rstrip(".") + "."
        kept.append(step)
    for index, step in enumerate(kept, start=1):
        step.step_number = index
    candidate.steps = kept
    cleaned = re.sub(r"\bFeature\b[^;]*", "", candidate.precondition or "", flags=re.I)
    cleaned = "; ".join(
        part.strip()
        for part in cleaned.split(";")
        if part.strip() and not re.search(r"\b(API|servicio|endpoint|response\.)\b", part, re.I)
    )
    candidate.precondition = normalize_precondition(cleaned)


def _lift_endpoints(candidate: GeneratedCaseCandidate) -> None:
    lifted: list[str] = []
    for step in candidate.steps or []:
        text = step.expected_result or ""
        if not _API.search(text):
            continue
        kept: list[str] = []
        for part in re.split(r"(?<=[.;])\s+", text):
            if _API.search(part):
                lifted.append(part.strip(" ;"))
            elif part.strip():
                kept.append(part.strip())
        step.expected_result = " ".join(kept).strip()
    if lifted:
        current = candidate.technical_reference or ""
        candidate.technical_reference = "; ".join(part for part in [current, *lifted] if part)


def _inject_required_literals(candidate: GeneratedCaseCandidate, gherkin: str) -> None:
    if not candidate.steps:
        return
    blob = " ".join(f"{step.action} {step.expected_result}" for step in candidate.steps).lower()
    missing = [quote for quote in required_ui_literals(gherkin) if quote.lower() not in blob]
    if not missing:
        return
    last = candidate.steps[-1]
    last.expected_result = (last.expected_result or "").rstrip(".") + ". " + " ".join(
        f'Se muestra "{item}".' for item in missing[:6]
    )


def _inject_ui_phrases(candidate: GeneratedCaseCandidate, source: str) -> None:
    if not candidate.steps:
        return
    blob = " ".join(
        [candidate.name or ""] + [f"{step.action} {step.expected_result}" for step in candidate.steps]
    ).lower()
    extra: list[str] = []
    for quote in _QUOTED.findall(source or ""):
        if not _is_ui_literal(quote):
            continue
        if quote.lower() in blob:
            continue
        extra.append(quote.strip())
        blob += " " + quote.lower()
    if extra:
        last = candidate.steps[-1]
        last.expected_result = (last.expected_result or "").rstrip(".") + ". " + " ".join(
            f'Se muestra "{item}".' for item in extra[:6]
        )


def polish_llm_candidates(candidates: list[GeneratedCaseCandidate]) -> list[GeneratedCaseCandidate]:
    for candidate in candidates:
        strip_filler_steps(candidate)
    return candidates


def llm_case_is_valid(
    base: GeneratedCaseCandidate,
    llm: GeneratedCaseCandidate,
    gherkin: str,
    sibling_data: list[str],
) -> bool:
    return not validate_llm_case(llm, gherkin, sibling_data, base.test_data or "")


def _format_variants(raw: Any, fallback: str | None) -> str | None:
    if isinstance(raw, list) and raw:
        lines = ["Condición | Resultado esperado"]
        for row in raw:
            if not isinstance(row, dict):
                continue
            condition = str(row.get("condition") or "").strip()
            expected = str(row.get("expected") or "").strip()
            if condition or expected:
                lines.append(f"{condition} | {expected}")
        if len(lines) > 1:
            return "\n".join(lines)
    return fallback


def _parse_rewrite(raw: str, base: GeneratedCaseCandidate) -> GeneratedCaseCandidate | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict) and "cases" in payload and payload["cases"]:
        payload = payload["cases"][0]
    if not isinstance(payload, dict):
        return None
    steps: list[CandidateStep] = []
    for index, row in enumerate(payload.get("steps") or [], start=1):
        if not isinstance(row, dict):
            continue
        steps.append(
            CandidateStep(
                step_number=index,
                action=str(row.get("action") or "").strip(),
                expected_result=str(row.get("expected_result") or row.get("expected") or "").strip(),
                covered_unit_ids=list(base.covers or []),
            )
        )
    copy = base.model_copy(deep=True)
    copy.name = str(payload.get("name") or base.name)[:120]
    precondition = str(payload.get("precondition") or "").strip()
    precondition = re.sub(r"\bFeature\b[^;]*", "", precondition, flags=re.I)
    precondition = re.sub(r"https?://\S+|/[a-z][a-z0-9_\-/]+", "", precondition, flags=re.I)
    precondition = re.sub(r"\s*;\s*;", ";", precondition).strip(" ;")
    copy.precondition = precondition or None
    copy.test_data = str(payload.get("test_data") or "").strip() or None
    copy.steps = steps
    copy.generation_origin = "llm"
    copy.covers = list(base.covers or [])
    copy.covered_unit_ids = list(base.covers or [])
    tech = str(payload.get("technical_reference") or "").strip() or base.technical_reference
    copy.technical_reference = tech
    copy.variant_table = _format_variants(payload.get("variants"), base.variant_table)
    copy.applicability = base.applicability
    copy.related_functionality = base.related_functionality
    copy.related_jira = base.related_jira
    return copy


def _call_llm(user_payload: dict[str, Any], timeout: float, feedback: str | None = None) -> str:
    from app.llm.client import generate

    user_content = json.dumps(user_payload, ensure_ascii=False)
    messages = [
        {"role": "system", "content": _REWRITE_SYSTEM},
        {"role": "user", "content": user_content},
    ]
    if feedback:
        messages.append(
            {
                "role": "user",
                "content": "El caso anterior fue rechazado. Corrige exactamente esto: " + feedback,
            }
        )
    return generate(
        messages,
        json_mode=True,
        temperature=0.1,
        model=settings.openai_model,
        timeout=timeout,
        api_key=str(getattr(settings, "llm_api_key", "") or settings.openai_api_key or ""),
    )


def _llm_eligible(unit: CoverageUnit) -> bool:
    if (unit.source_origin or "gherkin") != "gherkin":
        return False
    if (unit.applicability or "") == "na_ambiente":
        return False
    rules = unit.applied_rules or []
    if "verificacion-tecnica" in rules and not (unit.user_action or "").strip():
        return False
    return True


def _stub_from_unit(unit: CoverageUnit) -> GeneratedCaseCandidate:
    tech = "; ".join(part for part in (*(unit.technical_notes or []),) if part) or None
    if "verificacion-tecnica" in (unit.applied_rules or []) or "regresion-funcional" in (
        unit.applied_rules or []
    ):
        if tech and TECH_VERIFY_MARK not in tech:
            tech = f"{tech}; {TECH_VERIFY_MARK}"
        elif not tech:
            tech = TECH_VERIFY_MARK
    return GeneratedCaseCandidate(
        name=(unit.scenario or unit.behavior or "Escenario")[:120],
        description=unit.behavior or unit.scenario or "",
        precondition=None,
        steps=[],
        test_data=unit.extra_test_data,
        related_functionality=unit.artifact_key or None,
        related_jira=unit.story_key or unit.jira_key,
        related_rn=unit.rn_filename,
        evidence=unit.evidence or unit.scenario or "",
        justification="Redacción LLM desde Gherkin del escenario.",
        review_required=True,
        covers=[unit.coverage_id],
        covered_unit_ids=[unit.coverage_id],
        technical_reference=tech,
        applied_rules=list(unit.applied_rules or []),
        generation_origin="scenario-case",
        use_case_title=unit.story_summary,
        applicability=unit.applicability or "ejecutable",
        applicability_reason=unit.applicability_reason,
    )


def _mark_pending(candidate: GeneratedCaseCandidate, reason: str) -> GeneratedCaseCandidate:
    copy = candidate.model_copy(deep=True)
    copy.review_required = True
    copy.applicability_reason = reason
    copy.applied_rules = list(
        dict.fromkeys([*(copy.applied_rules or []), f"pendiente-qc:{reason[:80]}"])
    )
    return copy


def _mark_accepted(candidate: GeneratedCaseCandidate) -> GeneratedCaseCandidate:
    copy = candidate.model_copy(deep=True)
    copy.generation_origin = "llm"
    copy.review_required = True
    copy.applicability = "ejecutable"
    copy.applicability_reason = None
    copy.applied_rules = [
        rule
        for rule in (copy.applied_rules or [])
        if not str(rule).startswith("pendiente-qc")
    ]
    return copy


def _rewrite_one(
    base: GeneratedCaseCandidate,
    unit: CoverageUnit | None,
    story_summary: str,
    background: str,
    sibling_data: list[str],
    timeout: float,
) -> tuple[GeneratedCaseCandidate, dict[str, Any]]:
    gherkin = (unit.body if unit else "") or (base.evidence or "")
    payload = {
        "story_title": story_summary,
        "feature_background": background,
        "gherkin": gherkin[:4000],
        "tables": unit.extra_test_data if unit else base.test_data,
        "optional_draft": None,
        "required_ui_literals": required_ui_literals(gherkin),
        "ui_phrases": [
            quote.strip()
            for quote in _QUOTED.findall(f"{background}\n{gherkin}")
            if " " in (quote or "").strip() and _is_ui_literal(quote)
        ],
    }
    if base.steps:
        payload["optional_draft"] = {
            "name": base.name,
            "precondition": base.precondition,
            "steps": [{"action": step.action, "expected_result": step.expected_result} for step in base.steps],
            "test_data": base.test_data,
            "technical_reference": base.technical_reference,
            "variants": base.variant_table,
        }
    meta: dict[str, Any] = {
        "covers": list(base.covers or []),
        "scenario": (unit.scenario if unit else base.name) or "",
        "attempts": 0,
        "ok": False,
        "error": None,
        "ms": 0,
        "rejections": [],
    }
    started = time.perf_counter()
    last_error = None
    feedback = None
    for attempt in range(3):
        meta["attempts"] = attempt + 1
        try:
            raw = _call_llm(payload, timeout, feedback)
            llm = _parse_rewrite(raw, base)
            if llm is None:
                reasons = ["la respuesta no es un JSON de caso"]
            else:
                source = "\n".join(
                    part
                    for part in (
                        story_summary,
                        background,
                        gherkin,
                        (unit.extra_test_data if unit else "") or "",
                        base.test_data or "",
                    )
                    if part
                )
                _repair_llm_case(llm, source, unit)
                strip_filler_steps(llm)
                _lift_endpoints(llm)
                _inject_required_literals(llm, gherkin)
                reasons = validate_llm_case(llm, gherkin, sibling_data, base.test_data or "", source)
            if llm and not reasons:
                accepted = _mark_accepted(llm)
                _ensure_navigation(accepted, unit)
                _inject_ui_phrases(accepted, f"{background}\n{gherkin}\n{unit.extra_test_data if unit else ''}")
                meta["ok"] = True
                meta["ms"] = int((time.perf_counter() - started) * 1000)
                return accepted, meta
            meta["rejections"].append({"attempt": attempt + 1, "reasons": reasons})
            last_error = "; ".join(reasons) or "validator"
            feedback = last_error
        except Exception as exc:
            last_error = str(exc)[:200]
            meta["rejections"].append({"attempt": attempt + 1, "reasons": [last_error]})
            feedback = last_error
            logger.warning("scenario LLM rewrite failed attempt=%s error=%s", attempt + 1, last_error)
    meta["error"] = last_error
    meta["ms"] = int((time.perf_counter() - started) * 1000)
    if base.steps:
        return base.model_copy(deep=True), meta
    return _mark_pending(base, last_error or "LLM no redactó un caso válido"), meta


def rewrite_scenario_candidates(
    candidates: list[GeneratedCaseCandidate],
    inventory: list[CoverageUnit],
) -> tuple[list[GeneratedCaseCandidate], list[dict[str, Any]]]:
    provider = str(getattr(settings, "llm_provider", "") or "").strip().lower()
    key = str(getattr(settings, "llm_api_key", "") or getattr(settings, "openai_api_key", "") or "").strip()
    if provider == "none" or (provider != "ollama" and not key) or not inventory:
        return candidates, []
    by_cover: dict[str, GeneratedCaseCandidate] = {}
    for candidate in candidates:
        for cid in candidate.covers or candidate.covered_unit_ids or []:
            by_cover[cid] = candidate
    by_story: dict[str, list[str]] = {}
    for unit in inventory:
        key = unit.story_key or ""
        if unit.extra_test_data:
            by_story.setdefault(key, []).append(unit.extra_test_data)
    jobs: list[tuple[CoverageUnit, GeneratedCaseCandidate]] = []
    seen: set[str] = set()
    for unit in inventory:
        if not _llm_eligible(unit):
            continue
        group = scenario_group_key(unit)
        if group in seen:
            continue
        seen.add(group)
        base = by_cover.get(unit.coverage_id) or _stub_from_unit(unit)
        jobs.append((unit, base))
    if not jobs:
        return candidates, []
    concurrency = max(
        1,
        min(
            int(getattr(settings, "llm_scenario_concurrency", 8) or 8),
            int(getattr(settings, "llm_max_concurrency", 2) or 2),
        ),
    )
    timeout = float(getattr(settings, "llm_scenario_timeout", 45) or 45)
    rows: list[dict[str, Any]] = []
    rewritten_by_cover: dict[str, GeneratedCaseCandidate] = {}

    def work(unit: CoverageUnit, candidate: GeneratedCaseCandidate) -> tuple[CoverageUnit, GeneratedCaseCandidate, dict[str, Any]]:
        story = unit.story_key or ""
        siblings = [item for item in by_story.get(story, []) if item != (unit.extra_test_data or "")]
        background = (unit.feature_background or "").strip()
        rewritten, meta = _rewrite_one(
            candidate,
            unit,
            (unit.story_summary or "") or (candidate.use_case_title or ""),
            background,
            siblings,
            timeout,
        )
        return unit, rewritten, meta

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(work, unit, candidate) for unit, candidate in jobs]
        for future in as_completed(futures):
            unit, rewritten, meta = future.result()
            rewritten_by_cover[unit.coverage_id] = rewritten
            for cid in rewritten.covers or [unit.coverage_id]:
                rewritten_by_cover[cid] = rewritten
            rows.append(meta)

    out: list[GeneratedCaseCandidate] = []
    used: set[int] = set()
    for candidate in candidates:
        replacement = None
        for cid in candidate.covers or candidate.covered_unit_ids or []:
            if cid in rewritten_by_cover:
                replacement = rewritten_by_cover[cid]
                break
        if replacement is not None:
            marker = id(replacement)
            if marker not in used:
                out.append(replacement)
                used.add(marker)
        else:
            out.append(candidate)
    for unit, _base in jobs:
        replacement = rewritten_by_cover.get(unit.coverage_id)
        if replacement is not None and id(replacement) not in used:
            out.append(replacement)
            used.add(id(replacement))
    return out, rows
