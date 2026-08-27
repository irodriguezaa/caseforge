"""Health-check endpoints."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from psycopg import Error as PsycopgError

from app.database import check_database_connection

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health() -> dict[str, str]:
    """Report whether the FastAPI application is running."""
    return {"status": "ok", "service": "backend"}


@router.get("/db")
def database_health() -> JSONResponse:
    """Report whether PostgreSQL can be reached by the backend."""
    try:
        check_database_connection()
    except (PsycopgError, OSError, ValueError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "error",
                "service": "database",
                "connection": "unavailable",
                "message": "Database connection failed",
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ok", "service": "database", "connection": "connected"},
    )
