"""Small database connectivity utilities for infrastructure health checks."""

from psycopg import connect
from psycopg.conninfo import make_conninfo

from app.config import settings


def check_database_connection() -> None:
    """Open a short-lived connection and execute a trivial PostgreSQL query."""
    connection_string = make_conninfo(
        host=settings.database_host,
        port=settings.database_port,
        dbname=settings.database_name,
        user=settings.database_user,
        password=settings.database_password,
        connect_timeout=3,
    )
    with connect(connection_string) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
