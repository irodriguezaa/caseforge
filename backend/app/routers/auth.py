"""Login / logout / current user. Users live in QC_USERS, not in the database."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    authenticate,
    cookie_secure,
    session_secret,
    sign_session,
)
from app.auth import AuthUser
from app.db import get_db
from app.deps.auth import get_current_user
from app.models.login_event import LoginEvent
from app.schemas.auth import AuthUserRead, LoginRequest

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _session_cookie_kwargs() -> dict[str, object]:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": cookie_secure(),
        "max_age": SESSION_MAX_AGE_SECONDS,
        "path": "/",
    }


@router.post("/login", response_model=AuthUserRead)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> JSONResponse:
    if not session_secret():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticación no configurada (QC_SESSION_SECRET).",
        )
    user = authenticate(payload.email, payload.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Usuario o contraseña incorrectos.")
    try:
        db.add(LoginEvent(email=user.email, role=user.role.value))
        db.commit()
    except Exception:
        db.rollback()
    body = AuthUserRead(email=user.email, role=user.role)
    response = JSONResponse(body.model_dump())
    response.set_cookie(COOKIE_NAME, sign_session(user), **_session_cookie_kwargs())
    return response


@router.post("/logout")
def logout(_user: AuthUser = Depends(get_current_user)) -> JSONResponse:
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


@router.get("/me", response_model=AuthUserRead)
def me(user: AuthUser = Depends(get_current_user)) -> AuthUserRead:
    return AuthUserRead(email=user.email, role=user.role)
