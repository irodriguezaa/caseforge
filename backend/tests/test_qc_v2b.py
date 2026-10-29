"""QcPulse v2-B: elegibilidad, consolidación y que v2 no cambia."""

from __future__ import annotations

from app.services.qc_v2.collect import EpicBundle, Item, TechStory, UserStory
from app.services.qc_v2.stages import DesignedCase, Scenario
from app.services.qc_v2b.eligibility import (
    ESTADO_HPA,
    ESTADO_QA,
    ESTADO_REGRESSION,
    ESTADO_TECH,
    classify_text,
    filter_bundle,
)
from app.services.qc_v2b.pack import consolidate, rewrite_title, user_label

from tests.test_qc_v2 import _CASE, _FakeJira, _fake_chat, collect, engine as v2_engine


def _case(**overrides) -> DesignedCase:
    base = dict(
        scenario_id="ESC-01",
        titulo="Visualización",
        tipo="HPP",
        prioridad="CRITICAL",
        precondiciones=["Usuario externo con cuenta real"],
        pasos=[
            {"accion": "Ingresar a la Home", "resultado_esperado": "Se muestra la Home"},
            {"accion": "Observar el Centro", "resultado_esperado": "Se muestra desplegado"},
            {"accion": "Seleccionar un botón", "resultado_esperado": "Abre el destino"},
        ],
        variantes=[],
        referencia_tecnica=None,
        riesgo="estado incorrecto",
        confianza="alta",
    )
    base.update(overrides)
    return DesignedCase(**base)


def _bundle() -> EpicBundle:
    return EpicBundle(
        key="WEBCL-1",
        summary="Centro de notificaciones",
        technical_stories=[
            TechStory(
                "WEBCL-2",
                "CN",
                "",
                [
                    Item("COV-001", "Desplegado al registrar", "Then se muestra desplegado", "WEBCL-2"),
                    Item("COV-002", "Replegado al iniciar sesión", "Then se muestra replegado", "WEBCL-2"),
                    Item("COV-003", "Oculto con todas las suscripciones", "Then no se muestra", "WEBCL-2"),
                    Item("COV-004", "Textos y diseño", "Then cumple insumos de diseño", "WEBCL-2"),
                ],
            )
        ],
        user_stories=[
            UserStory("US-1", "Externos", criteria=[Item("CRN-001", "Desplegado", "se muestra desplegado", "US-1")])
        ],
    )


def test_eligibility_keys_and_api_and_hpa():
    assert classify_text("No se logra obtener una llave", "Given apa/metadata").estado == ESTADO_QA
    assert classify_text("El servicio responde 200", "Then el payload cumple el esquema").estado == ESTADO_TECH
    assert classify_text("Persistencia tras recargar la página", "recargar").estado == ESTADO_HPA
    assert classify_text("La Home no se rompe", "conservación de la navegación").estado == ESTADO_REGRESSION
    ok = classify_text("Usuario externo ve el Centro desplegado", "Then se muestra en pantalla")
    assert ok.eligible


def test_filter_bundle_keeps_visible_drops_keys():
    bundle = EpicBundle(
        key="E",
        summary="s",
        technical_stories=[
            TechStory(
                "T",
                "s",
                "",
                [
                    Item("COV-001", "Se muestra el centro", "Then se muestra", "T"),
                    Item("COV-002", "No se logra obtener una llave", "Given apa/metadata vacía", "T"),
                ],
            )
        ],
    )
    filtered, discarded = filter_bundle(bundle)
    assert [i.id for i in filtered.covs] == ["COV-001"]
    assert discarded[0]["estado"] == ESTADO_QA


def test_pack_drops_hpa_keys_and_merges_entry_path():
    bundle = _bundle()
    scenarios = [Scenario("ESC-01", "CN", "d", [], ["CRN-001"], ["COV-001"], "ninguna")]
    cases = [
        _case(titulo="Usuario externo registra y ve el Centro desplegado"),
        _case(
            titulo="Usuario externo ya tiene cuenta y ve el Centro desplegado",
            pasos=[
                {"accion": "Ingresar a la Home", "resultado_esperado": "Se muestra la Home"},
                {"accion": "Observar el Centro", "resultado_esperado": "Se muestra desplegado"},
                {"accion": "Recargar la página", "resultado_esperado": "Sigue igual"},
            ],
        ),
        _case(titulo="Persistencia tras recargar", tipo="HPA"),
        _case(titulo="Ausencia de leyenda si la llave está vacía", tipo="TTF"),
        _case(
            titulo="Visualización conforme a diseño",
            tipo="ERG",
            precondiciones=["Usuario Telmex fuera de casa"],
            pasos=[
                {"accion": "Observar textos y posición", "resultado_esperado": "Coinciden con el diseño aprobado"},
                {"accion": "Comparar botones", "resultado_esperado": "Mismos elementos que en el insumo"},
                {"accion": "Revisar recortes", "resultado_esperado": "Nada recortado ni encimado"},
            ],
        ),
        _case(
            titulo="Usuario externo inicia sesión y ve el Centro replegado",
            pasos=[
                {"accion": "Iniciar sesión", "resultado_esperado": "Entra a la Home"},
                {"accion": "Observar el Centro", "resultado_esperado": "Se muestra replegado"},
                {"accion": "Desplegar", "resultado_esperado": "Muestra los elementos"},
            ],
        ),
    ]
    packed, discarded = consolidate(cases, bundle, scenarios)
    tipos = {c.tipo for c in packed}
    assert "HPA" not in tipos
    assert all("llave" not in c.titulo.lower() for c in packed)
    assert any(c.tipo == "ERG" for c in packed)
    estados = {row["estado"] for row in discarded}
    assert ESTADO_HPA in estados
    deployed = [c for c in packed if "despleg" in (c.titulo + visible_blob(c)).lower()]
    assert len(deployed) == 1
    assert any("opcional" in v["condicion"] for v in deployed[0].variantes)
    assert all(3 <= len(c.pasos) <= 6 for c in packed)
    assert {c.prioridad for c in packed} <= {"BLOCKER", "CRITICAL"}
    assert any((c.riesgo or "").startswith("Major") for c in packed if c.tipo == "ERG")
    assert all(user_label(c) for c in packed)
    assert "  " not in rewrite_title(packed[0])


