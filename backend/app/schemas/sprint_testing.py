from pydantic import BaseModel, Field


class SprintOption(BaseModel):
    id: str
    label: str
    filter_id: str | None = None
    actionable: bool


class ProgramOption(BaseModel):
    program_key: str
    display_name: str


class SwfOption(BaseModel):
    id: str
    label: str
    programs: list[ProgramOption]


class SprintTestingOptions(BaseModel):
    sprints: list[SprintOption]
    swfs: list[SwfOption]


class SprintTestingSprint(BaseModel):
    id: str
    label: str
    filter_id: str


class ProgramMetrics(BaseModel):
    program_key: str
    display_name: str
    total: int
    todo: dict[str, int] = Field(default_factory=dict)
    development: dict[str, int] = Field(default_factory=dict)
    testing: dict[str, int] = Field(default_factory=dict)
    closed: dict[str, int] = Field(default_factory=dict)
    open: int
    closed_total: int
    unclassified: dict[str, int] = Field(default_factory=dict)
    consistency_ok: bool


class SprintTestingRead(BaseModel):
    sprint: SprintTestingSprint
    swf: str
    filter_issue_count: int
    technical_epic_count: int
    other_issue_count: int
    programs: list[ProgramMetrics]
    consistency_ok: bool
