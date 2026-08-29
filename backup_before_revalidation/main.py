"""CaseForge API application."""

from fastapi import FastAPI

from app.routers.dashboard import router as dashboard_router
from app.routers.defects import router as defects_router
from app.routers.deliverables import router as deliverables_router
from app.routers.health import router as health_router
from app.routers.imports import router as imports_router
from app.routers.operational_windows import router as operational_windows_router
from app.routers.qc_tickets import router as qc_tickets_router
from app.routers.release_windows import router as release_windows_router
from app.routers.releases import router as releases_router
from app.routers.test_case_revalidations import router as test_case_revalidations_router
from app.routers.test_cases import router as test_cases_router
from app.routers.test_steps import router as test_steps_router

app = FastAPI(title="CaseForge API", version="0.3.0")

# Sprint 1 (unchanged): GET /health, GET /health/db
app.include_router(health_router)

# Sprint 2: Releases + Test Cases, versioned under /api/v1
app.include_router(releases_router)
app.include_router(test_cases_router)
app.include_router(test_steps_router)
app.include_router(imports_router)

# Sprint 2 extension: Operational Windows, Release Windows, Defects, QC Dashboard
app.include_router(operational_windows_router)
app.include_router(release_windows_router)
app.include_router(defects_router)
app.include_router(qc_tickets_router)
app.include_router(dashboard_router)

# Deliverable / Release lineage / Revalidations (Alternative C)
app.include_router(deliverables_router)
app.include_router(test_case_revalidations_router)
