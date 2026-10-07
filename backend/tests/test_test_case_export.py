from app.services.test_case_export import split_stored_test_data


def test_split_stored_test_data_matches_case_page() -> None:
    raw = (
        'Precondición: la llave "show_quick_guide_player" tiene "enable" en false\n'
        '{"show_quick_guide_player": false}; se obtiene la configuracion de la region; '
        "Intención de prueba: Validar la experiencia."
    )
    precondition, data, notes = split_stored_test_data(raw)
    assert "show_quick_guide_player" in precondition
    assert "show_quick_guide_player = false" in data
    assert "se obtiene la configuracion" in notes
    assert "Intención de prueba" in notes
