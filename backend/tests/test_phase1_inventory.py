"""Phase 1 (P0): inventory sources, last-resort gate, key vs flag classification."""

from app.services.ai_case_engine import (
    generate_release_app_candidates,
    last_resort_applies,
)
from app.services.gherkin_coverage import build_coverage_inventory
from app.services.scenario_classifier import classify_scenario


def _ux_gherkin(title: str = "Completar pago") -> str:
    return (
        f"Feature: flujo\n"
        f"Scenario: {title}\n"
        "  When el usuario selecciona pagar con PayPal\n"
        "  Then se muestra el modal de confirmación y el usuario ve el resultado\n"
    )


def test_gherkin_in_acceptance_criteria_creates_coverage_unit() -> None:
    artifacts = [
        {
            "key": "WINCL-219",
            "issuetype": "Epic",
            "summary": "Navegación secundaria",
            "description": "",
            "acceptance_criteria": "",
            "children": [
                {
                    "key": "WINCL-220",
                    "summary": "Feature: Reproducción de canal",
                    "description": "",
                    "acceptance_criteria": (
                        "Scenario: Reproducción de canal por primera vez\n"
                        "  When el usuario entra a TV en vivo\n"
                        "  Then se reproduce el canal y se muestra el player\n"
                    ),
                }
            ],
        }
    ]
    units = build_coverage_inventory(artifacts, "xbox.pdf")
    assert len(units) == 1
    assert units[0].scenario == "Reproducción de canal por primera vez"
    assert units[0].role in {"A", "G"}
    assert units[0].rn_key == "WINCL-219"
    assert units[0].jira_key == "WINCL-220"


def test_non_feature_child_with_gherkin_creates_coverage_unit() -> None:
    artifacts = [
        {
            "key": "ADTCL-2787",
            "issuetype": "Epic",
            "summary": "Migración de usuario",
            "description": "",
            "acceptance_criteria": "",
            "children": [
                {
                    "key": "ADTCL-2800",
                    "summary": "User Story: Migración de marca visible",
                    "description": (
                        "Scenario: El usuario ve la marca migrada\n"
                        "  When el usuario abre la aplicación\n"
                        "  Then se muestra la pantalla con la marca Claro tv+\n"
                    ),
                    "acceptance_criteria": "",
                }
            ],
        }
    ]
    units = build_coverage_inventory(artifacts, "adt.pdf")
    assert len(units) == 1
    assert "marca" in units[0].scenario.lower() or "marca" in units[0].behavior.lower()
    assert units[0].jira_key == "ADTCL-2800"


def test_duplicate_gherkin_in_description_and_ac_is_not_doubled() -> None:
    gherkin = (
        "Scenario: Acceso a la Guía\n"
        "  When el usuario presiona abajo\n"
        "  Then se muestra la Guía de programación\n"
    )
    artifacts = [
        {
            "key": "WINCL-186",
            "children": [
                {
                    "key": "WINCL-187",
                    "summary": "Feature guía",
                    "description": gherkin,
                    "acceptance_criteria": gherkin,
                }
            ],
        }
    ]
    units = build_coverage_inventory(artifacts, "xbox.pdf")
    assert len(units) == 1


def test_empty_feature_does_not_fall_back_to_epic_gherkin() -> None:
    artifacts = [
        {
            "key": "WINCL-219",
            "summary": "Navegación secundaria",
            "description": (
                "Scenario: Reproducción del último canal visto por el perfil\n"
                "  When el usuario entra a TV en vivo\n"
                "  Then se muestra el player del último canal del perfil\n"
            ),
            "acceptance_criteria": "",
            "children": [
                {
                    "key": "WINCL-220",
                    "summary": "Feature: Reproducción de canal",
                    "description": "Feature: Reproducción de canal en TV en vivo\n",
                    "acceptance_criteria": "",
                }
            ],
        }
    ]
    units = build_coverage_inventory(artifacts, "xbox.pdf")
    assert units == []


def test_epic_is_source_when_it_has_no_stories() -> None:
    artifacts = [
        {
            "key": "WINCL-219",
            "summary": "Navegación secundaria",
            "issuetype": "Technical Epic",
            "description": (
                "Scenario: Reproducción del último canal visto por el perfil\n"
                "  When el usuario entra a TV en vivo\n"
                "  Then se muestra el player del último canal del perfil\n"
            ),
            "acceptance_criteria": "",
            "children": [],
        }
    ]
    units = build_coverage_inventory(artifacts, "xbox.pdf")
    assert len(units) == 1
    assert "último canal" in units[0].scenario.lower()


