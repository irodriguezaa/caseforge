"""Domain ORM models. Imported eagerly so Base.metadata is complete for Alembic and create_all."""

from app.models.defect import Defect, DefectStatus
from app.models.be_release import BeRelease
from app.models.deliverable import Deliverable
from app.models.epc import Epc, QcSuggestion
from app.models.operativa_release import OperativaRelease
from app.models.qc_ticket import QcTicket, QcTicketPriority, QcTicketSource, QcTicketView
from app.models.release import Release, ReleaseStatus, ReleaseType
from app.models.release_analysis import ReleaseAnalysis
from app.models.test_case import TestCase, TestCasePriority, TestCaseStatus, TestCaseType
from app.models.test_case_revalidation import TestCaseRevalidation
from app.models.test_case_publication import TestCasePublication
from app.models.test_step import TestStep
from app.models.window import OperationalWindow, ReleaseWindow, WindowStatus

__all__ = [
    "Defect",
    "DefectStatus",
    "BeRelease",
    "Deliverable",
    "Epc",
    "QcSuggestion",
    "OperativaRelease",
    "QcTicket",
    "QcTicketPriority",
    "QcTicketSource",
    "QcTicketView",
    "Release",
    "ReleaseStatus",
    "ReleaseType",
    "ReleaseAnalysis",
    "TestCase",
    "TestCasePriority",
    "TestCaseStatus",
    "TestCaseType",
    "TestCaseRevalidation",
    "TestCasePublication",
    "TestStep",
    "OperationalWindow",
    "ReleaseWindow",
    "WindowStatus",
]
