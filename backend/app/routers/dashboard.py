"""QC Dashboard summary endpoints.

GET /summary      -- original simple counts (kept for backward compatibility).
GET /qc-summary   -- redesigned QC Dashboard backing endpoint: "what is QC doing now, how far
                     along are we, what's at risk", with combinable filters (month, release,
                     operational window, release window, cluster).
"""

from calendar import monthrange
from collections import Counter
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.defect import Defect
from app.models.release import Release, ReleaseStatus
from app.models.test_case import TestCase, TestCasePriority, TestCaseStatus
from app.models.window import OperationalWindow, ReleaseWindow, WindowStatus
from app.schemas.dashboard import ActivityItem, AtRiskItem, DashboardSummary, QcDashboardSummary

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

# A window is flagged at risk if its executed ratio trails its elapsed-time ratio by more than
# this margin, or if it has any BLOCKED test case, or if FAIL exceeds this share of executed.
_RISK_SCHEDULE_TOLERANCE = 0.15
_RISK_FAIL_RATIO_THRESHOLD = 0.15


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummary:
    releases_total = db.execute(select(func.count(Release.id))).scalar_one()
    releases_by_status = db.execute(
        select(Release.status, func.count(Release.id)).group_by(Release.status)
    ).all()

    test_cases_total = db.execute(select(func.count(TestCase.id))).scalar_one()
    test_cases_by_status = db.execute(
        select(TestCase.status, func.count(TestCase.id)).group_by(TestCase.status)
    ).all()
    test_cases_by_priority = db.execute(
        select(TestCase.priority, func.count(TestCase.id)).group_by(TestCase.priority)
    ).all()

    return DashboardSummary(
        releases_total=releases_total,
        releases_by_status={status.value: count for status, count in releases_by_status},
        test_cases_total=test_cases_total,
        test_cases_by_status={status.value: count for status, count in test_cases_by_status},
        test_cases_by_priority={
            priority.value: count for priority, count in test_cases_by_priority
        },
    )


def _parse_month(month: str) -> tuple[date, date]:
    try:
        year_str, month_str = month.split("-")
        year, month_num = int(year_str), int(month_str)
        start = date(year, month_num, 1)
        end = date(year, month_num, monthrange(year, month_num)[1])
    except (ValueError, IndexError) as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="month must be in YYYY-MM format."
        ) from exc
    return start, end


