"""API-key primitives: generation, hashing, parsing, and the auth context.

Token format (see docs/ADR_002_PROJECT_API_KEYS.md):

    hel_proj_<lookup>_<secret>

- <lookup>: 16 hex chars (non-secret), the unique DB lookup prefix.
- <secret>: URL-safe base64 of 32 random bytes (>=256 bits of entropy).

Storage keeps only the lookup prefix and sha256(full token). The plaintext
token is returned once at creation and never persisted or logged.

Why SHA-256 and not bcrypt/argon2: API keys are 256-bit cryptographically
random secrets, not human passwords. A password hash's work factor exists to
slow brute force of low-entropy inputs; a 256-bit random token is infeasible
to brute-force regardless, so a fast deterministic digest is the correct and
constant-time-comparable choice.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

KEY_TOKEN_PREFIX = "hel_proj"
_LOOKUP_BYTES = 8  # -> 16 hex chars
_SECRET_BYTES = 32  # 256 bits of entropy

SCOPE_TRACES_INGEST = "traces:ingest"
SCOPE_TRACES_READ = "traces:read"
VALID_SCOPES = frozenset({SCOPE_TRACES_INGEST, SCOPE_TRACES_READ})


class AuthError(Exception):
    """Raised for any authentication/authorization failure.

    `reason` is an internal category for structured logging; it is never
    returned to clients (responses stay generic so key state is not revealed).
    """

    def __init__(self, reason: str, *, status_code: int = 401) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


@dataclass(frozen=True)
class GeneratedKey:
    token: str  # full plaintext, shown once
    key_prefix: str
    key_hash: str


@dataclass(frozen=True)
class AuthContext:
    api_key_id: str
    project_id: str
    project_slug: str
    project_name: str
    scopes: tuple[str, ...] = field(default_factory=tuple)
    environment: str | None = None

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def hash_token(token: str) -> str:
    """Deterministic SHA-256 hex digest of the complete token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_api_key() -> GeneratedKey:
    lookup = secrets.token_hex(_LOOKUP_BYTES)
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    token = f"{KEY_TOKEN_PREFIX}_{lookup}_{secret}"
    return GeneratedKey(token=token, key_prefix=lookup, key_hash=hash_token(token))


def parse_lookup_prefix(token: str) -> str | None:
    """Extract the non-secret lookup prefix from a token, or None if malformed.

    Expected shape: hel_proj_<lookup>_<secret> with a non-empty secret.
    """
    parts = token.split("_")
    # ["hel", "proj", "<lookup>", "<secret...>"] (secret may contain no "_")
    if len(parts) < 4:
        return None
    if parts[0] != "hel" or parts[1] != "proj":
        return None
    lookup = parts[2]
    secret = "_".join(parts[3:])
    if not lookup or not secret:
        return None
    return lookup


def verify_token(token: str, stored_hash: str) -> bool:
    """Constant-time comparison of sha256(token) against the stored digest."""
    return hmac.compare_digest(hash_token(token), stored_hash)


def validate_scopes(scopes: list[str]) -> list[str]:
    """Return a normalized, de-duplicated scope list or raise ValueError."""
    if not scopes:
        raise ValueError("at least one scope is required")
    normalized: list[str] = []
    for scope in scopes:
        cleaned = scope.strip()
        if cleaned not in VALID_SCOPES:
            raise ValueError(
                f"invalid scope '{scope}'; valid scopes: {', '.join(sorted(VALID_SCOPES))}"
            )
        if cleaned not in normalized:
            normalized.append(cleaned)
    return normalized
