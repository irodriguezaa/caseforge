from app.services.rn_vendor import detect_rn_vendor
from tests.test_release_note_analyzer import ALL_FIXTURES
from tests.test_tata_release_note_parser import LAUNCHER_9122, STV_LG, _bytes


def test_default_vendor_is_damco_when_signals_are_absent() -> None:
    assert detect_rn_vendor("random.pdf", b"%PDF-1.4 unrelated") == "damco"


def test_filename_damco_wins_over_tata_substring() -> None:
    assert detect_rn_vendor("DAMCO-RN-CV_-_WEB_-16_9_1.pdf") == "damco"


def test_all_checked_in_damco_rns_detect_as_damco() -> None:
    for filename in ALL_FIXTURES:
        assert detect_rn_vendor(filename, _bytes(filename)) == "damco"


def test_tata_body_without_atstata_prefix() -> None:
    assert detect_rn_vendor(STV_LG, _bytes(STV_LG)) == "tata"
    assert detect_rn_vendor(LAUNCHER_9122, _bytes(LAUNCHER_9122)) == "tata"
