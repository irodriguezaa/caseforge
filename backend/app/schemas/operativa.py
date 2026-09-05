from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class EpcRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operativa_release_id: int
    release_id: int | None = None
    brf_key: str
    epc_key: str | None
    titulo: str
    alcance: str | None
    nota_rte: str | None
    estado_jira: str | None
    qc_suggestion: str
    include_in_qc: bool
    alcance_funcional: str | None
    dispositivos_aplicables: list[str] | None


class EpcUpdate(BaseModel):
    """Fields QC can edit on an EPC. include_in_qc is never locked: qc_suggestion (set once
    at analysis time) is read-only, but the user's actual decision can change at any point.
    alcance_funcional and dispositivos_aplicables belong to Paso 3 (Configuración).
    include_in_qc belongs to Paso 4 (Análisis)."""

    include_in_qc: bool | None = None
    alcance_funcional: str | None = None
    dispositivos_aplicables: list[str] | None = None


class OperativaReleaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    entregable: str | None
    cluster: str | None
    description: str | None
    pdf_filename: str
    pdf_file_path: str | None = None
    start_date: date | None
    end_date: date | None
    jira_filter_url: str | None
    jira_filter_manual: str | None
    instrucciones_adicionales: str | None
    epcs: list[EpcRead] = []
    qc_release_id: int | None = None
    qc_release_status: str | None = None

    @model_validator(mode="wrap")
    @classmethod
    def attach_qc_release(cls, data: Any, handler: Any) -> Any:
        validated = handler(data)
        if isinstance(data, dict):
            return validated
        qc = getattr(data, "qc_release", None)
        qc_id = qc.id if qc is not None else validated.qc_release_id
        qc_status = None
        if qc is not None:
            qc_status = qc.status.value if hasattr(qc.status, "value") else str(qc.status)
        if qc_id is None:
            for epc in getattr(data, "epcs", None) or []:
                rid = getattr(epc, "release_id", None)
                if rid:
                    qc_id = rid
                    break
        if validated.qc_release_id == qc_id and validated.qc_release_status == qc_status:
            return validated
        return validated.model_copy(update={"qc_release_id": qc_id, "qc_release_status": qc_status})


class OperativaReleaseUpdate(BaseModel):
    """Paso 2 (header) and Paso 3 (configuración) fields. All optional; a PATCH only touches
    what is sent. Empty strings are stored as null (shown as No disponible in the UI)."""

    name: str | None = None
    entregable: str | None = None
    cluster: str | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    jira_filter_url: str | None = None
    jira_filter_manual: str | None = None
    instrucciones_adicionales: str | None = None

    @field_validator(
        "name",
        "entregable",
        "cluster",
        "description",
        "jira_filter_url",
        "jira_filter_manual",
        "instrucciones_adicionales",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            return _blank_to_none(value)
        return value


class OperativaAnalysisResult(BaseModel):
    """Response of POST /analyze-rn -- the persisted OperativaRelease plus its detected EPCs,
    each carrying only a SUGGESTION (qc_suggestion), never a final decision."""

    operativa_release: OperativaReleaseRead
