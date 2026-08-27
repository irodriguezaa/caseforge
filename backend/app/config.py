"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_host: str = os.getenv("DATABASE_HOST", "postgres")
    database_port: int = int(os.getenv("DATABASE_PORT", "5432"))
    database_name: str = os.getenv("DATABASE_NAME", "caseforge")
    database_user: str = os.getenv("DATABASE_USER", "caseforge_user")
    database_password: str = os.getenv("DATABASE_PASSWORD", "")


settings = Settings()
