import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import ISSUER_MODE_DERIVED, ISSUER_MODE_EXPLICIT, get_settings
from app.cors_policy import build_cors_kwargs
from app.deployment_validation import sanitize_message
from app.logging_config import AUTH_LOGGER_NAME, configure_auth_logging
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


def log_auth_contract(settings) -> None:
    """Emit one non-secret human-auth configuration line per worker startup.

    Reports only *presence* and *derivation mode*. It deliberately never reports
    the Client ID value, the issuer URL, the JWKS URL, a hostname, the accepted
    issuer list, or any path containing a Client ID — a hosted operator needs to
    know whether the verifier is configured and whether the issuer/JWKS were
    derived or overridden, not what they are.

    ``issuer_mode=derived_standard_set`` means the closed two-entry set of
    documented WorkOS API-root spellings is in effect; ``explicit`` means exactly
    one configured ``WORKOS_ISSUER`` is accepted.

    Readiness never depends on this: it is a log line only, and any failure to
    emit it is swallowed.
    """
    logger = logging.getLogger(AUTH_LOGGER_NAME)
    try:
        logger.info(
            "human auth verifier configured: client_id_present=%s "
            "issuer_mode=%s jwks_mode=%s environment=%s",
            "true" if settings.workos_client_id else "false",
            ISSUER_MODE_EXPLICIT if settings.workos_issuer else ISSUER_MODE_DERIVED,
            "explicit" if settings.workos_jwks_url else "derived",
            (settings.helios_environment or "local").strip().lower(),
        )
    except Exception:  # pragma: no cover - diagnostics must never block startup
        pass


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
    # Emitted only in staging/production-like (or unknown) environments, and only
    # after the fail-closed gate above, so a contract failure still aborts first.
    if is_staging_like_or_unknown:
        log_auth_contract(settings)
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

    # Make human-auth rejection diagnostics reach the hosted stderr stream.
    # Uvicorn configures only its own loggers, leaving the root logger at WARNING
    # with no handlers, so these records were previously discarded at the call
    # site. Idempotent, narrowly scoped, and never enables DEBUG.
    configure_auth_logging()

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
