"""CaseForge API application."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.auth import COOKIE_NAME, Role, read_session
from app.routers.auth import router as auth_router
from app.routers.dashboard import router as dashboard_router
from app.routers.defects import router as defects_router
from app.routers.deliverables import router as deliverables_router
from app.routers.health import router as health_router
from app.routers.imports import router as imports_router
from app.routers.operational_windows import router as operational_windows_router
from app.routers.be_release import router as be_release_router
from app.routers.calendar import router as calendar_router
from app.routers.operativa import router as operativa_router
from app.routers.qc_tickets import router as qc_tickets_router
from app.routers.release_windows import router as release_windows_router
from app.routers.releases import router as releases_router
from app.routers.test_case_revalidations import router as test_case_revalidations_router
from app.routers.test_cases import router as test_cases_router
from app.routers.test_steps import router as test_steps_router

app = FastAPI(title="CaseForge API", version="0.3.0")

_PUBLIC_EXACT = {"/api/v1/auth/login", "/docs", "/openapi.json", "/redoc"}
_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
_CONSULTA_ALLOWED_PREFIXES = (
    "/api/v1/auth",
    "/api/v1/dashboard",
    "/api/v1/calendar",
    "/api/v1/qc-tickets",
)


def _is_public(path: str) -> bool:
    if path in _PUBLIC_EXACT:
        return True
    return path == "/health" or path.startswith("/health/")


@app.middleware("http")
async def session_middleware(request: Request, call_next) -> Response:
    path = request.url.path
    if _is_public(path):
        return await call_next(request)

    if not path.startswith("/api/"):
        return await call_next(request)

    user = read_session(request.cookies.get(COOKIE_NAME))
    if user is None:
        return JSONResponse({"detail": "No autenticado."}, status_code=401)

    request.state.user = user
    if user.role == Role.CONSULTA:
        allowed = any(
            path == prefix or path.startswith(f"{prefix}/") for prefix in _CONSULTA_ALLOWED_PREFIXES
        )
        if not allowed:
            return JSONResponse({"detail": "No tienes permiso para esta acción."}, status_code=403)
        if request.method in _MUTATING and path != "/api/v1/auth/logout":
            return JSONResponse({"detail": "No tienes permiso para esta acción."}, status_code=403)

    return await call_next(request)

# Sprint 1 (unchanged): GET /health, GET /health/db
app.include_router(health_router)
app.include_router(auth_router)

# Sprint 2: Releases + Test Cases, versioned under /api/v1
app.include_router(releases_router)
app.include_router(test_cases_router)
app.include_router(test_steps_router)
app.include_router(imports_router)

# Sprint 2 extension: Operational Windows, Release Windows, Defects, QC Dashboard
app.include_router(operational_windows_router)
app.include_router(operativa_router)
app.include_router(be_release_router)
app.include_router(release_windows_router)
app.include_router(defects_router)
app.include_router(qc_tickets_router)
app.include_router(dashboard_router)
app.include_router(calendar_router)

# Deliverable / Release lineage / Revalidations (Alternative C)
app.include_router(deliverables_router)
app.include_router(test_case_revalidations_router)
