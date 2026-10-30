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
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    llm_provider: str = (os.getenv("LLM_PROVIDER") or "").strip().lower()
    llm_base_url: str = (os.getenv("LLM_BASE_URL") or "").strip()
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "60") or 60)
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "3") or 3)
    llm_temperature: float | None = (
        float(os.getenv("LLM_TEMPERATURE", "0.2")) if os.getenv("LLM_TEMPERATURE", "0.2") else None
    )
    llm_max_concurrency: int = int(os.getenv("LLM_MAX_CONCURRENCY", "2") or 2)
    rn_storage_dir: str = os.getenv("RN_STORAGE_DIR", "/tmp/caseforge_release_notes")
    # Homologated QC effort indicator (all Release types). Calibrate with real effort later.
    qc_cases_per_day: float = float(os.getenv("QC_CASES_PER_DAY", "46"))
    qc_release_effort_factor: float = float(os.getenv("QC_RELEASE_EFFORT_FACTOR", "3.0"))
    qc_hours_per_day: float = float(os.getenv("QC_HOURS_PER_DAY", "6"))
    case_composition_mode: str = os.getenv("CASE_COMPOSITION_MODE", "scenario")
    # QcPulse: "legacy" (default) | "v2" | "v2b". Solo afecta la generación de casos.
    qc_engine: str = (os.getenv("QC_ENGINE", "legacy") or "legacy").strip().lower()
    qc_v2_model_a: str = (
        os.getenv("OPENAI_QC_MODEL_A")
        or os.getenv("OPENAI_QC_MODEL")
        or os.getenv("LLM_MODEL")
        or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    )
    qc_v2_model_b: str = (
        os.getenv("OPENAI_QC_MODEL_B")
        or os.getenv("OPENAI_QC_MODEL")
        or os.getenv("LLM_MODEL")
        or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    )
    qc_v2_temperature: float | None = (
        float(os.getenv("OPENAI_QC_TEMPERATURE", "0.25")) if os.getenv("OPENAI_QC_TEMPERATURE", "0.25") else None
    )
    qc_v2_reasoning_a: str = (
        os.getenv("OPENAI_QC_REASONING_EFFORT_A") or os.getenv("OPENAI_QC_REASONING_EFFORT") or ""
    ).strip()
    qc_v2_reasoning_b: str = (
        os.getenv("OPENAI_QC_REASONING_EFFORT_B") or os.getenv("OPENAI_QC_REASONING_EFFORT") or ""
    ).strip()
    qc_v2_concurrency: int = int(os.getenv("QC_V2_CONCURRENCY", "5"))
    qc_v2_timeout: float = float(os.getenv("QC_V2_TIMEOUT", "240"))
    # Sprint Testing pack: emails that see the extra export; SWF ids (hitss, tata, nubiral, neoris).
    sprint_pack_emails: str = os.getenv("SPRINT_PACK_EMAILS", "")
    sprint_pack_swfs: str = os.getenv("SPRINT_PACK_SWFS", "hitss,neoris")
    llm_scenario_concurrency: int = int(os.getenv("LLM_SCENARIO_CONCURRENCY", "8"))
    llm_scenario_timeout: float = float(os.getenv("LLM_SCENARIO_TIMEOUT", "45"))
    # Outlook / Microsoft Graph (Calendario QC). MSAL login is not wired yet.
    ms_client_id: str = os.getenv("MS_CLIENT_ID", "")
    ms_client_secret: str = os.getenv("MS_CLIENT_SECRET", "")
    ms_tenant_id: str = os.getenv("MS_TENANT_ID", "")
    ms_graph_access_token: str = os.getenv("MS_GRAPH_ACCESS_TOKEN", "")
    ms_graph_mailbox: str = os.getenv("MS_GRAPH_MAILBOX", "")
    ms_graph_timezone: str = os.getenv("MS_GRAPH_TIMEZONE", "America/Mexico_City")
    # Method B: published Outlook ICS URL or uploaded .ics file.
    ms_calendar_ics_url: str = os.getenv("MS_CALENDAR_ICS_URL", "")
    ms_calendar_ics_path: str = os.getenv("MS_CALENDAR_ICS_PATH", "")
    ms_calendar_ics_qc_only: bool = os.getenv("MS_CALENDAR_ICS_QC_ONLY", "").lower() in {
        "1",
        "true",
        "yes",
    }


settings = Settings()
