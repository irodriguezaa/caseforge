from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class BeRegresivoScope(str, Enum):
    COMPLETO = "COMPLETO"
    SMOKE = "SMOKE"
    ACOTADO = "ACOTADO"

_SWF_ALLOWED = {"Neoris", "Tata", "Hitss"}


def _blank_to_none(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class BeReleaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None
    entregable: str | None
    swf: str | None
    description: str | None
    pdf_filename: str | None
    regresivo_scope: BeRegresivoScope | None
    affected_component: str | None


class BeReleaseUpdate(BaseModel):
    name: str | None = None
    entregable: str | None = None
    swf: str | None = None
    description: str | None = None
    regresivo_scope: BeRegresivoScope | None = None
    affected_component: str | None = None

    @field_validator("name", "entregable", "swf", "description", "affected_component", mode="before")
    @classmethod
    def empty_string_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            return _blank_to_none(value)
        return value

    @field_validator("swf")
    @classmethod
    def swf_must_be_known(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in _SWF_ALLOWED:
            raise ValueError("SWF debe ser Neoris, Tata o Hitss.")
        return value


class BeAnalysisResult(BaseModel):
    be_release: BeReleaseRead
