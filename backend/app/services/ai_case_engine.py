"""Release Apps candidate-case engine.

Encodes the agreed QC generation rules as the system contract. The LLM (when configured)
proposes structured JSON; QC decides. Without an API key, an evidence-only fallback proposes
one candidate per Funcionalidad ticket extracted from the stored RN PDF — it does not invent
variants, metrics cases, or user eligibility.

Does not write TestCase/TestStep rows.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import settings
from app.schemas.case_generation import (
    CandidateStep,
    CoverageUnit,
    GeneratedCaseCandidate,
    GenerateCasesResponse,
    GenerationStats,
)
from app.services.case_composer import (
    attach_artifact_literals,
    compose_inventory,
    proposed_flows_for_llm,
    validate_composed_candidates,
)
from app.services.gherkin_coverage import (
    build_coverage_inventory,
    extract_technical,
    materialize_coverage_units,
    sanitize_user_text,
)
from app.services.coverage_quality import quality_gate
from app.services.executability import (
    apply_executability_gate,
    is_stable_generic_step,
    is_user_action,
    STABLE_GENERIC_STEP,
)
from app.services.jira_generation import (
    fetch_artifacts_for_keys,
    fetch_issuetypes_for_keys,
    keep_technical_epic_keys,
)
from app.services.qc_candidate_rules import apply_qc_rules
from app.services.release_note_analyzer import iter_rn_ticket_rows
from app.services.rn_epc_scope import (
    build_rn_scope_coverage,
    rn_keys_from_tickets,
    stamp_candidates,
    story_to_rn_map,
)
from app.services.rn_source_type import stamp_source_types

ENGINE_VERSION = "ai-v4"
logger = logging.getLogger(__name__)
_last_llm_meta: dict[str, int] = {}


def _llm_safe_text(value: object) -> str:
    """Strip API key material from log text. Never log Authorization."""
    text = str(value) if value is not None else ""
    key = (settings.openai_api_key or "").strip()
    if key:
        text = text.replace(key, "[redacted]")
    text = re.sub(r"(?i)(authorization\s*[:=]\s*)(\S+)", r"\1[redacted]", text)
    text = re.sub(r"(?i)bearer\s+\S+", "Bearer [redacted]", text)
    return text[:300]


_ENGINE_RULES = """
Eres el motor de generación de Test Cases de CaseForge para RELEASE APPS.
Alcance de esta etapa: generación BASE de casos del entregable. IA propone; QC decide.
NO persistir. NO generar Smoke. NO generar Regression. NO usar matrices de no-afectación.
NO estimar. NO generar Excel ni Zephyr Export. NO asignar Test Type
(Smoke/Regression/Happy Path/Negative/Edge); QC lo hará después.

Entradas permitidas: coverage_inventory + tickets/evidencia de FUNCIONALIDAD +
Jira/Gherkin de esas keys + histórico de casos del entregable (referencia, no verdad automática).
No recibes el RN/PDF completo ni tablas NCO, TRI, QA Bugs o QC Bugs.

Cruce de dos fuentes (Prompt v4):
- Fuente A: Technical Epic → Technical Stories hijas (JQL parent = epic).
  Verifica issuetype. Un key de dispositivo suele ser Epic, no una historia.
  Filtra summaries que empiecen con "Feature". El description trae Gherkin
  (Feature/Background/Scenario/Scenario Outline). Traduce a usuario final.
  customfield_19094 del BRFRE es resumen de alto nivel: NUNCA fuente única.
- Fuente B: customfield_19114 en User Stories = vocabulario de negocio (modales, botones, textos).
Si no hay criterios en ninguna fuente: no inventes. Un caso de validación básica de usuario final,
marcado basic_validation=true.

Reglas HANDOFF (obligatorias):
1. IA propone. QC decide.
2. No todo Jira se convierte en Test Case.
3. NO convertir automáticamente cada Scenario/Gherkin en un Test Case.
4. Variantes técnicas con el mismo comportamiento de usuario → AGRUPAR (orígenes,
   HTTP 400/401/404/500/503, flags, labels por operación, valores de rating equivalentes,
   serie/episodio si el flujo y el resultado son equivalentes, variantes de datos).
5. Variantes técnicas que cambian el comportamiento observable → SEPARAR.
6. No fabricar códigos HTTP ni variantes no sustentadas.
7. Scenario Outline / Examples: materializar solo condiciones funcionales independientes
   (plan, add-on, producto). Lo demás va a Datos de Prueba.
8. No hacer combinatoria automática.
9. Distintos puntos de entrada con el MISMO UX → un caso (orígenes en Datos de Prueba).
   Distintos puntos de entrada con UX distinto → casos independientes.
10. No dividir cada atributo en un Test Case; varios checks coherentes pueden ser un caso.
11. Aplicabilidad ≠ ejecutabilidad.
12. Aplicable pero requiere configuración → conservarlo, requires_condition=true.
    No usar "no es posible forzar escenario" para descartar.
13. Fuera de alcance explícito → no generar TC QC.
14. No asumir Rewrite/Charles para fabricar condiciones.
15. QC NO valida métricas/BI/analytics/eventos/logs/schemas/pipelines como Test Case.
    Conservar solo si hay comportamiento observable (ej. el pago no se bloquea).
16. No generar casos de proceso QA (nomenclatura, habilitar despliegue).
17. Histórico: similitud, patrones, duplicados. No es regla permanente.
18. Duplicados del histórico: possible_duplicate_of (referencia). En la MISMA corrida,
    consolidar solo si hay equivalencia funcional (mismo objetivo, misma acción del
    usuario, misma condición, mismo resultado observable, mismo contexto). Conservar
    todas las claves Jira/Scenario en evidencia. No dejar duplicados marcados.
19. Cada candidato explica por qué existe (justification).
20. No asumir configuraciones que Jira solo menciona (ej. module_version=v8).
21. No inferir elegibilidad sin evidencia.
22. QC valida como usuario final. Steps = acciones de usuario. Expected = lo que el usuario observa.
    Revisar de forma independiente nombre, Test Step y Resultado Esperado.
    "El sistema consulta/invoca/ejecuta un servicio" NO es Resultado Esperado.
    Traducir a la consecuencia en pantalla; el detalle técnico va a Datos de Prueba.
    No eliminar cobertura solo porque el origen sea técnico.
    Clasifica cada Scenario: A observable, B condición, C implementación, D métrica,
    E proceso QA, F fuera de alcance, G técnico CON consecuencia observable.
    No materialices C/D/E/F. No uses frases comodín para salvar un Scenario técnico.
    Cada unidad trae coverage_id, test_intent, condition, user_action y observable_then.
    Identifica la condición que hace único al escenario (Given, título, test_intent).
    Esa condición va en precondition o test_data, NUNCA dentro del Step como
    "el usuario recorre la experiencia cuando…".
    CoverageUnit es la fuente de cobertura. Cada TC DEBE declarar covered_unit_ids
    con los coverage_id que cubre. Una unidad no puede desaparecer sin explicación.
    covered_unit_ids no es solo trazabilidad: fija la evidencia que el TC debe representar.
    Hay dos operaciones distintas:
    COMPOSICIÓN: unidades consecutivas del mismo flujo (el Given de B equivale a la
    acción o al Then de A en la misma historia) se convierten en PASOS de un mismo caso,
    aunque cambie la acción del usuario. Recibes "proposed_flows" como propuesta.
    EQUIVALENCIA: dos unidades que verifican lo mismo (mismo resultado esperado
    normalizado) se deduplican o se pliegan como Datos de prueba. Nunca unas
    historias distintas. Nunca unes flujos de distintas EPCs.
    Varios Then del mismo When = un paso con varios resultados.
    Variantes de dato con el mismo esperado = un caso, variantes en Datos de prueba.
    Variantes con esperado distinto = un caso por variante.
    Cambia la precondición no alcanzable desde el flujo = caso separado.
    Cambia la intención principal = caso separado.
    Rama negativa recuperable (dato inválido → mensaje → reintento → éxito) = mismo caso.
    Resultados excluyentes no recuperables = casos que pueden compartir pasos previos.
    Prueba de bolsillo: si dos resultados se verifican en la misma ejecución, sin
    cambiar configuración ni cuenta, van en el mismo caso.
    Fidelidad de user_action: el paso usa esa acción, en infinitivo ("Seleccionar…").
    NUNCA uses "El usuario ingresa al flujo correspondiente."
    Si una unidad no tiene acción soportable, el caso queda pendiente de revisión QC
    con el motivo; no inventes el paso.
    Expected = únicamente el resultado observable (Then/AC/observable_then) de las units.
    Expected NUNCA describe una acción del usuario.
    PROHIBIDO en Expected: "El usuario selecciona la opción.", "El usuario presiona...",
    "El usuario navega...", "El usuario ingresa...".
    NO uses "Se observa el comportamiento definido." ni variantes.
    NO repitas la condición como si fuera el resultado.
    NO introduzcas API, status, JSON ni endpoint en Step ni Expected, salvo que ese
    observable esté explícitamente exigido por Then/AC/observable_then de la unit.
    Si la fuente no da un observable suficiente, no inventes el Expected.
    Varios observables funcionalmente inseparables de la misma unidad pueden ir en el mismo Expected.
    Una unit queda cubierta solo si: (1) está en covered_unit_ids, (2) el TC representa
    su comportamiento, (3) si tiene user_action explícito esa acción está en el Step,
    (4) el observable corresponde a esa unit.
    NO inventes acciones, condiciones, resultados ni datos de prueba no soportados.
    NO inventes pantallas, textos ni condiciones fuera de Gherkin, Coverage Unit, Jira o RN.
