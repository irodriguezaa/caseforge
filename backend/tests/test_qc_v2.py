"""QcPulse v2: recolección, etapas y mapeo, con Jira real como fixture y la IA simulada."""

from __future__ import annotations

import json

import pytest

from app.services.qc_v2 import collect, engine, stages
from app.services.qc_v2.collect import EpicBundle, Item, TechStory, UserStory
from app.services.qc_v2.context import device_context
from app.services.qc_v2.llm import LlmMeta, QuotaExhausted

# ------------------------------------------------------------------ fixtures (texto real de Jira)

BRFRE_3529_AC = """1. Cuando el usuario Externo se registra en Claro video e ingresa por primera vez a la home de inicio, cuente o no con alguna suscripción, el Centro de notificaciones debe visualizarse desplegado mostrando los siguientes elementos:

    1. Se debe mostrar la comunicación Descubre más planes
    2. Se debe mostrar el botón accionable que dirija al usuario al Selector de planes respetando el comportamiento actualmente implementado en producción

2. Cuando el usuario Externo inicia sesión en Claro video e ingresa a la home de inicio, cuente o no con alguna suscripción, el Centro de notificaciones debe visualizarse replegado.

    1. Al desplegarse, este debe mostrar los elementos mencionados en el CA 1

3. El Centro de notificaciones debe visualizarse replegado si:

    1. Si el usuario selecciona uno de los botones del Centro de Notificaciones, independientemente si termina o no las acciones que se detonan de los botones
    2. Si el usuario cierra el Centro de Notificaciones antes salir de la home de inicio y posteriormente regresa al mismo

4. Si el usuario no realizó alguna de las interacciones previamente definidas con el Centro de Notificaciones y sale y vuelve a ingresar a la home de inicio, este se debe visualizar desplegado.
5. El Centro de Notificaciones debe ocultarse completamente solo si el usuario ha adquirido todas las suscripciones disponibles en la operación.
6. Todos los textos deben de ser configurables por operación.
7. Todos los elementos deben cumplir con los textos, posición y elementos definidos en los insumos de diseño compartidos.
"""

WEBCL_2061 = """Feature: Ajuste de espaciado vertical en las páginas Home de la UI

  Background:
    Given que tengo acceso a los insumos de diseño aprobados
    And me encuentro en una de las páginas Home definidas para el ajuste

  Scenario: Ajustar distancia entre el menú de navegación principal y los elementos de UI
    When identifico el menú de navegación principal
    Then la distancia vertical debe ser igual al valor definido en Figma

  Scenario: Ajustar espaciado entre elementos intermedios dentro de la Home
    Given que existen elementos intermedios como Brand Header
    Then cada distancia debe respetar los valores establecidos

  Scenario: Validación por resolución
  When se renderiza la Home en las resoluciones soportadas
  Then el espaciado debe mantenerse conforme al layout definido para cada breakpoint
```"""

WEBCL_1876 = """# Motivo: Actualizar el escenario "Identificar contenido bloqueado" al grabar o visualizar
Feature: Actualizar los assets de eventos bloqueados - WEB

    Background: El usuario ingresa a sección "Mis Contenidos"
        Given el usuario está autentificado en la plataforma
        Then se obtiene la lista de contenidos grabados, grabando y por grabar del usuario

    Scenario: Identificar contenido bloqueado
        Given se obtienen las listas de contenidos grabados
        When el "group id" del canal del evento se encuentra en la lista "data.pin_channel.info[]"
        Then la tarjeta del evento contiene el ícono de bloqueado y el overlay en el logo del canal
"""


# ------------------------------------------------------------------ collect


def test_split_criteria_keeps_subitems_inside_top_level():
    criteria = collect.split_criteria(BRFRE_3529_AC)
    assert len(criteria) == 7
    assert "Descubre más planes" in criteria[0]
    assert criteria[2].startswith("El Centro de notificaciones debe visualizarse replegado si")
    assert "cierra el Centro" in criteria[2]


def test_split_criteria_from_adf_ordered_list():
    adf = {
        "type": "doc",
        "content": [
            {"type": "orderedList", "content": [
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Primero"}]}]},
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Segundo"}]}]},
            ]}
        ],
    }
    assert collect.split_criteria(adf) == ["Primero", "Segundo"]


def test_split_criteria_without_numbers_is_one_criterion():
    assert collect.split_criteria("Texto libre sin numeración") == ["Texto libre sin numeración"]


def test_split_gherkin_background_is_context_not_scenario():
    context, blocks = collect.split_gherkin(WEBCL_2061)
    assert "Background" in context
    assert [title for title, _ in blocks] == [
        "Ajustar distancia entre el menú de navegación principal y los elementos de UI",
        "Ajustar espaciado entre elementos intermedios dentro de la Home",
        "Validación por resolución",
    ]
    assert "```" not in blocks[-1][1]


def test_split_gherkin_keeps_quotes_and_comments():
    context, blocks = collect.split_gherkin(WEBCL_1876)
    assert "al grabar o visualizar" in context
    assert len(blocks) == 1
    assert '"data.pin_channel.info[]"' in blocks[0][1]


