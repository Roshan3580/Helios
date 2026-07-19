from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import (
    dashboard,
    datasets,
    demo,
    evaluations,
    health,
    otlp,
    projects,
    prompts,
    rag,
    traces,
    traces_v2,
    user_v2,
)
from app.routers.e2e import include_e2e_router

settings = get_settings()

app = FastAPI(
    title="Helios API",
    description="AI systems observability backend",
    version=settings.app_version,
)

_cors: dict = {
    "allow_origins": settings.cors_origin_list,
    "allow_credentials": True,
    "allow_methods": ["*"],
    "allow_headers": ["*"],
    # Ephemeral local/CI frontend ports (Vite) on loopback.
    "allow_origin_regex": r"https?://(127\.0\.0\.1|localhost)(:\d+)?",
}

app.add_middleware(CORSMiddleware, **_cors)

app.include_router(health.router)
app.include_router(projects.router, prefix="/v1")
app.include_router(traces.router, prefix="/v1")
app.include_router(dashboard.router, prefix="/v1")
app.include_router(rag.router, prefix="/v1")
app.include_router(evaluations.router, prefix="/v1")
app.include_router(prompts.router, prefix="/v1")
app.include_router(datasets.router, prefix="/v1")
app.include_router(demo.router, prefix="/v1")
app.include_router(otlp.router, prefix="/v1")  # canonical v2 OTLP ingestion
app.include_router(traces_v2.router, prefix="/v2")  # canonical v2 reads
app.include_router(user_v2.router, prefix="/v2")  # human (WorkOS JWT) routes
include_e2e_router(app)  # no-op unless HELIOS_E2E_TEST_MODE=true
