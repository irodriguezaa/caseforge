"""Publication of persisted Operativas Test Cases to Jira QCO Test issues."""

from pydantic import BaseModel, Field


class PublicationRecordRead(BaseModel):
    caseforge_id: str
    zephyr_id: str | None = None
    brf: str
    hn: str
    device_channel: str
    name: str
    steps: int
    status: str
    resultado: str
    detail: str = ""


class PublishCasesResponse(BaseModel):
    status: str
    message: str
    release_id: int
    sent: int = 0
    created: int = 0
    errors: int = 0
    duplicates: int = 0
    rejected: int = 0
    caseforge_unmodified: bool = True
    records: list[PublicationRecordRead] = Field(default_factory=list)