def test_title_match_technical_brief_vs_product_epic():
    tb = "FE: Onboarding: Actualizar el comportamiento del Centro de Notificaciones de acuerdo al tipo de usuario (Pantallas medianas)"
    pe = "Actualizar el comportamiento del Centro de Notificaciones de acuerdo al tipo de usuario"
    spotlight = "Implementar estado Spotlight en el Centro de Notificaciones"
    assert collect.title_similarity(tb, pe) >= collect.TITLE_MATCH_THRESHOLD
    assert collect.title_similarity(tb, spotlight) < collect.TITLE_MATCH_THRESHOLD


class _Resp:
    def __init__(self, status: int, payload: dict | None = None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


def _issue(key, issuetype, summary="", parent=None, **fields):
    data = {"summary": summary, "issuetype": {"name": issuetype}, **fields}
    if parent:
        data["parent"] = {"key": parent}
    return {"key": key, "fields": data}


class _FakeJira:
    def __init__(self):
        self.issues = {
            "WEBCL-1586": _issue("WEBCL-1586", "Technical Epic", "Onboarding CN", parent="TBRFRE-895"),
            "TBRFRE-895": _issue(
                "TBRFRE-895", "Technical Brief",
                "FE: Onboarding: Actualizar el comportamiento del Centro de Notificaciones de acuerdo al tipo de usuario (Pantallas medianas)",
                parent="BRFRE-3492",
            ),
            "BRFRE-3492": _issue("BRFRE-3492", "Product Brief", "MX | Onboarding"),
        }
        self.children_map = {
            "WEBCL-1586": [_issue("WEBCL-1587", "Technical Story", "TS externo", description=WEBCL_2061)],
            "BRFRE-3492": [
                _issue("BRFRE-3510", "Product Epic", "Actualizar el comportamiento del Centro de Notificaciones de acuerdo al tipo de usuario"),
                _issue("BRFRE-3382", "Product Epic", "Implementar estado Spotlight en el Centro de Notificaciones"),
                _issue("TBRFRE-895", "Technical Brief", "FE: ..."),
            ],
            "BRFRE-3510": [
                _issue("BRFRE-3529", "User Story", "CN usuarios Externos", **{
                    collect.F_AC: BRFRE_3529_AC,
                    collect.F_YO_COMO: "negocio de Claro video",
                    collect.F_TIPO_USUARIO: [{"value": "Registrado"}, {"value": "Suscripto"}],
                }),
            ],
            "BRFRE-3382": [_issue("BRFRE-3502", "User Story", "Spotlight", **{collect.F_AC: "1. Spotlight"})],
        }

    def get(self, url, params=None):
        key = url.rsplit("/", 1)[-1]
        issue = self.issues.get(key)
        return _Resp(200, issue) if issue else _Resp(404)

    def post(self, url, json=None):
        key = json["jql"].split('"')[1]
        return _Resp(200, {"issues": self.children_map.get(key, [])})


def test_collect_epic_follows_business_branch_and_filters_by_title():
    bundle = collect.collect_epic(collect.JiraReader(_FakeJira()), "WEBCL-1586")
    assert [s.key for s in bundle.user_stories] == ["BRFRE-3529"]  # Spotlight fuera
    assert len(bundle.crns) == 7
    assert [c.id for c in bundle.covs] == ["COV-001", "COV-002", "COV-003"]
    assert bundle.user_stories[0].tipo_usuario == "Registrado, Suscripto"
    assert bundle.product_brief_key == "BRFRE-3492"
    assert not [w for w in bundle.warnings if "Sin User Story" in w]


# ------------------------------------------------------------------ stages + engine


def _bundle() -> EpicBundle:
    return EpicBundle(
        key="WEBCL-2060",
        summary="Espaciado vertical",
        technical_stories=[
            TechStory("WEBCL-2061", "Ajuste", "Background ...", [
                Item("COV-001", "Distancia menú", "Scenario: Distancia menú ...", "WEBCL-2061"),
                Item("COV-002", "Por resolución", "Scenario: Por resolución ...", "WEBCL-2061"),
                Item("COV-003", "Telemetría", "Scenario: se envía evento", "WEBCL-2061"),
            ])
        ],
        user_stories=[UserStory("BRFRE-1", "Espaciado", criteria=[Item("CRN-001", "Espaciado", "1. Espaciado", "BRFRE-1")])],
    )


_STAGE_A = {
    "resumen_funcionalidad": "El espaciado entre menú y contenido cambia",
    "escenarios": [
        {"id": "ESC-01", "titulo": "Espaciado entre menú y primer componente", "descripcion": "d",
         "condiciones": [], "cubre_negocio": ["CRN-001"], "cubre_tecnico": ["COV-001", "COV-002"],
         "brecha": "ninguna", "es_no_afectacion": False},
        {"id": "ESC-02", "titulo": "No afectación del menú", "descripcion": "d", "condiciones": [],
         "cubre_negocio": [], "cubre_tecnico": [], "brecha": "implicito", "es_no_afectacion": True},
    ],
    "excluidos": [{"id": "COV-003", "motivo": "telemetria", "explicacion": "solo evento"}],
}

_CASE = {
    "titulo": "Visualización del espaciado entre menú y primer componente",
    "tipo": "ERG",
    "prioridad": "Critical",
    "precondiciones": ["Pantalla mediana", "Diseño aprobado"],
    "pasos": [
        {"accion": "Seleccionar la Home", "resultado_esperado": "Se muestra la Home"},
        {"accion": "Observar la separación", "resultado_esperado": "Igual al diseño"},
        {"accion": "Recorrer las demás Homes", "resultado_esperado": "Igual al diseño en todas"},
    ],
    "variantes": [],
    "referencia_tecnica": "Figma",
    "riesgo": "espaciado incorrecto",
    "confianza": "alta",
}


def _fake_chat(responses):
    calls = []

    def chat(messages, *, model, temperature=None):
        calls.append(messages)
        system = messages[0]["content"]
        payload = responses["a"] if "ESCENARIOS DE PRUEBA" in system else responses["b"]
        if callable(payload):
            payload = payload(messages)
        return payload, LlmMeta(model=model, prompt_tokens=10, completion_tokens=5)

    chat.calls = calls
    return chat


def test_stage_a_parses_and_detects_missing():
    result = stages.parse_stage_a({**_STAGE_A, "excluidos": []}, _bundle())
    assert result.missing == ["COV-003"]
    assert result.scenarios[0].cubre_tecnico == ["COV-001", "COV-002"]


def test_stage_a_retries_once_when_missing():
    first = {**_STAGE_A, "excluidos": []}
    answers = iter([first, _STAGE_A])
    chat = _fake_chat({"a": lambda m: next(answers), "b": {"casos": [_CASE]}})
    result = stages.run_stage_a(_bundle(), device_context("WEB"), chat=chat)
    assert result.missing == []
    assert len(chat.calls) == 2


def test_engine_end_to_end_with_fake_llm():
    chat = _fake_chat({"a": _STAGE_A, "b": {"casos": [_CASE]}})
    run = engine.run_epic(_bundle(), device_context("WEB"), chat=chat)
    assert run.error is None
    assert len(run.candidates) == 2  # un caso por escenario en este fake
    first = run.candidates[0]
    assert first.generation_origin == "qc-v2"
    assert first.covers == ["CRN-001", "COV-001", "COV-002"]
    assert "qc-v2:tipo=ERG" in first.applied_rules
    assert "qc-v2:complejidad=BAJA" in first.applied_rules
    assert first.review_required is False
    estados = {row["scenario"].split()[0]: row["estado"] for row in run.ledger}
    assert estados["CRN-001"] == "cruce"
    assert estados["COV-003"] == "excluido: telemetria"
    assert any(row["estado"] == "no afectación" for row in run.ledger)
    assert run.llm_calls == 3


def test_case_with_two_steps_is_kept_and_flagged():
    short = {**_CASE, "pasos": _CASE["pasos"][:2]}
    chat = _fake_chat({"a": _STAGE_A, "b": {"casos": [short]}})
    run = engine.run_epic(_bundle(), device_context("WEB"), chat=chat)
    assert run.candidates, "nunca se descarta un caso"
    assert run.candidates[0].review_required is True
    assert "2 pasos" in (run.candidates[0].applicability_reason or "")


def test_empty_quotes_flagged():
    bad = {**_CASE, "pasos": [{"accion": 'Seleccionar "< >"', "resultado_esperado": "x"}] + _CASE["pasos"][1:]}
    case = stages.parse_stage_b({"casos": [bad]}, "ESC-01")[0]
    assert "texto entre comillas vacío" in stages.validate_case(case)


def test_complexity_rules():
    case = stages.parse_stage_b({"casos": [_CASE]}, "ESC-01")[0]
    assert stages.complexity(case) == "BAJA"
    case.tipo = "E2E"
    assert stages.complexity(case) == "ALTA"
    case.tipo = "HPA"
    case.variantes = [{"condicion": "a", "resultado_esperado": "b"}]
    assert stages.complexity(case) == "MEDIA"


def test_quota_stops_the_run():
    def chat(messages, *, model, temperature=None):
        raise QuotaExhausted("sin créditos")

    runs = engine.run_epics(["WEBCL-1586"], "WEB", reader=collect.JiraReader(_FakeJira()), chat=chat)
    assert runs[0].error and runs[0].error.startswith("corrida detenida")


def test_device_context_groups():
    assert device_context("ADT").modo_interaccion == "control remoto"
    assert device_context("WEB").grupo_pantalla == "Pantalla mediana"
    assert device_context("ADR").modo_interaccion == "táctil"
    assert device_context("WIN").metodos_pago == "No transacciona"


def test_prompts_exist_and_are_loaded():
    assert "ESCENARIOS DE PRUEBA" in stages.load_prompt("etapa_a.md")
    assert "REGLA DEL BUG" in stages.load_prompt("etapa_b.md")
