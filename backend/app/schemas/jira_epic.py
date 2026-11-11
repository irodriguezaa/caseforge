from pydantic import BaseModel

from app.schemas.release import ActivityType, EnvironmentName


class JiraEpicCreate(BaseModel):
    activity_type: ActivityType | None = None
    environment: EnvironmentName | None = None


class JiraEpicResult(BaseModel):
    already_existed: bool
    key: str
    summary: str
    activity_type: str
    environment: str
