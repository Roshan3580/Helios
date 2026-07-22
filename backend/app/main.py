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


# Unauthenticated legacy/demo routers. The security boundary is not mounting
# them at all outside explicit demo mode — never per-endpoint authentication
# (see deployment_validation.validate_settings, which forbids
# HELIOS_DEMO_MODE=true in staging/production).
_LEGACY_DEMO_ROUTERS = (
    projects.router,
    traces.router,
    dashboard.router,
    rag.router,
    evaluations.router,
    prompts.router,
    datasets.router,
    demo.router,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    from app.deployment_validation import STAGING_LIKE, LOCAL_LIKE

    settings = get_settings()
    issues = settings.deployment_issues()
    # Fail closed: any validation issue in staging/production/unknown environments
    # is fatal. Unknown environments are treated as unsafe (fail closed).
    env = (settings.helios_environment or "local").strip().lower()
    is_staging_like_or_unknown = env not in LOCAL_LIKE
    if issues and is_staging_like_or_unknown:
        details = "; ".join(f"{i.code}: {sanitize_message(i.message)}" for i in issues)
        raise RuntimeError(f"Helios deployment contract failed: {details}")
    yield


def create_app() -> FastAPI:
    """Build a FastAPI app from current settings.

    A factory (rather than mounting routers on a single module-level
    instance) so tests can construct independent apps for different
    HELIOS_DEMO_MODE / HELIOS_ENVIRONMENT combinations without mutating
    global state. Always reads settings via ``get_settings()`` at call time,
    so callers that need different settings must monkeypatch the environment
    and call ``get_settings.cache_clear()`` before invoking this.
    """
    settings = get_settings()

    app = FastAPI(
        title="Helios API",
        description="AI systems observability backend",
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(CORSMiddleware, **build_cors_kwargs(settings))

    app.include_router(health.router)
    app.include_router(otlp.router, prefix="/v1")  # canonical v2 OTLP ingestion
    app.include_router(traces_v2.router, prefix="/v2")  # canonical v2 reads
    app.include_router(user_v2.router, prefix="/v2")  # human (WorkOS JWT) routes
    include_e2e_router(app)  # no-op unless HELIOS_E2E_TEST_MODE=true

    if settings.helios_demo_mode:
        for router in _LEGACY_DEMO_ROUTERS:
            app.include_router(router, prefix="/v1")

    return app


app = create_app()