@router.get("/qc-summary", response_model=QcDashboardSummary)
def get_qc_summary(
    month: str | None = Query(default=None, description="YYYY-MM"),
    release_id: int | None = Query(default=None),
    operational_window_id: int | None = Query(default=None),
    release_window_id: int | None = Query(default=None),
    cluster: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> QcDashboardSummary:
    month_start = month_end = None
    if month is not None:
        month_start, month_end = _parse_month(month)

    # TestCases in scope for the current filter combination.
    tc_stmt = select(TestCase).join(Release, TestCase.release_id == Release.id)
    if release_id is not None:
        tc_stmt = tc_stmt.where(TestCase.release_id == release_id)
    if operational_window_id is not None:
        tc_stmt = tc_stmt.where(TestCase.operational_window_id == operational_window_id)
    if release_window_id is not None:
        tc_stmt = tc_stmt.where(TestCase.release_window_id == release_window_id)
    if cluster is not None:
        tc_stmt = tc_stmt.where(Release.cluster == cluster)
    if month_start is not None:
        tc_stmt = tc_stmt.where(
            TestCase.created_at >= month_start,
            TestCase.created_at < month_end + timedelta(days=1),
        )
    test_cases = list(db.execute(tc_stmt).scalars().all())

    planned = len(test_cases)
    executed = sum(1 for tc in test_cases if tc.status != TestCaseStatus.UNEXECUTED)
    status_counts = Counter(tc.status.value for tc in test_cases)
    # percent_avance and percent_cobertura share a formula today -- see QcDashboardSummary docstring.
    percent_avance = round((executed / planned) * 100, 1) if planned else 0.0
    percent_cobertura = percent_avance

    test_case_ids = [tc.id for tc in test_cases]
    defects_found = 0
    defects_critical = 0
    if test_case_ids:
        defect_rows = db.execute(
            select(Defect.severity, func.count(Defect.id))
            .where(Defect.test_case_id.in_(test_case_ids))
            .group_by(Defect.severity)
        ).all()
        for severity, count in defect_rows:
            defects_found += count
            if severity == TestCasePriority.CRITICAL:
                defects_critical += count

    releases_open_stmt = select(func.count(Release.id)).where(
        Release.status.in_([ReleaseStatus.DRAFT, ReleaseStatus.IN_PROGRESS])
    )
    if cluster is not None:
        releases_open_stmt = releases_open_stmt.where(Release.cluster == cluster)
    if release_id is not None:
        releases_open_stmt = releases_open_stmt.where(Release.id == release_id)
    releases_open = db.execute(releases_open_stmt).scalar_one()

    ow_stmt = select(OperationalWindow)
    if cluster is not None:
        ow_stmt = ow_stmt.where(OperationalWindow.cluster == cluster)
    if operational_window_id is not None:
        ow_stmt = ow_stmt.where(OperationalWindow.id == operational_window_id)
    if month_start is not None:
        ow_stmt = ow_stmt.where(
            OperationalWindow.start_date <= month_end, OperationalWindow.end_date >= month_start
        )
    operational_windows = list(db.execute(ow_stmt).scalars().all())

    rw_stmt = select(ReleaseWindow)
    if release_id is not None:
        rw_stmt = rw_stmt.where(ReleaseWindow.release_id == release_id)
    if release_window_id is not None:
        rw_stmt = rw_stmt.where(ReleaseWindow.id == release_window_id)
    if month_start is not None:
        rw_stmt = rw_stmt.where(
            ReleaseWindow.start_date <= month_end, ReleaseWindow.end_date >= month_start
        )
    release_windows = list(db.execute(rw_stmt).scalars().all())

    at_risk: list[AtRiskItem] = []
    today = date.today()
    windows_with_kind = [(w, "operational_window") for w in operational_windows] + [
        (w, "release_window") for w in release_windows
    ]
    for window, kind in windows_with_kind:
        if window.status != WindowStatus.ACTIVE:
            continue
        if kind == "operational_window":
            window_test_cases = [tc for tc in test_cases if tc.operational_window_id == window.id]
        else:
            window_test_cases = [tc for tc in test_cases if tc.release_window_id == window.id]

        w_planned = len(window_test_cases)
        w_executed = sum(1 for tc in window_test_cases if tc.status != TestCaseStatus.UNEXECUTED)
        w_blocked = sum(1 for tc in window_test_cases if tc.status == TestCaseStatus.BLOCKED)
        w_fail = sum(1 for tc in window_test_cases if tc.status == TestCaseStatus.FAIL)

        total_days = max((window.end_date - window.start_date).days, 1)
        elapsed_days = min(max((today - window.start_date).days, 0), total_days)
        elapsed_ratio = elapsed_days / total_days
        executed_ratio = (w_executed / w_planned) if w_planned else 0.0

        reasons: list[str] = []
        if w_planned and executed_ratio + _RISK_SCHEDULE_TOLERANCE < elapsed_ratio:
            reasons.append(
                f"Avance ({executed_ratio * 100:.0f}%) por debajo de lo esperado por tiempo "
                f"transcurrido ({elapsed_ratio * 100:.0f}%)."
            )
        if w_blocked > 0:
            reasons.append(f"{w_blocked} Test Case(s) en BLOCKED.")
        if w_executed and (w_fail / w_executed) > _RISK_FAIL_RATIO_THRESHOLD:
            reasons.append(
                f"% FAIL sobre ejecutados supera el {_RISK_FAIL_RATIO_THRESHOLD * 100:.0f}% "
                f"({(w_fail / w_executed) * 100:.0f}%)."
            )
        if reasons:
            at_risk.append(AtRiskItem(type=kind, id=window.id, name=window.name, reasons=reasons))

    # Activity table: one row per open Release, showing its own execution state and risk --
    # independent of the aggregate `test_cases` set above, since each release needs its own
    # planned/executed counts regardless of which release the top filters target.
    active_releases_stmt = select(Release).where(
        Release.status.in_([ReleaseStatus.DRAFT, ReleaseStatus.IN_PROGRESS])
    )
    if cluster is not None:
        active_releases_stmt = active_releases_stmt.where(Release.cluster == cluster)
    if release_id is not None:
        active_releases_stmt = active_releases_stmt.where(Release.id == release_id)
    active_releases = list(db.execute(active_releases_stmt).scalars().all())

    active_items: list[ActivityItem] = []
    for rel in active_releases:
        rel_tc_stmt = select(TestCase).where(TestCase.release_id == rel.id)
        if operational_window_id is not None:
            rel_tc_stmt = rel_tc_stmt.where(TestCase.operational_window_id == operational_window_id)
        if release_window_id is not None:
            rel_tc_stmt = rel_tc_stmt.where(TestCase.release_window_id == release_window_id)
        if month_start is not None:
            rel_tc_stmt = rel_tc_stmt.where(
                TestCase.created_at >= month_start,
                TestCase.created_at < month_end + timedelta(days=1),
            )
        rel_test_cases = list(db.execute(rel_tc_stmt).scalars().all())

        rel_planned = len(rel_test_cases)
        rel_executed = sum(1 for tc in rel_test_cases if tc.status != TestCaseStatus.UNEXECUTED)
        rel_pass = sum(1 for tc in rel_test_cases if tc.status == TestCaseStatus.PASS)
        rel_blocked = sum(1 for tc in rel_test_cases if tc.status == TestCaseStatus.BLOCKED)
        rel_fail = sum(1 for tc in rel_test_cases if tc.status == TestCaseStatus.FAIL)
        rel_unexecuted = rel_planned - rel_executed
        rel_avance = round((rel_executed / rel_planned) * 100, 1) if rel_planned else 0.0

        rel_test_case_ids = [tc.id for tc in rel_test_cases]
        rel_defects_blocker = 0
        if rel_test_case_ids:
            rel_defects_blocker = db.execute(
                select(func.count(Defect.id)).where(
                    Defect.test_case_id.in_(rel_test_case_ids),
                    Defect.severity == TestCasePriority.BLOCKER,
                )
            ).scalar_one()

        active_window = db.execute(
            select(ReleaseWindow)
            .where(ReleaseWindow.release_id == rel.id, ReleaseWindow.status == WindowStatus.ACTIVE)
            .order_by(ReleaseWindow.start_date.desc())
        ).scalars().first()

        reasons: list[str] = []
        fail_ratio = (rel_fail / rel_executed) if rel_executed else 0.0
        if active_window is not None:
            total_days = max((active_window.end_date - active_window.start_date).days, 1)
            elapsed_days = min(max((today - active_window.start_date).days, 0), total_days)
            elapsed_ratio = elapsed_days / total_days
            executed_ratio = (rel_executed / rel_planned) if rel_planned else 0.0
            if rel_planned and executed_ratio + _RISK_SCHEDULE_TOLERANCE < elapsed_ratio:
                reasons.append(
                    f"Avance ({executed_ratio * 100:.0f}%) por debajo de lo esperado por tiempo "
                    f"transcurrido ({elapsed_ratio * 100:.0f}%)."
                )
        if rel_blocked > 0:
            reasons.append(f"{rel_blocked} Test Case(s) en BLOCKED.")
        if rel_executed and fail_ratio > _RISK_FAIL_RATIO_THRESHOLD:
            reasons.append(
                f"% FAIL sobre ejecutados supera el {_RISK_FAIL_RATIO_THRESHOLD * 100:.0f}% "
                f"({fail_ratio * 100:.0f}%)."
            )

        if rel_blocked > 0 or fail_ratio > 0.25:
            risk_level = "HIGH"
        elif reasons:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        active_items.append(
            ActivityItem(
                release_id=rel.id,
                release_name=rel.name,
                release_version=rel.version,
                platform=rel.platform,
                cluster=rel.cluster,
                window_name=active_window.name if active_window else None,
                window_start_date=active_window.start_date if active_window else None,
                window_end_date=active_window.end_date if active_window else None,
                status=rel.status.value,
                planned=rel_planned,
                executed=rel_executed,
                pass_count=rel_pass,
                fail_count=rel_fail,
                blocked_count=rel_blocked,
                unexecuted_count=rel_unexecuted,
                defects_blocker_count=rel_defects_blocker,
                percent_avance=rel_avance,
                percent_cobertura=rel_avance,
                risk_level=risk_level,
                risk_reasons=reasons,
            )
        )

    return QcDashboardSummary(
        windows_total=len(operational_windows) + len(release_windows),
        windows_active=sum(1 for w in operational_windows if w.status == WindowStatus.ACTIVE)
        + sum(1 for w in release_windows if w.status == WindowStatus.ACTIVE),
        operational_windows_total=len(operational_windows),
        operational_windows_active=sum(
            1 for w in operational_windows if w.status == WindowStatus.ACTIVE
        ),
        release_windows_total=len(release_windows),
        release_windows_active=sum(1 for w in release_windows if w.status == WindowStatus.ACTIVE),
        releases_open=releases_open,
        test_cases_planned=planned,
        test_cases_executed=executed,
        percent_avance=percent_avance,
        percent_cobertura=percent_cobertura,
        pass_count=status_counts.get("PASS", 0),
        fail_count=status_counts.get("FAIL", 0),
        blocked_count=status_counts.get("BLOCKED", 0),
        unexecuted_count=status_counts.get("UNEXECUTED", 0),
        defects_found=defects_found,
        defects_critical=defects_critical,
        at_risk=at_risk,
        active_items=active_items,
    )
