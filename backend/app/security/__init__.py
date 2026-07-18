"""Project-scoped API-key security for canonical v2 telemetry."""

from app.security.api_keys import (
    KEY_TOKEN_PREFIX,
    SCOPE_TRACES_INGEST,
    SCOPE_TRACES_READ,
    VALID_SCOPES,
    AuthContext,
    AuthError,
    GeneratedKey,
    generate_api_key,
    hash_token,
    parse_lookup_prefix,
    validate_scopes,
)

__all__ = [
    "KEY_TOKEN_PREFIX",
    "SCOPE_TRACES_INGEST",
    "SCOPE_TRACES_READ",
    "VALID_SCOPES",
    "AuthContext",
    "AuthError",
    "GeneratedKey",
    "generate_api_key",
    "hash_token",
    "parse_lookup_prefix",
    "validate_scopes",
]
