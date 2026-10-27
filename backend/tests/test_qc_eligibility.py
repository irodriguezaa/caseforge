from app.services.gherkin_coverage import expand_for_eval
from app.services.qc_eligibility import (
    evaluate_scenario,
    impact_user_view,
    is_consumed_device_impact,
    select_qc_gherkin,
)


def test_user_visible_control_passes() -> None:
    elig = evaluate_scenario(
        "Apagar funcionalidad de Canales recientes",
        "Given la configuración está deshabilitada\n"
        "When el usuario abre el Control Player\n"
        'Then no se muestra el botón de "Canales recientes"\n',
    )
    assert elig.ok
    assert elig.surface == "boton"


def test_architecture_delivery_fails_actor_and_device() -> None:
    elig = evaluate_scenario(
        "Entregar listado a Arquitectura",
        "When la fábrica entrega el listado a Arquitectura\n"
        "Then la entrega queda formalizada\n",
    )
    assert not elig.ok
    assert elig.pending is False
    assert "actor no es el usuario final de la app" in elig.reasons


def test_logo_on_device_passes() -> None:
    elig = evaluate_scenario(
        "El modal de información de PIN muestra el logotipo de la operación",
        "When el usuario abre el modal de información de PIN\n"
        "Then se muestra el logotipo de la operación\n",
    )
    assert elig.ok
    assert elig.surface == "marca-modales"


def test_consumed_placeholder_is_surface_impact() -> None:
    elig = evaluate_scenario(
        "Los placeholders dejan de usar las llaves anteriores",
        "When se aplica el cambio\n"
        "Then pasan a consultar la llave de placeholder que corresponde a su forma de tarjeta\n",
    )
    assert not elig.ok
    assert elig.actor_ok is True
    assert elig.device_ok is False
    assert is_consumed_device_impact(elig)
    action, then = impact_user_view(elig.surface or "", "Los placeholders dejan de usar las llaves anteriores")
    assert "placeholder" in then
    assert "llave" not in then
    assert "usuario" in action


def test_select_qc_gherkin_keeps_impact_not_duplicate_direct() -> None:
    kept, dropped = select_qc_gherkin(
        "EPC-1",
        [
            (
                "ST-1",
                "Los placeholders dejan de usar las llaves anteriores",
                "When se aplica el cambio\nThen pasan a consultar la llave de placeholder que corresponde a su forma de tarjeta",
                "assets",
            ),
            (
                "ST-1",
                "El usuario ve el home",
                "When el usuario abre la aplicación\nThen se muestra el home",
                "",
            ),
        ],
    )
    titles = {row.title for row in kept}
    assert "Los placeholders dejan de usar las llaves anteriores" in titles
    assert any(row.kind == "impacto" for row in kept)
    assert "El usuario ve el home" in titles


def test_perceived_then_is_not_technical() -> None:
    samples = [
        (
            "Pausar la reproducción al abrir el Panel de Audio y Subtítulos",
            "When el usuario abre el Panel de Audio y Subtítulos\nThen la reproducción se pausa\n",
        ),
        (
            "Solicitar PIN al intentar bloquear un canal",
            "When el usuario intenta bloquear un canal\nThen se solicita el PIN\n",
        ),
        (
            "Arrastrar ventana PIP",
            "When el usuario arrastra la ventana PIP\nThen la ventana se mueve con el puntero\n",
        ),
        (
            "Selección de fecha en Filtro",
            "When el usuario selecciona una fecha en el filtro\nThen se muestran los eventos de esa fecha\n",
        ),
        (
            "La vinculación no se completa",
            "When el usuario intenta vincular la cuenta\nThen la vinculación no se completa\nAnd se muestra un mensaje\n",
        ),
    ]
    for title, body in samples:
        elig = evaluate_scenario(title, body)
        assert elig.ok, (title, elig.reasons, elig.pending)


def test_then_without_tech_object_is_visible() -> None:
    elig = evaluate_scenario(
        "Progress bar en el Panel de Más información",
        "When el usuario abre el panel\nThen no deben mostrarse los siguientes elementos: tiempo, marca\n",
    )
    assert elig.ok
    assert not elig.pending


def test_then_list_without_pipes_is_visible() -> None:
    title, body = expand_for_eval(
        "Elementos visibles",
        "When el usuario abre la guía\n"
        "Then no deben mostrarse los siguientes elementos\n"
        "Indicador de tiempo\n"
        "Indicador de duración\n",
        [],
    )
    elig = evaluate_scenario(title, body)
    assert elig.ok
    assert not elig.pending


def test_empty_then_is_pending() -> None:
    elig = evaluate_scenario("Líneas a mostrar de Sinopsis", "When el usuario abre el panel\nThen\n")
    assert elig.pending
    assert elig.ledger_estado == "pendiente de revisión QC"


def test_pipeline_and_logs_fail_device() -> None:
    elig = evaluate_scenario(
        "El manifiesto es auditable",
        "When se revisa el manifiesto de un release\nThen indica el hash\n",
    )
    assert not elig.ok
    assert "el resultado no se verifica mirando el dispositivo" in elig.reasons
