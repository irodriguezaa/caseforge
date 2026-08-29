"""Domain ORM models. Imported eagerly so Base.metadata is complete for Alembic and create_all."""

from app.models.defect import Defect, DefectStatus
from app.models.qc_ticket import QcTicket, QcTicketPriority, QcTicketSource, QcTicketView
from app.models.release import Release, ReleaseStatus
from app.models.release_analysis import ReleaseAnalysis
from app.models.test_case import TestCase, TestCasePriority, TestCaseStatus, TestCaseType
from app.models.test_step import TestStep
from app.models.window import OperationalWindow, ReleaseWindow, WindowStatus

__all__ = [
    "Defect",
    "DefectStatus",
    "QcTicket",
    "QcTicketPriority",
    "QcTicketSource",
    "QcTicketView",
    "Release",
    "ReleaseStatus",
    "ReleaseAnalysis",
    "TestCase",
    "TestCasePriority",
    "TestCaseStatus",
    "TestCaseType",
    "TestStep",
    "OperationalWindow",
    "ReleaseWindow",
    "WindowStatus",
]