def test_technical_key_scenario_is_not_ag() -> None:
    clf = classify_scenario(
        "Alta de llaves de configuración en el dispositivo",
        "When el backend publica las llaves\n"
        "Then se crean las llaves en apa/metadata\n",
    )
    assert clf.role == "B"
    units = build_coverage_inventory(
        [
            {
                "key": "WINCL-462",
                "children": [
                    {
                        "key": "WINCL-463",
                        "summary": "Feature: Alta de llaves",
                        "description": (
                            "Scenario: Alta de llaves de configuración en el dispositivo\n"
                            "  When el backend publica las llaves\n"
                            "  Then se crean las llaves en apa/metadata\n"
                        ),
                    }
                ],
            }
        ],
        "xbox.pdf",
    )
    assert units == []


def test_flag_that_hides_visible_control_stays_ag() -> None:
    clf = classify_scenario(
        "Apagar funcionalidad de Canales recientes",
        "Given la llave show_recent_channels está deshabilitada en la configuración\n"
        "When el usuario abre el Control Player\n"
        'Then no se muestra el botón de "Canales recientes"\n',
    )
    assert clf.role in {"A", "G"}
    units = build_coverage_inventory(
        [
            {
                "key": "WINCL-226",
                "children": [
                    {
                        "key": "WINCL-228",
                        "summary": "User Story: llave canales recientes",
                        "description": (
                            "Scenario: Apagar funcionalidad de Canales recientes\n"
                            "  Given la llave show_recent_channels está deshabilitada\n"
                            "  When el usuario abre el Control Player\n"
                            '  Then no se muestra el botón de "Canales recientes"\n'
                        ),
                    }
                ],
            }
        ],
        "xbox.pdf",
    )
    assert len(units) == 1
    assert units[0].role in {"A", "G"}


def test_metrics_scenario_is_not_coverage() -> None:
    units = build_coverage_inventory(
        [
            {
                "key": "WINCL-823",
                "children": [
                    {
                        "key": "WINCL-824",
                        "summary": "Feature: setup de métricas",
                        "description": (
                            "Scenario: Implementación inicial del setup de métricas\n"
                            "  When se instrumenta el pipeline\n"
                            "  Then el esquema de métricas cumple el pipeline\n"
                        ),
                    }
                ],
            }
        ],
        "xbox.pdf",
    )
    assert units == []


def test_last_resort_gate_reference_cells() -> None:
    assert last_resort_applies(
        "ADTCL-2787: Migración de usuario a la marca Claro tv+", "ADTCL-2787"
    )
    assert last_resort_applies(
        "WINCL-219: Incorporación de reglas de navegación secundaria", "WINCL-219"
    )
    assert last_resort_applies(
        "ADTCL-419: Registro de usuario y envío de subregión en login", "ADTCL-419"
    )
    assert not last_resort_applies(
        "WINCL-823: Integración y cumplimiento del setup de métricas", "WINCL-823"
    )
    assert not last_resort_applies(
        'METADATA: Alta de llaves de configuración en el dispositivo – "Player de TV"',
        "WINCL-462",
    )
    assert not last_resort_applies(
        "METADATA: Alta de llaves de configuración – Timeshift pantallas Grandes",
        "WINCL-464",
    )
    assert not last_resort_applies(
        "METADATA: Alta de llaves de configuración – NPVR pantallas Grandes",
        "WINCL-465",
    )
    assert not last_resort_applies(
        "ADTCL-2798: HITSS SmartLib retiro NanoCDN", "ADTCL-2798"
    )
    assert not last_resort_applies(
        "ADTCL-653: Integración y cumplimiento del setup de métricas", "ADTCL-653"
    )


def _run_generation(monkeypatch, tickets: list[tuple[str, str]], artifacts: list[dict]):
    from dataclasses import replace

    from app.config import settings

    monkeypatch.setattr(
        "app.services.ai_case_engine.settings",
        replace(settings, openai_api_key=""),
    )
    monkeypatch.setattr(
        "app.services.ai_case_engine.fetch_artifacts_for_keys",
        lambda _keys: artifacts,
    )
    return generate_release_app_candidates(
        release_id=1,
        release_name="P0",
        validation_type=None,
        analysis_present=True,
        rn_filename="rn.pdf",
        pdf_bytes=b"%PDF-placeholder",
        release_context={},
        existing_cases=[],
        tickets={"functionality": tickets, "nco": [], "tri": [], "qa_qc": []},
    )


