from pydantic import BaseModel

from app.schemas.release import ActivityType, EnvironmentName


class JiraSprintOption(BaseModel):
    id: int
    name: str
    state: str
    label: str


class JiraEpicCreate(BaseModel):
    activity_type: ActivityType | None = None
    environment: EnvironmentName | None = None
    sprint_id: int | None = None


class JiraEpicResult(BaseModel):
    already_existed: bool
    key: str
    summary: str
    activity_type: str
    environment: str
    task_key: str
    task_summary: str
    task_already_existed: bool
    subtask_count: int = 0
    subtasks_already_existed: int = 0
    sprint_id: int | None = None
    sprint_label: str = ""
