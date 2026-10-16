from typing import Any
from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class BeRegresivoScope(str, Enum):
    SMOKE_TEST = "Smoke Test"
    PRUEBAS_ACOTADAS = "Pruebas Acotadas"
    REGRESION_COMPLETA = "Regresión completa"
    NA = "N/A"


BE_QC_SCOPE_VALUES = {item.value for item in BeRegresivoScope}

BE_SWF_VALUES = {"BE Hitss", "BE Nubiral", "BE Neoris"}
BE_CLUSTER_TODOS = "Todos"
BE_CLUSTER_INDIVIDUAL = ("Global", "AUP", "CENAM", "Andina", "Dominicana")
BE_CLUSTER_VALUES = {BE_CLUSTER_TODOS, *BE_CLUSTER_INDIVIDUAL}


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def normalize_be_clusters(values: list[str] | None) -> list[str] | None:
    """Todos is exclusive and is not stored alongside individual clusters."""
    if values is None:
        return None
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        item = raw.strip() if isinstance(raw, str) else ""
        if not item or item in seen:
            continue
        if item not in BE_CLUSTER_VALUES:
            raise ValueError(
                "Cluster debe ser Todos, Global, AUP, CENAM, Andina o Dominicana."
            )
        seen.add(item)
        cleaned.append(item)
    if not cleaned:
        return None
    if BE_CLUSTER_TODOS in seen:
        return [BE_CLUSTER_TODOS]
    return [name for name in BE_CLUSTER_INDIVIDUAL if name in seen]


def be_clusters_as_release_label(clusters: list[str] | None) -> str | None:
    normalized = normalize_be_clusters(clusters)
    if not normalized:
        return None
    return ", ".join(normalized)


class BeReleaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    entregable: str | None
    swf: str | None
    clusters: list[str] | None = None
    description: str | None
    pdf_filename: str | None
    regresivo_scope: BeRegresivoScope | None
    affected_component: str | None
    qc_matrix_touched_modules: list[str] | None = None
    start_date: date | None = None
    end_date: date | None = None
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
        if validated.qc_release_id == qc_id and validated.qc_release_status == qc_status:
            return validated
        return validated.model_copy(update={"qc_release_id": qc_id, "qc_release_status": qc_status})


class BeReleaseUpdate(BaseModel):
    name: str | None = None
    entregable: str | None = None
    swf: str | None = None
    clusters: list[str] | None = None
    description: str | None = None
    regresivo_scope: BeRegresivoScope | None = None
    affected_component: str | None = None
    qc_matrix_touched_modules: list[str] | None = None
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("name", "entregable", "swf", "description", "affected_component", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            return _blank_to_none(value)
        return value

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def empty_date_to_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("swf")
    @classmethod
    def swf_must_be_known(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in BE_SWF_VALUES:
            raise ValueError("SWF solicitante debe ser BE Hitss, BE Nubiral o BE Neoris.")
        return value

    @field_validator("clusters")
    @classmethod
    def clusters_must_be_known_and_exclusive(cls, value: list[str] | None) -> list[str] | None:
        return normalize_be_clusters(value)

    @field_validator("regresivo_scope", mode="before")
    @classmethod
    def scope_must_be_known(cls, value: object) -> object:
        if value is None or value == "":
            return None
        if isinstance(value, BeRegresivoScope):
            return value
        text = str(value).strip()
        legacy = {"COMPLETO": "Regresión completa", "SMOKE": "Smoke Test", "ACOTADO": "Pruebas Acotadas"}
        text = legacy.get(text, text)
        if text not in BE_QC_SCOPE_VALUES:
            raise ValueError("Alcance QC debe ser Smoke Test, Pruebas Acotadas, Regresión completa o N/A.")
        return text


class BeAnalysisResult(BaseModel):
    be_release: BeReleaseRead
