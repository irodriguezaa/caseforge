from pydantic import BaseModel, Field

from app.auth import Role


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class AuthUserRead(BaseModel):
    email: str
    role: Role
