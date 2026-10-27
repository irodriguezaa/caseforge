from app.services.qc_eligibility import (
    evaluate_scenario,
    impact_user_view,
    is_consumed_device_impact,
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


def test_pipeline_and_logs_fail_device() -> None:
    elig = evaluate_scenario(
        "El manifiesto es auditable",
        "When se revisa el manifiesto de un release\nThen indica el hash\n",
    )
    assert not elig.ok
    assert "el resultado no se verifica mirando el dispositivo" in elig.reasons
