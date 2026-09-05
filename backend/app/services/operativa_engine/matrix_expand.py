"""Preview expansion: behavior → use cases → country (if explicit) → device.

Does not persist, create Jira/Zephyr issues, or change matrix rows / HN / scope.
Interaction points, EPC, MDP catalogues and ofertas are not cartesianized here.
"""

from __future__ import annotations

from app.schemas.coverage_matrix import CoverageMatrixResponse, CoverageMatrixRow
from app.schemas.matrix_preview import (
    MatrixPreviewResponse,
    PreviewBrfSummary,
    PreviewReportRow,
    PreviewTestCase,
)
from app.services.operativa_engine.coverage_matrix import CHANNEL_EMAIL
from app.services.operativa_engine.matrix_steps import extract_countries
from app.services.operativa_engine.use_cases import FunctionalUseCase, extract_use_cases

ENGINE_VERSION = "operativa-v4.0-use-case-exec"

_EXECUTABLE_ORIGINS = frozenset({"directo", "derivado"})


def expand_matrix_preview(matrix: CoverageMatrixResponse) -> MatrixPreviewResponse:
    """Expand an already-built matrix. Does not rebuild or correct matrix rows."""
    cases: list[PreviewTestCase] = []
    report: list[PreviewReportRow] = []
    warnings: list[str] = []
    stats: dict[str, PreviewBrfSummary] = {}

    for row in matrix.rows:
        summary = stats.setdefault(row.brf_key, PreviewBrfSummary(brf_key=row.brf_key))
        summary.matrix_rows += 1
        if row.scope_status == "OUT_OF_SCOPE":
            summary.out_of_scope_omitted += 1
        if row.origin == "QC_REVIEW":
            summary.qc_review_omitted += 1

        skip = _omit_reason(row)
        if skip:
            report.append(_report_row(row, device="—", generated=False, reason=skip))
            continue

        use_cases = extract_use_cases(row)
        countries = _row_countries(row)
        country_axis = countries if len(countries) >= 2 else ([countries[0]] if countries else [None])
        devices = list(row.applicable_devices)

        if row.channel == CHANNEL_EMAIL and not devices:
            summary.executable_rows += 1
            for use_case in use_cases:
                for country in country_axis:
                    summary.devices_expanded += 1
                    summary.preview_tcs += 1
                    reason = _expansion_reason(countries, device=False, use_case=use_case)
                    cases.append(
                        _preview_case(
                            row, device=None, country=country, use_case=use_case, reason=reason
                        )
                    )
                    report.append(_report_row(row, device="—", generated=True, reason=reason))
            continue

        if not devices:
            warning = (
                f"{row.brf_key} {row.behavior_key}: IN_SCOPE ejecutable sin dispositivos "
                "ni canal Email; 0 TCs."
            )
            warnings.append(warning)
            summary.warnings += 1
            report.append(
                _report_row(
                    row,
                    device="—",
                    generated=False,
                    reason="IN_SCOPE ejecutable sin dispositivos ni canal; 0 TCs.",
                )
            )
            continue

        summary.executable_rows += 1
        for use_case in use_cases:
            reason = _expansion_reason(countries, device=True, use_case=use_case)
            for country in country_axis:
                for device in devices:
                    summary.devices_expanded += 1
                    summary.preview_tcs += 1
                    cases.append(
                        _preview_case(
                            row, device=device, country=country, use_case=use_case, reason=reason
                        )
                    )
                    report.append(_report_row(row, device=device, generated=True, reason=reason))

    ordered = _ordered_summaries(matrix, stats)
    return MatrixPreviewResponse(
        engine=ENGINE_VERSION,
        release_id=matrix.release_id,
        release_name=matrix.release_name,
        persisted=False,
        jira=False,
        zephyr=False,
        matrix_row_count=len(matrix.rows),
        preview_tc_count=len(cases),
        cases=cases,
        report=report,
        summary=ordered,
        warnings=warnings,
        source_matrix=list(matrix.rows),
    )


def _row_countries(row: CoverageMatrixRow) -> list[str]:
    blob = "\n".join(part for part in (row.evidence, row.test_data, row.behavior_title) if part)
    return extract_countries(blob)


def _expansion_reason(countries: list[str], *, device: bool, use_case: FunctionalUseCase) -> str:
    scenario = (
        f"1 caso de uso ({use_case.title or 'comportamiento'})"
        if use_case.key != "default"
        else "1 caso de uso (comportamiento sin escenarios independientes)"
    )
    if len(countries) >= 2 and device:
        return f"{scenario} × 1 país/región declarado × 1 dispositivo aplicable. {use_case.reason}"
    if len(countries) >= 2:
        return f"{scenario} × 1 país/región declarado × canal Email. {use_case.reason}"
    if device:
        return f"{scenario} × 1 dispositivo aplicable. {use_case.reason}"
    return f"{scenario} × canal Email. {use_case.reason}"


def _omit_reason(row: CoverageMatrixRow) -> str | None:
    if row.scope_status == "OUT_OF_SCOPE":
        return "OUT_OF_SCOPE; 0 TCs."
    if row.origin == "QC_REVIEW" or row.origin not in _EXECUTABLE_ORIGINS:
        return "QC_REVIEW / origen no ejecutable; 0 TCs automáticos."
    return None


def _preview_case(
    row: CoverageMatrixRow,
    *,
    device: str | None,
    country: str | None,
    use_case: FunctionalUseCase,
    reason: str,
) -> PreviewTestCase:
    return PreviewTestCase(
        brf_key=row.brf_key,
        hn_keys=list(row.hn_keys),
        behavior_key=row.behavior_key,
        behavior_title=row.behavior_title,
        interaction_points=list(row.interaction_points),
        channel=row.channel,
        ecosystem=row.ecosystem,
        device=device,
        country=country,
        use_case_key=use_case.key,
        use_case_title=use_case.title,
        user_type=use_case.user,
        access_path=use_case.access_path,
        polarity=use_case.polarity,  # type: ignore[arg-type]
        applicable_devices=list(row.applicable_devices),
        relevant_users=list(row.relevant_users),
        transactional=row.transactional,
        mdp=list(row.mdp),
        test_data=row.test_data,
        epc_keys=list(row.epc_keys),
        origin=row.origin,
        scope_status=row.scope_status,
        duplicate_risk=row.duplicate_risk,
        duplicate_with=list(row.duplicate_with),
        reasoning=row.reasoning,
        evidence=row.evidence,
        expansion_reason=reason,
    )


def _report_row(
    row: CoverageMatrixRow,
    *,
    device: str,
    generated: bool,
    reason: str,
) -> PreviewReportRow:
    return PreviewReportRow(
        brf_key=row.brf_key,
        hn="; ".join(row.hn_keys) if row.hn_keys else "—",
        behavior=row.behavior_title,
        device=device,
        channel=row.channel or "—",
        generated=generated,
        reason=reason,
    )


def _ordered_summaries(
    matrix: CoverageMatrixResponse,
    stats: dict[str, PreviewBrfSummary],
) -> list[PreviewBrfSummary]:
    order: list[str] = []
    seen: set[str] = set()
    for row in matrix.rows:
        if row.brf_key not in seen:
            seen.add(row.brf_key)
            order.append(row.brf_key)
    return [stats[key] for key in order if key in stats]
