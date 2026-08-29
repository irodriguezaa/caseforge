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
    # Optional: only needed for the Jira sync feature. Never required for the app to start,
    # unlike DATABASE_* -- most environments won't set these yet.
    jira_base_url: str = os.getenv("JIRA_BASE_URL", "")
    jira_email: str = os.getenv("JIRA_EMAIL", "")
    jira_api_token: str = os.getenv("JIRA_API_TOKEN", "")


settings = Settings()