def test_empty_feature_uses_gated_last_resort_when_other_inventory_exists(monkeypatch) -> None:
    artifacts = [
        {
            "key": "WINCL-182",
            "issuetype": "Epic",
            "summary": "Panel metadata",
            "description": _ux_gherkin(),
            "children": [
                {
                    "key": "WINCL-185",
                    "summary": "Feature panel",
                    "description": _ux_gherkin("Construcción del Panel de metadata"),
                    "acceptance_criteria": "",
                }
            ],
        },
        {
            "key": "WINCL-219",
            "issuetype": "Epic",
            "summary": "Navegación secundaria",
            "description": "",
            "children": [
                {
                    "key": "WINCL-220",
                    "summary": "Feature: Reproducción de canal",
                    "description": "Feature: Reproducción de canal en TV en vivo\n",
                    "acceptance_criteria": "",
                }
            ],
        },
        {
            "key": "ADTCL-2787",
            "issuetype": "Epic",
            "summary": "Migración de usuario",
            "description": "",
            "children": [],
        },
    ]
    tickets = [
        ("WINCL-182", "WINCL-182: Incorporación del Nuevo Panel de Metadata en el Player"),
        ("WINCL-219", "WINCL-219: Incorporación de reglas de navegación secundaria"),
        ("ADTCL-2787", "ADTCL-2787: Migración de usuario a la marca Claro tv+"),
        ("WINCL-823", "WINCL-823: Integración y cumplimiento del setup de métricas"),
        ("WINCL-462", "METADATA: Alta de llaves de configuración en el dispositivo"),
        ("WINCL-464", "METADATA: Alta de llaves de configuración – Timeshift"),
        ("WINCL-465", "METADATA: Alta de llaves de configuración – NPVR"),
        ("ADTCL-2798", "ADTCL-2798: HITSS SmartLib retiro NanoCDN"),
        ("ADTCL-653", "ADTCL-653: Integración y cumplimiento del setup de métricas"),
    ]
    response = _run_generation(monkeypatch, tickets, artifacts)
    keys = {
        (row.related_jira or row.related_functionality or "").split("|")[0].strip().upper()
        for row in response.candidates
    }
    last_resort = [row for row in response.candidates if row.basic_validation]
    last_keys = {
        (row.related_jira or "").upper()
        for row in last_resort
    }
    assert "WINCL-219" in last_keys
    assert "ADTCL-2787" in last_keys
    assert "WINCL-823" not in last_keys
    assert "WINCL-462" not in last_keys
    assert "WINCL-464" not in last_keys
    assert "WINCL-465" not in last_keys
    assert "ADTCL-2798" not in last_keys
    assert "ADTCL-653" not in last_keys
    assert sum(1 for row in last_resort if (row.related_jira or "").upper() == "WINCL-219") == 1
    assert sum(1 for row in last_resort if (row.related_jira or "").upper() == "ADTCL-2787") == 1
    assert any(not row.basic_validation for row in response.candidates)
    assert "WINCL-182" in keys or any(
        "COV-" in (cid or "") for row in response.candidates for cid in (row.covers or [])
    )


def test_llm_path_still_adds_gated_last_resort(monkeypatch) -> None:
    from dataclasses import replace
    from unittest.mock import MagicMock, patch
    import json

    from app.config import settings

    monkeypatch.setattr(
        "app.services.ai_case_engine.settings",
        replace(settings, openai_api_key="sk-test", openai_model="gpt-4o-mini"),
    )
    artifacts = [
        {
            "key": "WINCL-182",
            "children": [
                {
                    "key": "WINCL-185",
                    "summary": "Feature panel",
                    "description": _ux_gherkin("Construcción del Panel"),
                }
            ],
        },
        {
            "key": "WINCL-219",
            "children": [
                {
                    "key": "WINCL-220",
                    "summary": "Feature vacía",
                    "description": "Feature: canal\n",
                }
            ],
        },
    ]
    monkeypatch.setattr(
        "app.services.ai_case_engine.fetch_artifacts_for_keys",
        lambda _keys: artifacts,
    )
    payload = {
        "candidates": [
            {
                "name": "Construcción del Panel",
                "description": "UX",
                "steps": [
                    {
                        "step_number": 1,
                        "action": "El usuario inicia reproducción",
                        "expected_result": "Se muestra el panel de metadata",
                    }
                ],
                "related_functionality": "WINCL-182",
                "related_jira": "WINCL-182",
                "evidence": "COV",
                "justification": "LLM",
                "review_required": True,
                "covers": ["COV-001"],
            }
        ]
    }
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "choices": [{"message": {"content": json.dumps(payload)}}]
    }
    fake_client = MagicMock()
    fake_client.post.return_value = fake_response
    tickets = [
        ("WINCL-182", "WINCL-182: Panel de metadata en el Player"),
        ("WINCL-219", "WINCL-219: reglas de navegación secundaria"),
        ("WINCL-823", "WINCL-823: setup de métricas"),
    ]
    with patch("app.services.ai_case_engine.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value = fake_client
        response = generate_release_app_candidates(
            release_id=1,
            release_name="P0-LLM",
            validation_type=None,
            analysis_present=True,
            rn_filename="rn.pdf",
            pdf_bytes=b"%PDF-placeholder",
            release_context={},
            existing_cases=[],
            tickets={"functionality": tickets, "nco": [], "tri": [], "qa_qc": []},
        )
    last_keys = {
        (row.related_jira or "").upper()
        for row in response.candidates
        if row.basic_validation
    }
    assert "WINCL-219" in last_keys
    assert "WINCL-823" not in last_keys
    assert any(row.covers == ["COV-001"] or "COV-001" in (row.covers or []) for row in response.candidates)