23. Títulos funcionales, no "Validar invocación/API/status 503".
    Título, condición, step y resultado deben ser el mismo flujo.
24. Prioridad: BLOCKER (acceso, playback, bookmark, lineal, transacción, parental,
    compras, cancelación, NPVR, TimeShift, perfiles) o CRITICAL (navegación, search,
    vcard, resto). Nunca dejar vacía si el caso es clasificable.
25. Confianza high solo si el UX está claro en RN/Jira sin asumir implementación.
    Configuración no comprobable → medium/low.

Lenguaje:
- Test Step y Resultado Esperado = acción/observación de usuario final.
- NUNCA endpoints, GET/POST, status codes, nombres de parámetro, invocaciones internas.
- Eso va en test_data (Datos de Prueba).
- HTTP explícitos: trazabilidad en test_data. Si 400/401/404/429/500/503 producen el mismo
  comportamiento (ej. no mostrar el componente) → UN caso. Si el usuario ve algo distinto → SEPARAR.

Casos de estudio (principios, no recetas inventadas):
- STVCL-2234: no explotar un ticket en decenas de variantes técnicas; agrupar mismo UX;
  separar solo con cambio de comportamiento; descartar lo sin sustento.
- WEBCL-3785, WEBCL-3723, WEBCL-3725, WEBCL-3844, WEBCL-3846, WEBCL-3779:
  cubrir escenarios funcionales evidentes, no 1 Jira = 1 caso.

