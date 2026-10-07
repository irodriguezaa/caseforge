from types import SimpleNamespace

from app.services.test_case_export import epic_progress_rows, split_stored_test_data


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


def _case(**kwargs):
    defaults = {
        "component": "ADTCL-1",
        "technical_epic": None,
        "hn_source": None,
        "status": "UNEXECUTED",
        "estimation_hours": 0.2,
        "test_case_id": "QC-001",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_epic_progress_counts_anything_but_unexecuted() -> None:
    rows = epic_progress_rows(
        [
            _case(status="UNEXECUTED", test_case_id="QC-001"),
            _case(status="PASS", test_case_id="QC-002"),
            _case(component="ADTCL-1 | ADTCL-9", status="FAIL", test_case_id="QC-003"),
            _case(component="ADTCL-2", status="BLOCKED", estimation_hours=0.4, test_case_id="QC-004"),
        ]
    )
    by_key = {row["key"]: row for row in rows}
    assert by_key["ADTCL-1"]["total"] == 3
    assert by_key["ADTCL-1"]["executed"] == 2
    assert by_key["ADTCL-1"]["percent"] == 66.7
    assert by_key["ADTCL-2"]["executed"] == 1
    assert by_key["ADTCL-2"]["total"] == 1
