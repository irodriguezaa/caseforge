from unittest.mock import Mock

from fastapi.testclient import TestClient
from psycopg import OperationalError

from app.main import app
from app.routers import health


client = TestClient(app)


def test_health_returns_backend_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "backend"}


def test_database_health_returns_consistent_error_when_database_is_unavailable(monkeypatch) -> None:
    database_check = Mock(side_effect=OperationalError("connection refused"))
    monkeypatch.setattr(health, "check_database_connection", database_check)

    response = client.get("/health/db")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "service": "database",
        "connection": "unavailable",
        "message": "Database connection failed",
    }
