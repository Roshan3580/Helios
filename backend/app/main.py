from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.cors_policy import build_cors_kwargs
from app.deployment_validation import sanitize_message
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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    issues = settings.deployment_issues()
    if issues and settings.helios_environment in {"staging", "production"}:
        details = "; ".join(f"{i.code}: {sanitize_message(i.message)}" for i in issues)
        raise RuntimeError(f"Helios deployment contract failed: {details}")
    yield


settings = get_settings()

app = FastAPI(
    title="Helios API",
    description="AI systems observability backend",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, **build_cors_kwargs(settings))

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
