"""Preview expander: matrix row × applicable device. No persistence, no matrix mutation."""

from app.schemas.coverage_matrix import CoverageMatrixResponse, CoverageMatrixRow
from app.services.operativa_engine.matrix_expand import expand_matrix_preview


def _row(**overrides) -> CoverageMatrixRow:
    data = {
        "brf_key": "BRF-1",
        "epc_keys": ["EPC-1", "EPC-2"],
        "hn_keys": ["HN001"],
        "behavior_key": "BRF-1:HN001:demo",
        "behavior_title": "Comportamiento demo",
        "interaction_points": ["Plan Selector"],
        "channel": None,
        "ecosystem": "OTT",
        "applicable_devices": ["WEB", "iOS"],
        "relevant_users": ["Suscrito", "No suscrito"],
        "transactional": True,
        "mdp": ["Visa", "Telmex"],
        "test_data": "dato-fuente",
        "origin": "directo",
        "scope_status": "IN_SCOPE",
        "duplicate_risk": "UNIQUE",
        "evidence": "extracto HN001",
        "applicability_reason": "universo OTT",
        "reasoning": "razonamiento de matriz",
    }
    data.update(overrides)
    return CoverageMatrixRow(**data)


def _matrix(*rows: CoverageMatrixRow) -> CoverageMatrixResponse:
    return CoverageMatrixResponse(
        status="MATRIX",
        engine="test",
        release_id=10,
        release_name="OPE-preview",
        brfs_analyzed=len({row.brf_key for row in rows}),
        row_count=len(rows),
        rows=list(rows),
    )


def test_expand_one_behavior_per_device_not_epc_user_or_mdp() -> None:
    preview = expand_matrix_preview(_matrix(_row(relevant_users=[])))
    assert preview.persisted is False
    assert preview.jira is False
    assert preview.zephyr is False
    assert preview.preview_tc_count == 2
    assert [case.device for case in preview.cases] == ["WEB", "iOS"]
    assert all(case.behavior_key == "BRF-1:HN001:demo" for case in preview.cases)
    assert all(case.epc_keys == ["EPC-1", "EPC-2"] for case in preview.cases)
    assert all(case.mdp == ["Visa", "Telmex"] for case in preview.cases)
    assert all(case.interaction_points == ["Plan Selector"] for case in preview.cases)
    assert all(case.test_data == "dato-fuente" for case in preview.cases)
    assert all(case.country is None for case in preview.cases)
    assert all(case.use_case_key == "default" for case in preview.cases)


def test_expand_independent_users_before_devices() -> None:
    preview = expand_matrix_preview(_matrix(_row()))
    assert preview.preview_tc_count == 4
    pairs = {(case.user_type, case.device) for case in preview.cases}
    assert pairs == {
        ("Suscrito", "WEB"),
        ("Suscrito", "iOS"),
        ("No suscrito", "WEB"),
        ("No suscrito", "iOS"),
    }
    assert all(case.mdp == ["Visa", "Telmex"] for case in preview.cases)
    assert len({case.use_case_key for case in preview.cases}) == 2


def test_expand_does_not_multiply_interaction_points() -> None:
    preview = expand_matrix_preview(
        _matrix(
            _row(
                relevant_users=[],
                interaction_points=["Plan Selector", "Landing Comercial", "vCard", "Home"],
            )
        )
    )
    assert preview.preview_tc_count == 2
    assert all(
        case.interaction_points == ["Plan Selector", "Landing Comercial", "vCard", "Home"]
        for case in preview.cases
    )


def test_expand_vod_and_live_are_independent_use_cases() -> None:
    preview = expand_matrix_preview(
        _matrix(
            _row(
                relevant_users=[],
                applicable_devices=["WEB"],
                evidence=(
                    "HN001 Alta de canales.\n"
                    "Usuario suscrito puede reproducir.\n"
                    "Suscripción desde VOD obtiene acceso.\n"
                    "Suscripción desde Live obtiene acceso.\n"
                ),
            )
        )
    )
    assert preview.preview_tc_count == 2
    assert {case.access_path for case in preview.cases} == {"VOD", "Live"}


def test_expand_explicit_countries_times_devices() -> None:
    preview = expand_matrix_preview(
        _matrix(
            _row(
                relevant_users=[],
                evidence=(
                    "Criterios de aceptación\n"
                    "- El Salvador:\n"
                    "- Guatemala:\n"
                    "- Honduras:\n"
                    "El canal NO debe ser mostrado en la grilla.\n"
                ),
                applicable_devices=["WEB", "iOS"],
            )
        )
    )
    assert preview.preview_tc_count == 6
    pairs = {(case.country, case.device) for case in preview.cases}
    assert pairs == {
        ("El Salvador", "WEB"),
        ("El Salvador", "iOS"),
        ("Guatemala", "WEB"),
        ("Guatemala", "iOS"),
        ("Honduras", "WEB"),
        ("Honduras", "iOS"),
    }


def test_expand_skips_qc_review_and_out_of_scope() -> None:
    preview = expand_matrix_preview(
        _matrix(
            _row(behavior_key="a", origin="QC_REVIEW", applicable_devices=["WEB"], relevant_users=[]),
            _row(
                behavior_key="b",
                origin="directo",
                scope_status="OUT_OF_SCOPE",
                applicable_devices=["WEB"],
                relevant_users=[],
            ),
            _row(behavior_key="c", origin="directo", applicable_devices=["WEB"], relevant_users=[]),
        )
    )
    assert preview.preview_tc_count == 1
    assert preview.cases[0].behavior_key == "c"
    summary = preview.summary[0]
    assert summary.qc_review_omitted == 1
    assert summary.out_of_scope_omitted == 1
    assert summary.preview_tcs == 1
    omitted = [row for row in preview.report if not row.generated]
    assert len(omitted) == 2


def test_expand_email_without_devices_is_one_channel_tc() -> None:
    preview = expand_matrix_preview(
        _matrix(
            _row(
                channel="Email",
                applicable_devices=[],
                ecosystem=None,
                relevant_users=["Registrado (tras alta)"],
                transactional=False,
                mdp=[],
            )
        )
    )
    assert preview.preview_tc_count == 1
    case = preview.cases[0]
    assert case.device is None
    assert case.channel == "Email"
    assert case.relevant_users == ["Registrado (tras alta)"]
    assert preview.report[0].generated is True


def test_expand_empty_devices_without_channel_warns_and_generates_zero() -> None:
    preview = expand_matrix_preview(_matrix(_row(applicable_devices=[], channel=None)))
    assert preview.preview_tc_count == 0
    assert preview.warnings
    assert preview.summary[0].warnings == 1
    assert preview.report[0].generated is False


def test_expand_does_not_invent_behavior_or_polarity() -> None:
    row = _row(behavior_title="No implementar chapita", origin="directo", relevant_users=[])
    preview = expand_matrix_preview(_matrix(row))
    assert {case.behavior_title for case in preview.cases} == {"No implementar chapita"}
    assert {case.behavior_key for case in preview.cases} == {row.behavior_key}
    assert all(case.origin == "directo" for case in preview.cases)
