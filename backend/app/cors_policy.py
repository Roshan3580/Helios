"""CORS configuration builder for exact-origin allowlists."""

from __future__ import annotations

from app.config import Settings
from app.deployment_validation import allow_loopback_cors_regex

# Canonical browser APIs need these; keep the list tight for staging.
ALLOWED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
ALLOWED_HEADERS = [
    "Authorization",
    "Content-Type",
    "Accept",
    "X-Requested-With",
]

LOOPBACK_ORIGIN_REGEX = r"https?://(127\.0\.0\.1|localhost)(:\d+)?"


def build_cors_kwargs(settings: Settings) -> dict:
    """Return kwargs for fastapi.middleware.cors.CORSMiddleware."""
    kwargs: dict = {
        "allow_origins": settings.cors_origin_list,
        "allow_credentials": True,
        "allow_methods": ALLOWED_METHODS,
        "allow_headers": ALLOWED_HEADERS,
    }
    if allow_loopback_cors_regex(settings.helios_environment, settings.helios_e2e_test_mode):
        kwargs["allow_origin_regex"] = LOOPBACK_ORIGIN_REGEX
    return kwargs
