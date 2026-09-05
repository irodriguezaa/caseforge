"""Shared pytest fixtures for Sprint 2 domain tests.

Uses an in-memory SQLite database (with foreign keys enforced) instead of PostgreSQL so these
tests run without Docker. The Sprint 1 health tests are untouched and keep mocking the
psycopg-based check directly, independent of this fixture.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  ensure all models are registered on Base.metadata
from app.db import Base, get_db
from app.main import app

TEST_QC_USERS = (
    "jefe@test.com:jefe:jefe-pass,"
    "lider@test.com:lider:lider-pass,"
    "tester@test.com:tester:tester-pass,"
    "consulta@test.com:consulta:consulta-pass"
)
TEST_SESSION_SECRET = "test-qc-session-secret"


@pytest.fixture(autouse=True)
def qc_auth_env(monkeypatch):
    monkeypatch.setenv("QC_USERS", TEST_QC_USERS)
    monkeypatch.setenv("QC_SESSION_SECRET", TEST_SESSION_SECRET)


def login_as(client: TestClient, email: str, password: str) -> None:
    client.cookies.clear()
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    testing_session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        login_as(test_client, "jefe@test.com", "jefe-pass")
        yield test_client
    app.dependency_overrides.clear()