La fuente principal de QUÉ cubrir es coverage_inventory (unidades A/G).
NO resumas el RN a un caso por fila de Funcionalidad.
NO inventes un número objetivo de casos. El número es consecuencia de los flujos.
Compón unidades consecutivas del mismo flujo como pasos. Equivalencia solo si
verifican lo mismo. No un caso por endpoint, HTTP status o Jira técnico.
Cada candidato DEBE listar covered_unit_ids. Cada paso DEBE listar
steps[].covered_unit_ids. NO dejes unidades ejecutables sin cubrir.
Las únicas fuentes permitidas para generar casos mediante LLM son coverage_inventory
y la evidencia/tickets de FUNCIONALIDAD. Ignora NCO, TRI, QA Bugs y QC Bugs.
"""

_JSON_INSTRUCTIONS = """
Responde SOLO con un JSON de la forma:
{"candidates":[{
  "name": string,
  "description": string,
  "precondition": string|null,
  "requires_condition": boolean,
  "steps":[{"step_number":int,"action":string,"expected_result":string,"test_data":string|null,"covered_unit_ids":["COV-001"]}],
  "test_data": string|null,
  "related_functionality": string|null,
  "related_jira": string|null,
  "related_rn": string|null,
  "evidence": string,
  "justification": string,
  "possible_duplicate_of": string|null,
  "confidence": "high"|"medium"|"low",
  "review_required": true,
  "basic_validation": boolean,
  "covered_unit_ids": ["COV-001"]
}]}
Sin markdown, sin texto fuera del JSON.
Título: comportamiento + contexto, sin prefijos Validar/Verificar/Scenario.
Paso: infinitivo de acción de usuario que avanza el flujo. Nunca
"El usuario ingresa al flujo correspondiente."
Resultado: lo que el tester ve. Textos de UI entre comillas de Jira se copian literales.
Cada paso declara covered_unit_ids. Cada unidad ejecutable queda en al menos un paso.
Usa proposed_flows como propuesta de composición; puedes ajustar redacción, no inventar acciones.
Compón unidades consecutivas del mismo flujo como pasos. Equivalencia solo si el
esperado normalizado es idéntico. No mezcles historias ni EPCs.
related_functionality = key de la Technical Epic. related_jira = Story.
"""

_METRICS_RE = re.compile(r"\bm[eé]tric|\banalytics\b|\bga4\b|\bfirebase\b|\bmdp\b", re.IGNORECASE)
_ISSUE_KEY = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
_ISSUE_KEY_ONLY = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")

_LAST_RESORT_EXCLUDE = re.compile(
    r"setup de m[eé]tricas|\b(m[eé]tric|analytics|telemetr)|"
    r"alta de llaves|llaves de configuraci[oó]n en el dispositivo|"
    r"metadata:\s*alta|module_version|"
    r"\bsmartlib\b|\bnanocdn\b|"
    r"inicializa(r)? (el )?(player|engine|m[oó]dulo)|"
    r"\binitialize\b|\bload module\b|\bset config\b",
    re.IGNORECASE,
)
_LAST_RESORT_ALLOW = re.compile(
    r"pantalla|panel|navegaci|reproduc|\blive\b|\bvod\b|"
    r"grabar|grabaci[oó]n|perfil|bot[oó]n|control player|"
    r"usuario|experiencia|migraci[oó]n|marca|m[oó]dulo|"
    r"canal|gu[ií]a|ticket|modal|carrusel|player|epg|"
    r"timeshift|npvr|login|registro|paypal|pago|checkout|"
    r"banner|home|men[uú]|activaci[oó]n|\bactivar\b|\bhbo\b|"
    r"visible para el usuario",
    re.IGNORECASE,
)


def last_resort_applies(cell_text: str, ticket_id: str = "") -> bool:
    """True when RN functionality may yield one gated basic_validation case.

    Excludes metrics, key provisioning, and libraries without UX. Does not invent
    screens; the candidate only restates the RN cell.
    """
    blob = f"{ticket_id} {cell_text}"
    if _LAST_RESORT_EXCLUDE.search(blob):
        return False
    return bool(_LAST_RESORT_ALLOW.search(blob))


def _tickets_by_section(pdf_bytes: bytes, filename: str = "") -> dict[str, list[tuple[str, str]]]:
    """Section -> [(ticket_id, cell_text), ...] via the shared RN table walk."""
    buckets: dict[str, list[tuple[str, str]]] = {
        "functionality": [],
        "nco": [],
        "tri": [],
        "qa_qc": [],
    }
    seen: dict[str, set[str]] = {key: set() for key in buckets}
    for ticket_id, cell_text, bucket in iter_rn_ticket_rows(pdf_bytes, filename):
        if bucket not in buckets or ticket_id in seen[bucket]:
            continue
        seen[bucket].add(ticket_id)
        buckets[bucket].append((ticket_id, cell_text))
    return buckets


def _looks_like_metrics(text: str) -> bool:
    return bool(_METRICS_RE.search(text))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _duplicate_of(name: str, jira: str | None, existing: list[dict[str, str]]) -> str | None:
    name_n = _normalize(name)
    jira_n = (jira or "").strip().upper()
    for row in existing:
        other_name = _normalize(row.get("test_case_name") or "")
        other_id = (row.get("test_case_id") or "").strip()
        blob = _normalize(f"{row.get('test_case_name','')} {row.get('description','')}")
        if jira_n and jira_n in blob.upper():
            return other_id or row.get("test_case_name")
        if other_name and (other_name == name_n or other_name in name_n or name_n in other_name):
            return other_id or row.get("test_case_name")
    return None


def _candidate_from_functionality_ticket(
    ticket_id: str,
    cell_text: str,
    rn_filename: str,
    existing: list[dict[str, str]],
) -> GeneratedCaseCandidate | None:
    summary = cell_text
    if ":" in cell_text:
        summary = cell_text.split(":", 1)[1].strip()
    needs_config = bool(
        re.search(r"llave|configuraci[oó]n|flag|setup|habilit", cell_text, re.IGNORECASE)
    )
    name = f"Validar {summary[:120]}" if summary else f"Validar {ticket_id}"
    dup = _duplicate_of(name, ticket_id, existing)
    return GeneratedCaseCandidate(
        name=name[:250],
        description=summary[:2000] or cell_text[:2000],
        precondition=(
            (f"{summary}. " if summary else "")
            + "Validación básica: el RN no describe un paso de usuario ni un resultado UI específico."
        ),
        requires_condition=needs_config,
        steps=[
            CandidateStep(
                step_number=1,
                action=STABLE_GENERIC_STEP,
                expected_result=(
                    f"Se observa el comportamiento definido para la funcionalidad descrita en el RN "
                    f"({summary[:180]}). Validación básica: el RN no describe un paso de usuario ni un resultado UI específico."
                    if summary
                    else "Validación básica: el RN no describe un paso de usuario ni un resultado UI específico."
                ),
            )
        ],
        related_functionality=ticket_id,
        related_jira=ticket_id,
        related_rn=rn_filename,
        evidence=cell_text[:2000],
        justification=(
            "Último recurso sin Gherkin/AC de Jira: validación básica de usuario final "
            "a partir del ticket de Funcionalidad del RN. No es cobertura completa del entregable."
        ),
        possible_duplicate_of=dup,
        confidence="low",
        review_required=True,
        basic_validation=True,
        priority="CRITICAL",
        generation_origin="nuevo-functionality",
        source_type="functionality",
    )


def _from_evidence(
    pdf_bytes: bytes | None,
    rn_filename: str,
    existing: list[dict[str, str]],
) -> list[GeneratedCaseCandidate]:
    if not pdf_bytes:
        return []
    tickets = _tickets_by_section(pdf_bytes, rn_filename)
    candidates: list[GeneratedCaseCandidate] = []
    for ticket_id, cell_text in tickets.get("functionality", []):
        if not last_resort_applies(cell_text, ticket_id):
            continue
        candidate = _candidate_from_functionality_ticket(ticket_id, cell_text, rn_filename, existing)
        if candidate is not None:
            candidates.append(candidate)
    return apply_qc_rules(candidates)


_FIDELITY_STOPWORDS = {
    "usuario",
    "cuando",
    "entonces",
    "desde",
    "para",
    "con",
    "una",
    "unas",
    "unos",
    "este",
    "esta",
    "esto",
    "selecciona",
    "seleccionar",
    "seleccion",
    "ingresa",
    "ingresar",
    "presiona",
    "presionar",
    "intenta",
    "intentar",
    "boton",
    "botón",
    "flujo",
    "corresponding",
}


def _fidelity_norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _fidelity_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-záéíóúñ0-9]{3,}", _fidelity_norm(text))
        if token not in _FIDELITY_STOPWORDS
    }


def _explicit_user_action(unit: CoverageUnit) -> str:
    raw = (unit.user_action or "").strip()
    if not raw or is_stable_generic_step(raw):
        return ""
    return raw


def _step_actions(candidate: GeneratedCaseCandidate) -> str:
    return " ".join(step.action or "" for step in (candidate.steps or []))


def _action_represents_unit(step_action: str, user_action: str) -> bool:
    if not user_action.strip():
        return True
    if is_stable_generic_step(step_action):
        return False
    unit_tokens = _fidelity_tokens(user_action)
    step_tokens = _fidelity_tokens(step_action)
    unit_n = _fidelity_norm(user_action)
    step_n = _fidelity_norm(step_action)
    if unit_n and (unit_n in step_n or step_n in unit_n):
        return True
    if not unit_tokens:
        return False
    overlap = unit_tokens & step_tokens
    needed = len(unit_tokens) if len(unit_tokens) <= 2 else max(1, (len(unit_tokens) + 1) // 2)
    return len(overlap) >= needed


def _source_has_matching_when(action: str, units: list[CoverageUnit]) -> bool:
    if is_stable_generic_step(action) or not is_user_action(action):
        return True
    clauses: list[str] = []
    for unit in units:
        blob = "\n".join(
            filter(
                None,
                [
                    unit.user_action,
                    unit.evidence,
                    unit.body,
                    unit.scenario,
                    unit.test_intent,
                ],
            )
        )
        for line in re.split(r"[\n.;]+", blob):
            clause = line.strip()
            if clause:
                clauses.append(clause)
    for clause in clauses:
        if not is_user_action(clause):
            continue
        if _action_represents_unit(action, clause) or _action_represents_unit(clause, action):
            return True
    return False


_EXPECTED_IS_USER_ACT = re.compile(
    r"^\s*(el usuario\s+)?(selecciona|seleccionar|presiona|presionar|navega|navegar|"
    r"ingresa|ingresar|abre|abrir|cierra|cerrar|da clic|intenta|intentar|"
    r"cancela|cancelar|graba|grabar)\b",
    re.IGNORECASE,
)


def _expected_describes_user_action(text: str) -> bool:
    bare = (text or "").strip()
    if not bare:
        return False
    return bool(_EXPECTED_IS_USER_ACT.search(bare))


def _observable_from_units(units: list[CoverageUnit]) -> str:
    for unit in units:
        for item in unit.observable_then or []:
            text = (item or "").strip()
            if text and not is_user_action(text):
                return text
        scenario = (unit.scenario or "").strip()
        if scenario and not is_user_action(scenario):
            return scenario
    return ""


def enforce_llm_unit_fidelity(
    candidates: list[GeneratedCaseCandidate],
    inventory: list[CoverageUnit],
) -> list[GeneratedCaseCandidate]:
    """Post-LLM fidelity only (after _keep_llm_functionality_candidates).

    A) Explicit user_action not represented in When: rewrite When, or drop that id
       from covered_unit_ids.
    B) Empty user_action with an unsupported specific When: controlled generic step.
    C) Expected that is a user action: replace with observable_then when present.
    """
    by_id = {unit.coverage_id: unit for unit in inventory}
    kept: list[GeneratedCaseCandidate] = []
    for candidate in candidates:
        ids = list(candidate.covered_unit_ids or candidate.covers or [])
        action_blob = _step_actions(candidate)
        faithful: list[str] = []
        mismatched: list[tuple[str, str]] = []
        for cid in ids:
            unit = by_id.get(cid)
            if unit is None:
                continue
            explicit = _explicit_user_action(unit)
            if not explicit:
                faithful.append(cid)
            elif _action_represents_unit(action_blob, explicit):
                faithful.append(cid)
            else:
                mismatched.append((cid, explicit))
        if mismatched:
            unique_actions = list(dict.fromkeys(action for _, action in mismatched))
            if not faithful and len(unique_actions) == 1 and candidate.steps:
                candidate.steps[0].action = unique_actions[0]
                faithful = [cid for cid, _ in mismatched]
        if not faithful:
            logger.info(
                "LLM candidate rejected: name=%s reason=unfaithful-coverage covers=%s",
                candidate.name[:120],
                ids,
            )
            continue
        units = [by_id[cid] for cid in faithful if cid in by_id]
        explicit_units = [unit for unit in units if _explicit_user_action(unit)]
        if explicit_units and candidate.steps:
            shared = list(
                dict.fromkeys(_explicit_user_action(unit) for unit in explicit_units)
            )
            if len(shared) == 1 and not _action_represents_unit(
                _step_actions(candidate), shared[0]
            ):
                candidate.steps[0].action = shared[0]
        empty_action_units = [unit for unit in units if not _explicit_user_action(unit)]
        if empty_action_units and len(empty_action_units) == len(units) and candidate.steps:
            current = candidate.steps[0].action or ""
            if (
                current
                and not is_stable_generic_step(current)
                and is_user_action(current)
                and not _source_has_matching_when(current, units)
            ):
                candidate.steps[0].action = STABLE_GENERIC_STEP
        for step in candidate.steps or []:
            expected = (step.expected_result or "").strip()
            if expected and _expected_describes_user_action(expected):
                replacement = _observable_from_units(units)
                if replacement:
                    step.expected_result = replacement
                else:
                    logger.info(
                        "LLM candidate rejected: name=%s reason=expected-is-user-action",
                        candidate.name[:120],
                    )
                    faithful = []
                    break
        if not faithful:
            continue
        candidate.covers = faithful
        candidate.covered_unit_ids = faithful
        kept.append(candidate)
    return kept


def _parse_llm_candidates(payload: dict[str, Any], existing: list[dict[str, str]]) -> list[GeneratedCaseCandidate]:
    raw_list = payload.get("candidates") if isinstance(payload, dict) else None
    if not isinstance(raw_list, list):
        return []
    out: list[GeneratedCaseCandidate] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        try:
            candidate = GeneratedCaseCandidate.model_validate(item)
        except Exception:
            continue
        if _looks_like_metrics(candidate.name) and not candidate.related_functionality:
            continue
        raw_steps = item.get("steps") if isinstance(item.get("steps"), list) else []
        for index, step in enumerate(candidate.steps):
            original = f"{step.action} {step.expected_result}"
            tech = extract_technical(original)
            step.action = sanitize_user_text(step.action) or step.action
            step.expected_result = sanitize_user_text(step.expected_result) or step.expected_result
            if index < len(raw_steps) and isinstance(raw_steps[index], dict):
                ids = raw_steps[index].get("covered_unit_ids") or raw_steps[index].get("covers") or []
                if isinstance(ids, str):
                    ids = [ids]
                if isinstance(ids, list):
                    step.covered_unit_ids = [str(cid).strip() for cid in ids if str(cid).strip()]
            if tech and not step.test_data:
                step.test_data = tech
            if tech and not candidate.test_data:
                candidate.test_data = tech
        candidate.review_required = True

        def _coverage_ids(value: Any) -> list[str]:
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, list):
                return []
            return [str(cid).strip() for cid in value if str(cid).strip()]

        declared = _coverage_ids(item.get("covered_unit_ids")) or _coverage_ids(
            item.get("covers")
        )
        if item.get("covered_unit_ids") and item.get("covers"):
            declared = list(
                dict.fromkeys(
                    _coverage_ids(item.get("covered_unit_ids"))
                    + _coverage_ids(item.get("covers"))
                )
            )
        candidate.covers = declared
        candidate.covered_unit_ids = declared
        if not candidate.possible_duplicate_of:
            candidate.possible_duplicate_of = _duplicate_of(
                candidate.name, candidate.related_jira, existing
            )
        out.append(candidate)
    return apply_qc_rules(out)


def _functionality_tickets_for_llm(
    tickets: dict[str, list[tuple[str, str]]],
) -> list[dict[str, str]]:
    return [
        {"jira": tid, "evidence": text}
        for tid, text in tickets.get("functionality", [])
    ]


def _jira_artifacts_for_llm(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        children: list[dict[str, Any]] = []
        for child in art.get("children") or []:
            if not isinstance(child, dict):
                continue
            children.append(
                {
                    "key": child.get("key"),
                    "issuetype": child.get("issuetype"),
                    "summary": child.get("summary"),
                    "description": (child.get("description") or "")[:4000],
                    "acceptance_criteria": (child.get("acceptance_criteria") or "")[:1500],
                }
            )
        compact.append(
            {
                "key": art.get("key"),
                "issuetype": art.get("issuetype"),
                "summary": art.get("summary"),
                "description": (art.get("description") or "")[:4000],
                "acceptance_criteria": (art.get("acceptance_criteria") or "")[:1500],
                "children": children,
            }
        )
    return compact


def _llm_functionality_keys(
    tickets: dict[str, list[tuple[str, str]]],
    inventory: list[CoverageUnit],
    artifacts: list[dict[str, Any]] | None = None,
) -> set[str]:
    """RN Funcionalidad keys only. Technical Stories are not EPC identity."""
    del artifacts
    keys = set(rn_keys_from_tickets(tickets))
    for unit in inventory:
        if unit.rn_key:
            keys.add(unit.rn_key.strip().upper())
    return keys


def _llm_jira_trace_keys(
    tickets: dict[str, list[tuple[str, str]]],
    inventory: list[CoverageUnit],
    artifacts: list[dict[str, Any]] | None = None,
) -> set[str]:
    keys = set(_llm_functionality_keys(tickets, inventory, artifacts))
    for unit in inventory:
        if unit.jira_key:
            keys.add(unit.jira_key.strip().upper())
        if unit.story_key:
            keys.add(str(unit.story_key).strip().upper())
    for art in artifacts or []:
        if art.get("key"):
            keys.add(str(art["key"]).strip().upper())
        for child in art.get("children") or []:
            if isinstance(child, dict) and child.get("key"):
                keys.add(str(child["key"]).strip().upper())
    return keys


def _label_key(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _remember_summary(index: dict[str, set[str]], summary: str, key: str) -> None:
    label = _label_key(summary)
    token = (key or "").strip().upper()
    if not label or not token:
        return
    index.setdefault(label, set()).add(token)


def _summary_index(
    tickets: dict[str, list[tuple[str, str]]],
    artifacts: list[dict[str, Any]],
    inventory: list[CoverageUnit],
) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for tid, text in tickets.get("functionality", []):
        _remember_summary(index, text, tid)
        _remember_summary(index, tid, tid)
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        _remember_summary(index, str(art.get("summary") or ""), str(art.get("key") or ""))
        _remember_summary(index, str(art.get("key") or ""), str(art.get("key") or ""))
        for child in art.get("children") or []:
            if not isinstance(child, dict):
                continue
            _remember_summary(index, str(child.get("summary") or ""), str(child.get("key") or ""))
            _remember_summary(index, str(child.get("key") or ""), str(child.get("key") or ""))
    for unit in inventory:
        _remember_summary(index, unit.behavior, unit.rn_key or unit.jira_key or "")
        _remember_summary(index, unit.scenario, unit.jira_key or unit.rn_key or "")
        _remember_summary(index, unit.traceability, unit.rn_key or unit.jira_key or "")
    return index


def _unique_allowed(keys: set[str], allowed: set[str]) -> str | None:
    hits = [key for key in keys if key in allowed]
    if len(hits) == 1:
        return hits[0]
    return None


def _resolve_issue_ref(
    raw: str | None,
    allowed_keys: set[str],
    summaries: dict[str, set[str]],
) -> tuple[str | None, str]:
    text = (raw or "").strip()
    if not text:
        return None, "empty"
    upper = text.upper()
    if _ISSUE_KEY_ONLY.match(upper):
        if upper in allowed_keys:
            return upper, "key"
        return None, "unknown-key"
    embedded = [token for token in _ISSUE_KEY.findall(upper) if token in allowed_keys]
    unique_embedded = list(dict.fromkeys(embedded))
    if len(unique_embedded) == 1:
        return unique_embedded[0], "embedded-key"
    if len(unique_embedded) > 1:
        return None, "ambiguous-key"
    label = _label_key(text)
    exact = _unique_allowed(summaries.get(label) or set(), allowed_keys)
    if exact:
        return exact, "summary"
    if len(label) < 24:
        return None, "unresolved"
    contains: list[str] = []
    for summary, keys in summaries.items():
        if label in summary or summary in label:
            contains.extend(key for key in keys if key in allowed_keys)
    unique = list(dict.fromkeys(contains))
    if len(unique) == 1:
        return unique[0], "summary-contains"
    if len(unique) > 1:
        return None, "ambiguous-summary"
    return None, "unresolved"


def _infer_keys_from_covers(
    covers: list[str],
    inventory: list[CoverageUnit],
) -> tuple[str | None, str | None]:
    by_id = {unit.coverage_id: unit for unit in inventory}
    rn_keys: list[str] = []
    jira_keys: list[str] = []
    for cid in covers:
        unit = by_id.get(cid)
        if unit is None:
            continue
        if unit.rn_key:
            rn_keys.append(unit.rn_key.strip().upper())
        if unit.jira_key:
            jira_keys.append(unit.jira_key.strip().upper())
    rn = list(dict.fromkeys(rn_keys))
    jira = list(dict.fromkeys(jira_keys))
    return (rn[0] if len(rn) == 1 else None, jira[0] if len(jira) == 1 else None)


def _keep_llm_functionality_candidates(
    candidates: list[GeneratedCaseCandidate],
    allowed_keys: set[str],
    allowed_covers: set[str],
    inventory: list[CoverageUnit] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    tickets: dict[str, list[tuple[str, str]]] | None = None,
) -> list[GeneratedCaseCandidate]:
    inventory = inventory or []
    artifacts = artifacts or []
    tickets = tickets or {}
    rn_keys = rn_keys_from_tickets(tickets) or [
        key for key in allowed_keys if story_to_rn_map(artifacts, list(allowed_keys)).get(key) in {None, key}
    ]
    story_map = story_to_rn_map(artifacts, rn_keys)
    jira_keys = set(allowed_keys) | _llm_jira_trace_keys(tickets, inventory, artifacts)
    func_keys = set(rn_keys) or {key for key in allowed_keys if story_map.get(key, key) == key}
    summaries = _summary_index(tickets, artifacts, inventory)
    kept: list[GeneratedCaseCandidate] = []
    received = len(candidates)
    rejected = 0
    for candidate in candidates:
        original_func = candidate.related_functionality
        original_jira = candidate.related_jira
        valid_covers = [cid for cid in (candidate.covers or []) if cid in allowed_covers]
        unknown_covers = [cid for cid in (candidate.covers or []) if cid not in allowed_covers]
        if not valid_covers:
            rejected += 1
            logger.info(
                "LLM candidate rejected: name=%s reason=%s covers=%s",
                candidate.name[:120],
                "missing-or-unknown-coverage-id" if unknown_covers or not candidate.covers else "no-coverage-id",
                candidate.covers,
            )
            continue
        func_key, func_how = _resolve_issue_ref(original_func, func_keys | set(story_map), summaries)
        if func_key and func_key in story_map:
            func_key = story_map[func_key]
            func_how = "story-remapped-to-rn"
        jira_key, jira_how = _resolve_issue_ref(original_jira, jira_keys, summaries)
        inferred_rn, inferred_jira = _infer_keys_from_covers(valid_covers, inventory)
        if inferred_rn is None and inferred_jira and inferred_jira in story_map:
            inferred_rn = story_map[inferred_jira]
        if original_func and func_how == "unknown-key":
            rejected += 1
            logger.info(
                "LLM candidate rejected: name=%s reason=unknown-functionality-key value=%s",
                candidate.name[:120],
                original_func[:80],
            )
            continue
        if original_jira and jira_how == "unknown-key" and inferred_jira is None and inferred_rn is None:
            rejected += 1
            logger.info(
                "LLM candidate rejected: name=%s reason=unknown-jira-key value=%s",
                candidate.name[:120],
                original_jira[:80],
            )
            continue
        if original_func and func_key is None and inferred_rn is None:
            rejected += 1
            logger.info(
                "LLM candidate rejected: name=%s reason=unresolved-functionality value=%s",
                candidate.name[:120],
                (original_func or "")[:80],
            )
            continue
        if original_jira and jira_key is None and inferred_jira is None and inferred_rn is None:
            rejected += 1
            logger.info(
                "LLM candidate rejected: name=%s reason=unresolved-jira value=%s",
                candidate.name[:120],
                (original_jira or "")[:80],
            )
            continue
        resolved_func = func_key if func_key in func_keys else inferred_rn
        if resolved_func and resolved_func in story_map:
            resolved_func = story_map[resolved_func]
        if resolved_func and resolved_func not in func_keys:
            resolved_func = inferred_rn if inferred_rn in func_keys else None
        resolved_jira = jira_key or inferred_jira
        if resolved_func is None and resolved_jira is None:
            rejected += 1
            logger.info("LLM candidate rejected: name=%s reason=no-traceable-key", candidate.name[:120])
            continue
        if resolved_func and resolved_func not in func_keys:
            rejected += 1
            logger.info(
                "LLM candidate rejected: name=%s reason=functionality-not-in-release key=%s",
                candidate.name[:120],
                resolved_func,
            )
            continue
        if resolved_jira and resolved_jira not in jira_keys:
            rejected += 1
            logger.info(
                "LLM candidate rejected: name=%s reason=jira-not-in-release key=%s",
                candidate.name[:120],
                resolved_jira,
            )
            continue
        notes: list[str] = []
        if original_func and func_key and original_func.strip().upper() != func_key:
            notes.append(f"LLM related_functionality original: {original_func}")
        if original_jira and jira_key and original_jira.strip().upper() != jira_key:
            notes.append(f"LLM related_jira original: {original_jira}")
        candidate.covers = valid_covers
        candidate.covered_unit_ids = valid_covers
        candidate.related_functionality = resolved_func or candidate.related_functionality
        candidate.related_jira = resolved_jira or candidate.related_jira
        candidate.generation_origin = candidate.generation_origin or "llm"
        if notes:
            extra = " | ".join(notes)
            candidate.evidence = f"{candidate.evidence}\n{extra}".strip() if candidate.evidence else extra
            candidate.applied_rules = list(dict.fromkeys([*(candidate.applied_rules or []), "llm-ref-resolved"]))
        logger.info(
            "LLM candidate accepted: name=%s covers=%s functionality=%s jira=%s func_how=%s jira_how=%s",
            candidate.name[:120],
            candidate.covers,
            candidate.related_functionality,
            candidate.related_jira,
            func_how,
            jira_how,
        )
        kept.append(candidate)
    logger.info(
        "LLM keep: received=%s accepted=%s rejected=%s covers=%s",
        received,
        len(kept),
        rejected,
        sorted(_covered_ids(kept)),
    )
    return kept


MAX_LLM_PAYLOAD_CHARS = 50000


@dataclass
class LlmBatch:
    batch_id: str
    epc: str
    story: str
    units: list[CoverageUnit]
    tickets: dict[str, list[tuple[str, str]]]
    artifacts: list[dict[str, Any]]
    pass_name: str = "first"
    stats: dict[str, Any] = field(default_factory=dict)


def _unit_epc_story(unit: CoverageUnit) -> tuple[str, str]:
    epc = (unit.rn_key or unit.artifact_key or "").strip().upper() or "UNKNOWN"
    story = (unit.story_key or unit.jira_key or epc).strip().upper() or epc
    return epc, story


def _tickets_for_epc(
    tickets: dict[str, list[tuple[str, str]]],
    epc: str,
) -> dict[str, list[tuple[str, str]]]:
    wanted = epc.strip().upper()
    return {
        "functionality": [
            (tid, text)
            for tid, text in tickets.get("functionality", [])
            if (tid or "").strip().upper() == wanted
        ]
    }


def _artifacts_for_story(
    artifacts: list[dict[str, Any]],
    epc: str,
    story: str,
) -> list[dict[str, Any]]:
    epc_u = epc.strip().upper()
    story_u = story.strip().upper()
    scoped: list[dict[str, Any]] = []
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        key = str(art.get("key") or "").strip().upper()
        if key != epc_u and key != story_u:
            children_hit = [
                child
                for child in (art.get("children") or [])
                if isinstance(child, dict)
                and str(child.get("key") or "").strip().upper() in {story_u, epc_u}
            ]
            if not children_hit:
                continue
            copy = dict(art)
            copy["children"] = children_hit
            scoped.append(copy)
            continue
        copy = dict(art)
        if key == epc_u:
            children = [
                child
                for child in (art.get("children") or [])
                if isinstance(child, dict)
                and str(child.get("key") or "").strip().upper() == story_u
            ]
            copy["children"] = children
        scoped.append(copy)
    return scoped


def _llm_chat_body(
    context: dict[str, Any],
    existing: list[dict[str, str]],
    tickets: dict[str, list[tuple[str, str]]],
    jira_artifacts: list[dict[str, Any]],
    inventory: list[CoverageUnit],
) -> dict[str, Any]:
    """Chat/completions body. Prompt contract lives in _ENGINE_RULES + _JSON_INSTRUCTIONS."""
    user_payload = {
        "release": context,
        "existing_cases_reference": existing,
        "tickets_from_rn": {
            "functionality": _functionality_tickets_for_llm(tickets),
        },
        "coverage_inventory": [unit.for_llm() for unit in inventory],
        "proposed_flows": proposed_flows_for_llm(inventory),
        "functionality_jira_artifacts": _jira_artifacts_for_llm(jira_artifacts),
        "jira_dual_source_note": (
            "Jira crudo es contexto de Funcionalidad. La fuente de cobertura es coverage_inventory."
        ),
        "product_brief_field_note": "customfield_19094 es resumen; no es fuente única de casos.",
        "instruction": (
            "Redacta casos como flujos ejecutables a partir de coverage_inventory y "
            "proposed_flows. Composición: unidades consecutivas del mismo flujo son "
            "pasos de un caso, aunque cambie la acción. Equivalencia: solo si el "
            "esperado normalizado es idéntico. Pasos en infinitivo. Textos de UI "
            "entre comillas se copian literales. Cada paso declara covered_unit_ids. "
            "Nunca 'El usuario ingresa al flujo correspondiente.' "
            "No mezcles historias ni EPCs. related_functionality es la Epic; "
            "related_jira es la Story. Ignora NCO, TRI, QA Bugs y QC Bugs."
        ),
    }
    return {
        "model": settings.openai_model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _ENGINE_RULES + "\n" + _JSON_INSTRUCTIONS},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }


def llm_payload_chars(
    context: dict[str, Any],
    existing: list[dict[str, str]],
    tickets: dict[str, list[tuple[str, str]]],
    jira_artifacts: list[dict[str, Any]],
    inventory: list[CoverageUnit],
) -> int:
    body = _llm_chat_body(context, existing, tickets, jira_artifacts, inventory)
    return len(json.dumps(body, ensure_ascii=False))


def _chunk_story_units(
    units: list[CoverageUnit],
    *,
    epc: str,
    story: str,
    tickets: dict[str, list[tuple[str, str]]],
    artifacts: list[dict[str, Any]],
    context: dict[str, Any],
    existing: list[dict[str, str]],
    limit: int,
) -> list[list[CoverageUnit]]:
    ordered = sorted(units, key=lambda unit: unit.coverage_id)
    if not ordered:
        return []
    size = llm_payload_chars(context, existing, tickets, artifacts, ordered)
    if size <= limit or len(ordered) == 1:
        return [ordered]
    mid = max(1, len(ordered) // 2)
    return _chunk_story_units(
        ordered[:mid],
        epc=epc,
        story=story,
        tickets=tickets,
        artifacts=artifacts,
        context=context,
        existing=existing,
        limit=limit,
    ) + _chunk_story_units(
        ordered[mid:],
        epc=epc,
        story=story,
        tickets=tickets,
        artifacts=artifacts,
        context=context,
        existing=existing,
        limit=limit,
    )


def partition_coverage_for_llm(
    inventory: list[CoverageUnit],
    *,
    tickets: dict[str, list[tuple[str, str]]],
    artifacts: list[dict[str, Any]],
    context: dict[str, Any],
    existing: list[dict[str, str]],
    limit: int | None = None,
    pass_name: str = "first",
) -> list[LlmBatch]:
    """Deterministic EPC+Story batches. Chunk a Story only when payload exceeds limit."""
    cap = MAX_LLM_PAYLOAD_CHARS if limit is None else limit
    grouped: dict[tuple[str, str], list[CoverageUnit]] = {}
    order: list[tuple[str, str]] = []
    for unit in inventory:
        key = _unit_epc_story(unit)
        if key not in grouped:
            order.append(key)
            grouped[key] = []
        grouped[key].append(unit)
    batches: list[LlmBatch] = []
    seq = 0
    for epc, story in order:
        story_units = grouped[(epc, story)]
        scoped_tickets = _tickets_for_epc(tickets, epc)
        scoped_arts = _artifacts_for_story(artifacts, epc, story)
        chunks = _chunk_story_units(
            story_units,
            epc=epc,
            story=story,
            tickets=scoped_tickets,
            artifacts=scoped_arts,
            context=context,
            existing=existing,
            limit=cap,
        )
        for chunk in chunks:
            seq += 1
            batch_id = f"B-{seq:03d}"
            stamped = [
                unit.model_copy(update={"batch_id": batch_id})
                for unit in chunk
            ]
            batches.append(
                LlmBatch(
                    batch_id=batch_id,
                    epc=epc,
                    story=story,
                    units=stamped,
                    tickets=scoped_tickets,
                    artifacts=scoped_arts,
                    pass_name=pass_name,
                )
            )
    return batches


def reconcile_llm_coverage(
    inventory: list[CoverageUnit],
    candidates: list[GeneratedCaseCandidate],
    failed_ids: set[str],
) -> dict[str, str]:
    covered: dict[str, list[str]] = {}
    for candidate in candidates:
        if (candidate.generation_origin or "llm") != "llm":
            continue
        for cid in candidate.covers or []:
            covered.setdefault(cid, []).append(candidate.name)
    status: dict[str, str] = {}
    for unit in inventory:
        cid = unit.coverage_id
        if cid in failed_ids:
            status[cid] = "llm_failed"
        elif cid not in covered:
            status[cid] = "llm_uncovered"
        elif any(
            len(cand.covers or []) > 1
            for cand in candidates
            if cid in (cand.covers or []) and (cand.generation_origin or "llm") == "llm"
        ):
            status[cid] = "llm_merged"
        else:
            status[cid] = "llm_covered"
    return status


def _run_llm_batch(
    batch: LlmBatch,
    context: dict[str, Any],
    existing: list[dict[str, str]],
) -> tuple[list[GeneratedCaseCandidate], dict[str, Any]]:
    payload = llm_payload_chars(
        context, existing, batch.tickets, batch.artifacts, batch.units
    )
    row: dict[str, Any] = {
        "batch_id": batch.batch_id,
        "epc": batch.epc,
        "story": batch.story,
        "pass": batch.pass_name,
        "number_of_units": len(batch.units),
        "unit_ids": [unit.coverage_id for unit in batch.units],
        "payload_chars": payload,
        "model": settings.openai_model,
        "candidates": 0,
        "accepted": 0,
        "rejected": 0,
        "uncovered": [unit.coverage_id for unit in batch.units],
        "openai_status": None,
        "duration_ms": None,
        "error": None,
    }
    started = time.perf_counter()
    try:
        accepted = _from_llm(
            context,
            existing,
            batch.tickets,
            batch.artifacts,
            batch.units,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        for candidate in accepted:
            candidate.generation_origin = candidate.generation_origin or "llm"
            candidate.batch_id = batch.batch_id
        covered = _covered_ids(accepted)
        row.update(
            {
                "openai_status": 200,
                "duration_ms": duration_ms,
                "candidates": _last_llm_meta.get("received", len(accepted)),
                "accepted": _last_llm_meta.get("accepted", len(accepted)),
                "rejected": _last_llm_meta.get("rejected", 0),
                "uncovered": [
                    unit.coverage_id
                    for unit in batch.units
                    if unit.coverage_id not in covered
                ],
            }
        )
        return accepted, row
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        status = getattr(exc, "status_code", None) or getattr(
            getattr(exc, "response", None), "status_code", None
        )
        row.update(
            {
                "openai_status": status,
                "duration_ms": duration_ms,
                "error": _llm_safe_text(exc),
                "uncovered": [unit.coverage_id for unit in batch.units],
            }
        )
        logger.error(
            "LLM call failed: type=%s status=%s message=%s",
            type(exc).__name__,
            status,
            _llm_safe_text(exc),
        )
        logger.error(
            "LLM batch failed: batch_id=%s epc=%s story=%s units=%s payload=%s error=%s",
            batch.batch_id,
            batch.epc,
            batch.story,
            [unit.coverage_id for unit in batch.units],
            payload,
            _llm_safe_text(exc),
        )
        return [], row


def _from_llm(
    context: dict[str, Any],
    existing: list[dict[str, str]],
    tickets: dict[str, list[tuple[str, str]]],
    jira_artifacts: list[dict[str, Any]],
    inventory: list[CoverageUnit],
) -> list[GeneratedCaseCandidate]:
    logger.info("LLM attempt: using model %s", settings.openai_model)
    allowed_ids = {unit.coverage_id for unit in inventory}
    allowed_keys = _llm_functionality_keys(tickets, inventory, jira_artifacts)
    body = _llm_chat_body(context, existing, tickets, jira_artifacts, inventory)
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    with httpx.Client(timeout=90.0) as client:
        response = client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
    if response.status_code != 200:
        logger.warning(
            "LLM HTTP error: type=RuntimeError status=%s message=%s",
            response.status_code,
            _llm_safe_text(response.text),
        )
        raise RuntimeError(f"LLM HTTP {response.status_code}: {response.text[:400]}")
    content = response.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    parsed_candidates = _parse_llm_candidates(parsed, existing)
    candidates = _keep_llm_functionality_candidates(
        parsed_candidates,
        allowed_keys,
        allowed_ids,
        inventory=inventory,
        artifacts=jira_artifacts,
        tickets=tickets,
    )
    before_fidelity = len(candidates)
    candidates = enforce_llm_unit_fidelity(candidates, inventory)
    candidates = validate_composed_candidates(
        candidates,
        inventory,
        fill_missing=lambda missing: compose_inventory(missing, existing, _duplicate_of),
    )
    for row in candidates:
        row.generation_origin = row.generation_origin or "llm"
    _last_llm_meta.clear()
    _last_llm_meta.update(
        {
            "received": len(parsed_candidates),
            "accepted": len(candidates),
            "rejected": len(parsed_candidates) - len(candidates),
            "fidelity_dropped": before_fidelity - len(candidates),
        }
    )
    logger.info(
        "LLM responded correctly: received=%s accepted=%s rejected=%s model=%s covers=%s",
        len(parsed_candidates),
        len(candidates),
        len(parsed_candidates) - len(candidates),
        settings.openai_model,
        sorted(_covered_ids(candidates)),
    )
    return candidates


def _covered_rn_keys(
    already: list[GeneratedCaseCandidate],
    inventory: list[CoverageUnit] | None = None,
) -> set[str]:
    covered: set[str] = set()
    for unit in inventory or []:
        if unit.rn_key:
            covered.add(unit.rn_key.strip().upper())
    for candidate in already:
        for part in (candidate.related_functionality or "").split("|"):
            key = part.strip().upper()
            if key:
                covered.add(key)
    return covered


def _merge_last_resort(
    pdf_bytes: bytes | None,
    rn_filename: str,
    existing: list[dict[str, str]],
    already: list[GeneratedCaseCandidate],
    inventory: list[CoverageUnit] | None = None,
    tickets: dict[str, list[tuple[str, str]]] | None = None,
) -> list[GeneratedCaseCandidate]:
    covered = _covered_rn_keys(already, inventory)
    if tickets is not None:
        extras: list[GeneratedCaseCandidate] = []
        for ticket_id, cell_text in tickets.get("functionality", []):
            if ticket_id.strip().upper() in covered:
                continue
            if not last_resort_applies(cell_text, ticket_id):
                continue
            candidate = _candidate_from_functionality_ticket(
                ticket_id, cell_text, rn_filename, existing
            )
            if candidate is not None:
                extras.append(candidate)
        extras = apply_qc_rules(extras)
        return already + extras
    extras = _from_evidence(pdf_bytes, rn_filename, existing)
    return already + [
        row for row in extras if (row.related_jira or "").upper() not in covered
    ]


def _keep_scoped_candidates(
    candidates: list[GeneratedCaseCandidate],
    allowed_keys: set[str] | None,
) -> list[GeneratedCaseCandidate]:
    if not allowed_keys:
        return candidates
    kept: list[GeneratedCaseCandidate] = []
    for candidate in candidates:
        keys = {
            (candidate.related_functionality or "").strip().upper(),
            (candidate.related_jira or "").strip().upper(),
        }
        if keys & allowed_keys:
            kept.append(candidate)
    return kept


def _covered_ids(candidates: list[GeneratedCaseCandidate]) -> set[str]:
    covered: set[str] = set()
    for candidate in candidates:
        covered.update(candidate.covers or [])
    return covered


def _dedupe_candidates(candidates: list[GeneratedCaseCandidate]) -> list[GeneratedCaseCandidate]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    out: list[GeneratedCaseCandidate] = []
    for candidate in candidates:
        key = (_normalize(candidate.name), tuple(sorted(candidate.covers or [])))
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def generate_release_app_candidates(
    *,
    release_id: int,
    release_name: str,
    validation_type: str | None,
    analysis_present: bool,
    rn_filename: str | None,
    pdf_bytes: bytes | None,
    release_context: dict[str, Any],
    existing_cases: list[dict[str, str]],
    tickets: dict[str, list[tuple[str, str]]] | None = None,
    restrict_to_functionality_keys: set[str] | None = None,
) -> GenerateCasesResponse:
    parsed_tickets = (
        tickets
        if tickets is not None
        else (_tickets_by_section(pdf_bytes, rn_filename or "") if pdf_bytes else {})
    )
    allowed = {key.upper() for key in (restrict_to_functionality_keys or set()) if key}
    if allowed:
        parsed_tickets = {
            **parsed_tickets,
            "functionality": [
                (tid, text)
                for tid, text in parsed_tickets.get("functionality", [])
                if tid.upper() in allowed
            ],
        }
    functionality_keys = rn_keys_from_tickets(parsed_tickets)
    stats = GenerationStats()
    if functionality_keys:
        kept, dropped_nco = keep_technical_epic_keys(
            functionality_keys,
            fetch_issuetypes_for_keys(functionality_keys),
        )
        functionality_keys = kept
        for key in dropped_nco:
            stats.inventory_exclusions.append(
                f"{key}: no es Technical Epic; no genera casos de funcionalidad"
            )
        if dropped_nco:
            parsed_tickets = {
                **parsed_tickets,
                "functionality": [
                    (tid, text)
                    for tid, text in parsed_tickets.get("functionality", [])
                    if tid.upper() not in {item.upper() for item in dropped_nco}
                ],
            }
    jira_artifacts = fetch_artifacts_for_keys(functionality_keys) if functionality_keys else []
    inventory = build_coverage_inventory(jira_artifacts, rn_filename or "", stats=stats)
    if allowed:
        inventory = [
            unit
            for unit in inventory
            if (unit.rn_key or "").upper() in allowed or (unit.jira_key or "").upper() in allowed
        ]
    jira_candidates = attach_artifact_literals(
        compose_inventory(inventory, existing_cases, _duplicate_of),
        jira_artifacts,
    )

    engine = "evidence"
    candidates: list[GeneratedCaseCandidate] = []
    analysis_details: list[str] = []
    if settings.openai_api_key and inventory:
        llm_tickets = {"functionality": list(parsed_tickets.get("functionality", []))}
        first_batches = partition_coverage_for_llm(
            inventory,
            tickets=llm_tickets,
            artifacts=jira_artifacts,
            context=release_context,
            existing=existing_cases,
            pass_name="first",
        )
        by_id = {unit.coverage_id: unit for unit in inventory}
        for batch in first_batches:
            for unit in batch.units:
                original = by_id.get(unit.coverage_id)
                if original is not None:
                    original.batch_id = batch.batch_id
        llm_candidates: list[GeneratedCaseCandidate] = []
        failed_ids: set[str] = set()
        batch_rows: list[dict[str, Any]] = []
        for batch in first_batches:
            accepted, row = _run_llm_batch(batch, release_context, existing_cases)
            batch_rows.append(row)
            if row.get("error"):
                failed_ids.update(unit.coverage_id for unit in batch.units)
                continue
            llm_candidates.extend(accepted)
        llm_covers = _covered_ids(llm_candidates)
        missing = [
            unit
            for unit in inventory
            if unit.coverage_id not in llm_covers and unit.coverage_id not in failed_ids
        ]
        if missing:
            logger.info(
                "LLM coverage check: missing=%s ids=%s",
                len(missing),
                [unit.coverage_id for unit in missing],
            )
            second_batches = partition_coverage_for_llm(
                missing,
                tickets=llm_tickets,
                artifacts=jira_artifacts,
                context=release_context,
                existing=existing_cases,
                pass_name="second",
            )
            for batch in second_batches:
                accepted, row = _run_llm_batch(batch, release_context, existing_cases)
                batch_rows.append(row)
                if row.get("error"):
                    failed_ids.update(unit.coverage_id for unit in batch.units)
                    continue
                llm_candidates.extend(accepted)
        llm_candidates = _dedupe_candidates(llm_candidates)
        llm_covers = _covered_ids(llm_candidates)
        stats.llm_batches = batch_rows
        stats.coverage_unit_status = reconcile_llm_coverage(
            inventory, llm_candidates, failed_ids
        )
        analysis_details.append(
            f"LLM batches={len(batch_rows)} aceptados={len(llm_candidates)} "
            f"CoverageUnits cubiertas={len(llm_covers)} "
            f"({', '.join(sorted(llm_covers)) or 'ninguna'})."
        )
        still_missing = [
            unit for unit in inventory if unit.coverage_id not in llm_covers
        ]
        candidates = list(llm_candidates)
        if still_missing:
            logger.info(
                "Coverage fill: missing=%s ids=%s",
                len(still_missing),
                [unit.coverage_id for unit in still_missing],
            )
            filled = compose_inventory(
                still_missing, existing_cases, _duplicate_of
            )
            for row in filled:
                row.review_required = True
                row.generation_origin = "coverage-fill"
                source = by_id.get((row.covers or [None])[0] or "")
                if source is not None:
                    row.batch_id = source.batch_id
            candidates = _dedupe_candidates(candidates + filled)
            if llm_candidates:
                engine = "llm+coverage-fill"
                analysis_details.append(
                    "Coverage Fill: "
                    f"{len(still_missing)} unidad(es) materializadas de forma determinista "
                    f"({', '.join(unit.coverage_id for unit in still_missing)})."
                )
            else:
                logger.warning("LLM fallback activated")
                candidates = jira_candidates or filled or []
                engine = "evidence-jira" if candidates else "evidence-fallback"
        elif llm_candidates:
            engine = "llm"
        else:
            candidates = jira_candidates or []
            engine = "evidence-jira" if jira_candidates else "evidence-fallback"
        if not candidates:
            candidates = jira_candidates or []
            engine = "evidence-jira" if jira_candidates else "evidence-fallback"
    elif jira_candidates:
        candidates = jira_candidates
        engine = "evidence-jira"
    else:
        candidates = []

    candidates = stamp_candidates(candidates, functionality_keys, jira_artifacts)
    candidates = _merge_last_resort(
        pdf_bytes,
        rn_filename or "",
        existing_cases,
        candidates,
        inventory=inventory,
        tickets=parsed_tickets,
    )
    if not candidates and pdf_bytes:
        candidates = _from_evidence(pdf_bytes, rn_filename or "", existing_cases)
        engine = "evidence"

    candidates = _keep_scoped_candidates(candidates, allowed or None)
    candidates = apply_qc_rules(candidates, release_context=release_context, stats=stats)
    candidates = apply_executability_gate(candidates, inventory)
    candidates = quality_gate(candidates)
    stamp_source_types(candidates)
    candidates = stamp_candidates(candidates, functionality_keys, jira_artifacts)
    covered = sorted(_covered_ids(candidates))
    coverage = build_rn_scope_coverage(
        rn_keys=functionality_keys,
        artifacts=jira_artifacts,
        inventory=inventory,
        covered_ids=covered,
        candidates=candidates,
    )
    required = [unit.coverage_id for unit in inventory]
    uncovered = [cid for cid in required if cid not in set(covered)]
    message = (
        f"Se propusieron {len(candidates)} caso(s) candidato(s). La IA propone; QC decide. "
        "No se crearon Test Cases en la base de datos."
    )
    if not analysis_present:
        message = "No hay análisis de RN asociado; no hay evidencia para proponer casos."
    elif not pdf_bytes and not candidates:
        message = (
            "El PDF del RN no está almacenado. Vuelve a analizar el RN al crear la Release "
            "para poder generar candidatos."
        )
    return GenerateCasesResponse(
        status="PROPOSED" if candidates else "EMPTY",
        message=message,
        release_id=release_id,
        release_name=release_name,
        validation_type=validation_type,
        has_analysis=analysis_present,
        engine=engine,
        candidates=candidates,
        persisted=False,
        generation_stats=stats,
        analysis_details=analysis_details,
        coverage_unit_count=len(inventory),
        covered_coverage_ids=covered,
        uncovered_coverage_ids=uncovered,
        rn_scope_coverage=coverage,
    )
