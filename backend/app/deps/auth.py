"""FastAPI dependencies for session users and role checks."""

from fastapi import Depends, HTTPException, Request, status

from app.auth import AuthUser, Role, read_session, COOKIE_NAME

FORBIDDEN = "No tienes permiso para esta acción."
UNAUTHENTICATED = "No autenticado."


def get_current_user(request: Request) -> AuthUser:
    user = getattr(request.state, "user", None)
    if user is not None:
        return user
    user = read_session(request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=UNAUTHENTICATED)
    return user


def require_roles(*roles: Role):
    allowed = set(roles)

    def _check(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=FORBIDDEN)
        return user

    return _check


require_dashboard = require_roles(Role.JEFE, Role.LIDER, Role.CONSULTA)
require_jefe = require_roles(Role.JEFE)
require_status_change = require_roles(Role.JEFE, Role.LIDER)
