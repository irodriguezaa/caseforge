"""SQLAlchemy engine, session factory, and declarative base for CaseForge domain models.

This module is additive to Sprint 1: the existing `app/database.py` module (used by the
`/health/db` endpoint) is untouched and keeps using `psycopg` directly. This module is used
only by the new Sprint 2 domain routers (releases, test cases, test steps, dashboard).
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def build_database_url() -> str:
    """Build the SQLAlchemy connection URL from the same settings used by health checks."""
    return (
        f"postgresql+psycopg://{settings.database_user}:{settings.database_password}"
        f"@{settings.database_host}:{settings.database_port}/{settings.database_name}"
    )


engine = create_engine(build_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Declarative base for all CaseForge ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a request-scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