def visible_blob(case: DesignedCase) -> str:
    return " ".join(s["resultado_esperado"] for s in case.pasos)


def test_rewrite_drops_duplicated_usuario_phrases():
    case = _case(
        titulo="Usuario Telmex fuera de casa observa usuario telmex fuera de casa observa usuario elegible de mexico"
    )
    title = rewrite_title(case)
    assert title.lower().count("usuario") == 1
    assert "…" not in title
    assert title.startswith("Usuario")


def test_pack_relabels_expected_collapsed_state_as_hpp():
    bundle = _bundle()
    scenarios = [Scenario("ESC-01", "CN", "d", [], [], ["COV-002"], "ninguna")]
    packed, _ = consolidate(
        [_case(titulo="Ausencia del centro replegado al iniciar sesión", tipo="TTF")],
        bundle,
        scenarios,
    )
    assert packed[0].tipo == "HPP"


def test_pack_caps_variants_mexico_only():
    bundle = _bundle()
    scenarios = [Scenario("ESC-01", "CN", "d", [], [], ["COV-001"], "ninguna")]
    packed, _ = consolidate(
        [
            _case(
                variantes=[
                    {"condicion": "México", "resultado_esperado": "ok"},
                    {"condicion": "Colombia", "resultado_esperado": "ok"},
                    {"condicion": "Perú", "resultado_esperado": "ok"},
                    {"condicion": "PayPal", "resultado_esperado": "ok"},
                    {"condicion": "Tarjeta", "resultado_esperado": "ok"},
                ]
            )
        ],
        bundle,
        scenarios,
    )
    conditions = [v["condicion"] for v in packed[0].variantes]
    assert len(conditions) <= 3
    assert not any("Colombia" in c or "Perú" in c or "PayPal" in c for c in conditions)


def test_v2b_engine_filters_before_stage_b_and_v2_keeps_hpa():
    from app.services.qc_v2b import engine as v2b

    stage_a = {
        "resumen_funcionalidad": "CN",
        "escenarios": [
            {
                "id": "ESC-01",
                "titulo": "Centro desplegado para externo",
                "descripcion": "se muestra desplegado",
                "condiciones": [],
                "cubre_negocio": ["CRN-001"],
                "cubre_tecnico": ["COV-001"],
                "brecha": "ninguna",
                "es_no_afectacion": False,
            },
            {
                "id": "ESC-02",
                "titulo": "Persistencia tras recargar la página",
                "descripcion": "recargar",
                "condiciones": [],
                "cubre_negocio": [],
                "cubre_tecnico": ["COV-002"],
                "brecha": "ninguna",
                "es_no_afectacion": False,
            },
        ],
        "excluidos": [],
    }

    def casos_v2(_messages):
        return {
            "casos": [
                {**_CASE, "titulo": "Usuario externo ve el Centro desplegado", "tipo": "HPP"},
                {**_CASE, "titulo": "Persistencia tras recargar", "tipo": "HPA"},
            ]
        }

    chat_v2 = _fake_chat({"a": stage_a, "b": casos_v2})
    v2_runs = v2_engine.run_epics(["WEBCL-1586"], "WEB", reader=collect.JiraReader(_FakeJira()), chat=chat_v2)
    v2_tipos = [
        next(r.split("=", 1)[1] for r in c.applied_rules if r.startswith("qc-v2:tipo="))
        for c in v2_runs[0].candidates
    ]
    assert "HPA" in v2_tipos

    chat_v2b = _fake_chat({"a": stage_a, "b": casos_v2})
    v2b_runs = v2b.run_epics(["WEBCL-1586"], "WEB", reader=collect.JiraReader(_FakeJira()), chat=chat_v2b)
    v2b_tipos = [
        next(r.split("=", 1)[1] for r in c.applied_rules if r.startswith("qc-v2:tipo="))
        for c in v2b_runs[0].candidates
    ]
    assert "HPA" not in v2b_tipos
    assert all(c.generation_origin == "qc-v2b" for c in v2b_runs[0].candidates)
    assert any("fuera de paquete" in (row.get("estado") or "") or "variable" in (row.get("estado") or "") for row in v2b_runs[0].ledger)


def test_dispatch_v2b_name():
    from app.config import settings

    assert settings.qc_engine in {"legacy", "v2", "v2b"}
