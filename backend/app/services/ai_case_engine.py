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
from app.services.gherkin_coverage import (
    build_coverage_inventory,
    extract_technical,
    materialize_coverage_units,
    sanitize_user_text,
)
from app.services.jira_generation import fetch_artifacts_for_keys
from app.services.qc_candidate_rules import apply_qc_rules
from app.services.release_note_analyzer import iter_rn_ticket_rows
from app.services.rn_source_type import stamp_source_types

ENGINE_VERSION = "ai-v4"
logger = logging.getLogger(__name__)


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
   HTTP 400/401/404/500/503, flags, acciones de cierre equivalentes, labels por operación).
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
    si dos candidatos validan el mismo comportamiento observable, CONSOLIDAR y conservar
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
NO inventes un número objetivo de casos. El número es consecuencia de las unidades.
Agrupa unidades solo si son el mismo comportamiento observable y la misma validación.
Separa unidades si cambia comportamiento, estado, error observable, persistencia,
condición de negocio, resultado esperado o escenario funcional independiente.
NO un caso por endpoint, HTTP status o Jira técnico.
Cada candidato DEBE listar covers con coverage_id de las unidades que cubre.
NO dejes unidades A/G sin covers.
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
  "steps":[{"step_number":int,"action":string,"expected_result":string,"test_data":string|null}],
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
  "covers": ["COV-001"]
}]}
Sin markdown, sin texto fuera del JSON.
No asignes test type Smoke/Regression. No inventes escenarios.
covers es obligatorio: ids de coverage_inventory cubiertos por ese caso.
Agrupa en covers solo unidades con el mismo comportamiento observable.
No colapses unidades independientes en un solo caso porque compartan Funcionalidad.
No inventes un resultado observable genérico.
"""

_METRICS_RE = re.compile(r"\bm[eé]tric|\banalytics\b|\bga4\b|\bfirebase\b|\bmdp\b", re.IGNORECASE)


def _tickets_by_section(pdf_bytes: bytes) -> dict[str, list[tuple[str, str]]]:
    """Section -> [(ticket_id, cell_text), ...] via the shared RN table walk."""
    buckets: dict[str, list[tuple[str, str]]] = {
        "functionality": [],
        "nco": [],
        "tri": [],
        "qa_qc": [],
    }
    seen: dict[str, set[str]] = {key: set() for key in buckets}
    for ticket_id, cell_text, bucket in iter_rn_ticket_rows(pdf_bytes):
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
            "Requiere la configuración/condición descrita en el RN; el caso es aplicable aunque no sea ejecutable aún."
            if needs_config
            else None
        ),
        requires_condition=needs_config,
        steps=[
            CandidateStep(
                step_number=1,
                action="El usuario recorre el flujo de la funcionalidad descrita en el RN.",
                expected_result="Se observa el comportamiento de usuario final declarado en el RN, sin condiciones no evidenciadas.",
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
    tickets = _tickets_by_section(pdf_bytes)
    candidates: list[GeneratedCaseCandidate] = []
    for ticket_id, cell_text in tickets.get("functionality", []):
        candidate = _candidate_from_functionality_ticket(ticket_id, cell_text, rn_filename, existing)
        if candidate is not None:
            candidates.append(candidate)
    return apply_qc_rules(candidates)


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
        for step in candidate.steps:
            original = f"{step.action} {step.expected_result}"
            tech = extract_technical(original)
            step.action = sanitize_user_text(step.action) or "El usuario completa el flujo funcional."
            step.expected_result = sanitize_user_text(step.expected_result) or "Se observa el comportamiento declarado."
            if tech and not step.test_data:
                step.test_data = tech
            if tech and not candidate.test_data:
                candidate.test_data = tech
        candidate.review_required = True
        raw_covers = item.get("covers") or []
        if isinstance(raw_covers, str):
            raw_covers = [raw_covers]
        candidate.covers = [
            str(cid).strip()
            for cid in raw_covers
            if str(cid).strip()
        ]
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
) -> set[str]:
    keys = {tid.strip().upper() for tid, _text in tickets.get("functionality", []) if tid}
    for unit in inventory:
        for raw in (unit.jira_key, unit.rn_key):
            if raw:
                keys.add(raw.strip().upper())
    return keys


def _keep_llm_functionality_candidates(
    candidates: list[GeneratedCaseCandidate],
    allowed_keys: set[str],
    allowed_covers: set[str],
) -> list[GeneratedCaseCandidate]:
    kept: list[GeneratedCaseCandidate] = []
    for candidate in candidates:
        jira = (candidate.related_jira or "").strip().upper()
        func = (candidate.related_functionality or "").strip().upper()
        if jira and jira not in allowed_keys:
            continue
        if func and func not in allowed_keys:
            continue
        candidate.covers = [cid for cid in candidate.covers if cid in allowed_covers]
        kept.append(candidate)
    return kept


def _from_llm(
    context: dict[str, Any],
    existing: list[dict[str, str]],
    tickets: dict[str, list[tuple[str, str]]],
    jira_artifacts: list[dict[str, Any]],
    inventory: list[CoverageUnit],
) -> list[GeneratedCaseCandidate]:
    logger.info("LLM attempt: using model %s", settings.openai_model)
    allowed_ids = {unit.coverage_id for unit in inventory}
    allowed_keys = _llm_functionality_keys(tickets, inventory)
    user_payload = {
        "release": context,
        "existing_cases_reference": existing,
        "tickets_from_rn": {
            "functionality": _functionality_tickets_for_llm(tickets),
        },
        "coverage_inventory": [unit.for_llm() for unit in inventory],
        "functionality_jira_artifacts": _jira_artifacts_for_llm(jira_artifacts),
        "jira_dual_source_note": (
            "Jira crudo es contexto de Funcionalidad. La fuente de cobertura es coverage_inventory."
        ),
        "product_brief_field_note": "customfield_19094 es resumen; no es fuente única de casos.",
        "instruction": (
            "Traduce coverage_inventory a casos ejecutables de usuario final. "
            "Cada candidato debe incluir covers con coverage_id. "
            "Agrupa unidades solo si el usuario observa el mismo resultado y la misma validación. "
            "No resumas una Funcionalidad en un solo caso si hay varias unidades independientes. "
            "Las únicas fuentes permitidas para generar casos mediante LLM son "
            "coverage_inventory y la evidencia/tickets de FUNCIONALIDAD. "
            "Ignora NCO, TRI, QA Bugs y QC Bugs. "
            "No inventes tickets ni combinaciones. No casos de métricas ni proceso QA."
        ),
    }
    body = {
        "model": settings.openai_model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _ENGINE_RULES + "\n" + _JSON_INSTRUCTIONS},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }
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
    candidates = _keep_llm_functionality_candidates(
        _parse_llm_candidates(parsed, existing),
        allowed_keys,
        allowed_ids,
    )
    logger.info(
        "LLM responded correctly: candidates=%s model=%s",
        len(candidates),
        settings.openai_model,
    )
    return candidates


def _merge_last_resort(
    pdf_bytes: bytes | None,
    rn_filename: str,
    existing: list[dict[str, str]],
    already: list[GeneratedCaseCandidate],
) -> list[GeneratedCaseCandidate]:
    covered: set[str] = set()
    for candidate in already:
        for key in (candidate.related_functionality, candidate.related_jira):
            if key:
                covered.add(key.strip().upper())
    extras = _from_evidence(pdf_bytes, rn_filename, existing)
    return already + [row for row in extras if (row.related_jira or "").upper() not in covered]


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
    parsed_tickets = tickets if tickets is not None else (_tickets_by_section(pdf_bytes) if pdf_bytes else {})
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
    functionality_keys = [tid for tid, _text in parsed_tickets.get("functionality", [])]
    jira_artifacts = fetch_artifacts_for_keys(functionality_keys) if functionality_keys else []
    stats = GenerationStats()
    inventory = build_coverage_inventory(jira_artifacts, rn_filename or "", stats=stats)
    if allowed:
        inventory = [
            unit
            for unit in inventory
            if (unit.rn_key or "").upper() in allowed or (unit.jira_key or "").upper() in allowed
        ]
    jira_candidates = materialize_coverage_units(
        inventory, existing_cases, _duplicate_of, stats=stats
    )

    engine = "evidence"
    candidates: list[GeneratedCaseCandidate] = []
    analysis_details: list[str] = []
    if settings.openai_api_key and pdf_bytes and inventory:
        try:
            llm_tickets = {"functionality": list(parsed_tickets.get("functionality", []))}
            candidates = _from_llm(
                release_context,
                existing_cases,
                llm_tickets,
                jira_artifacts,
                inventory,
            )
            engine = "llm"
            missing = [unit for unit in inventory if unit.coverage_id not in _covered_ids(candidates)]
            if missing:
                logger.info("LLM coverage check: missing=%s", len(missing))
                second = _from_llm(
                    release_context,
                    existing_cases,
                    llm_tickets,
                    jira_artifacts,
                    missing,
                )
                candidates = _dedupe_candidates(candidates + second)
            still_missing = [unit for unit in inventory if unit.coverage_id not in _covered_ids(candidates)]
            if still_missing:
                filled = materialize_coverage_units(
                    still_missing, existing_cases, _duplicate_of, stats=stats
                )
                for row in filled:
                    row.review_required = True
                    row.generation_origin = row.generation_origin or "coverage-fill"
                candidates = _dedupe_candidates(candidates + filled)
                engine = "llm+coverage-fill"
                analysis_details.append(
                    f"Coverage check: {len(still_missing)} unidad(es) materializadas de forma determinista."
                )
            if not candidates:
                candidates = jira_candidates or _from_evidence(
                    pdf_bytes, rn_filename or "", existing_cases
                )
                engine = "evidence-jira" if jira_candidates else "evidence-fallback"
        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(
                getattr(exc, "response", None), "status_code", None
            )
            logger.error(
                "LLM call failed: type=%s status=%s message=%s",
                type(exc).__name__,
                status,
                _llm_safe_text(exc),
            )
            logger.warning("LLM fallback activated")
            candidates = jira_candidates or _from_evidence(
                pdf_bytes, rn_filename or "", existing_cases
            )
            engine = "evidence-jira" if jira_candidates else "evidence-fallback"
    elif jira_candidates:
        candidates = _merge_last_resort(pdf_bytes, rn_filename or "", existing_cases, jira_candidates)
        engine = "evidence-jira"
    else:
        candidates = _from_evidence(pdf_bytes, rn_filename or "", existing_cases)

    candidates = _keep_scoped_candidates(candidates, allowed or None)
    candidates = apply_qc_rules(candidates, release_context=release_context, stats=stats)
    stamp_source_types(candidates)
    covered = sorted(_covered_ids(candidates))
    required = [unit.coverage_id for unit in inventory]
    uncovered = [cid for cid in required if cid not in set(covered)]
    message = (
        f"Se propusieron {len(candidates)} caso(s) candidato(s). La IA propone; QC decide. "
        "No se crearon Test Cases en la base de datos."
    )
    if not analysis_present:
        message = "No hay análisis de RN asociado; no hay evidencia para proponer casos."
    elif not pdf_bytes:
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
    )
