"""WorkOS AuthKit access-token verification for human (browser) requests.

Completely separate from project API-key auth (app/security/api_keys.py):
humans present a WorkOS JWT, machines present a Helios project key. Neither
path is reused or weakened by the other.

Verification: RS256 signature against the WorkOS JWKS (cached, bounded TTL),
issuer, expiration, and required claims (sub, sid; org_id for org-scoped
routes). Claims are never trusted without signature verification. JWKS
fetching fails closed, uses explicit timeouts, and retries exactly once when
an unknown `kid` appears (key rotation). JWTs and Authorization headers are
never logged.

JIT identity: a verified user is upserted/touched locally (isolated session,
same pattern as api-key last_used_at). Organizations are NOT auto-created:
the org must already be linked via `python -m app.cli.organizations`, so
arbitrary external org IDs can never implicitly own projects. Unknown org →
stable 403 onboarding response.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
import jwt as pyjwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models_identity import Organization, User
from app.security.api_keys import AuthError

logger = logging.getLogger("helios.auth.human")

ALLOWED_ALGORITHMS = ("RS256",)


@dataclass(frozen=True)
class HumanAuthContext:
    workos_user_id: str
    workos_session_id: str
    workos_org_id: str | None
    role: str | None
    permissions: tuple[str, ...]
    expires_at: datetime
    local_user_id: str
    local_org_id: str | None = None
    organization_slug: str | None = None
    organization_name: str | None = None

    def __repr__(self) -> str:  # never include tokens
        return (
            f"HumanAuthContext(sub={self.workos_user_id!r}, "
            f"org={self.workos_org_id!r}, role={self.role!r})"
        )


class JWKSClient:
    """Bounded-TTL JWKS cache with retry-once-on-unknown-kid and fail-closed."""

    def __init__(
        self,
        url: str,
        *,
        cache_ttl: int = 3600,
        timeout: float = 5.0,
        fetcher=None,
    ) -> None:
        self._url = url
        self._cache_ttl = cache_ttl
        self._timeout = timeout
        self._fetcher = fetcher or self._http_fetch
        self._keys: dict[str, dict] = {}
        self._fetched_at: float = 0.0
        self._lock = threading.Lock()

    def _http_fetch(self) -> dict:
        response = httpx.get(self._url, timeout=self._timeout)
        response.raise_for_status()
        return response.json()

    def _refresh(self) -> None:
        try:
            document = self._fetcher()
            keys = {
                key["kid"]: key
                for key in document.get("keys", [])
                if key.get("kid") and key.get("kty")
            }
        except Exception:
            # Fail closed; never surface JWKS/HTTP details to callers.
            logger.warning("jwks refresh failed", exc_info=False)
            raise AuthError("jwks_unavailable", status_code=401)
        self._keys = keys
        self._fetched_at = time.monotonic()

    def get_signing_key(self, kid: str) -> dict:
        with self._lock:
            expired = (time.monotonic() - self._fetched_at) > self._cache_ttl
            if not self._keys or expired:
                self._refresh()
            if kid not in self._keys:
                # Unknown kid: refresh exactly once (key rotation), then decide.
                self._refresh()
            key = self._keys.get(kid)
            if key is None:
                raise AuthError("unknown_signing_key", status_code=401)
            return key


class WorkOSTokenVerifier:
    def __init__(self, *, issuer: str, jwks_client: JWKSClient) -> None:
        self._issuer = issuer
        self._jwks = jwks_client

    def verify(self, token: str) -> dict:
        """Verify signature + registered claims; return the claim set."""
        try:
            header = pyjwt.get_unverified_header(token)
        except pyjwt.InvalidTokenError:
            raise AuthError("malformed_jwt", status_code=401)

        algorithm = header.get("alg")
        if algorithm not in ALLOWED_ALGORITHMS:
            raise AuthError("unsupported_algorithm", status_code=401)
        kid = header.get("kid")
        if not kid:
            raise AuthError("missing_kid", status_code=401)

        jwk = self._jwks.get_signing_key(kid)
        try:
            public_key = pyjwt.PyJWK(jwk).key
            claims = pyjwt.decode(
                token,
                key=public_key,
                algorithms=list(ALLOWED_ALGORITHMS),
                issuer=self._issuer,
                options={
                    "require": ["exp", "iat", "iss", "sub", "sid"],
                    "verify_aud": False,  # WorkOS access tokens carry no aud claim
                },
            )
        except pyjwt.ExpiredSignatureError:
            raise AuthError("expired_jwt", status_code=401)
        except pyjwt.InvalidIssuerError:
            raise AuthError("wrong_issuer", status_code=401)
        except pyjwt.MissingRequiredClaimError:
            raise AuthError("missing_claims", status_code=401)
        except pyjwt.InvalidTokenError:
            raise AuthError("invalid_signature", status_code=401)

        if not claims.get("sub"):
            raise AuthError("missing_sub", status_code=401)
        if not claims.get("sid"):
            raise AuthError("missing_sid", status_code=401)
        return claims


_verifier: WorkOSTokenVerifier | None = None
_verifier_lock = threading.Lock()


def get_verifier() -> WorkOSTokenVerifier:
    """Module-level verifier built from settings (tests inject their own)."""
    global _verifier
    with _verifier_lock:
        if _verifier is None:
            settings = get_settings()
            issuer = settings.workos_issuer_resolved
            jwks_url = settings.workos_jwks_url_resolved
            if not issuer or not jwks_url:
                raise AuthError("human_auth_not_configured", status_code=401)
            _verifier = WorkOSTokenVerifier(
                issuer=issuer,
                jwks_client=JWKSClient(
                    jwks_url,
                    cache_ttl=settings.workos_jwks_cache_ttl,
                    timeout=settings.workos_jwks_timeout,
                ),
            )
        return _verifier


def set_verifier_for_tests(verifier: WorkOSTokenVerifier | None) -> None:
    global _verifier
    with _verifier_lock:
        _verifier = verifier


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _touch_user(claims: dict) -> str:
    """JIT upsert of the local user in an isolated committed session.

    Returns the local user UUID (as str). Independent of the request session so
    read-only routes still record identity and rollbacks never lose it.
    """
    now = _utc_now()
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.workos_user_id == claims["sub"]))
        if user is None:
            user = User(
                workos_user_id=claims["sub"],
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(user)
        else:
            user.last_seen_at = now
        session.commit()
        return str(user.id)


def authenticate_human(
    db: Session,
    token: str | None,
    *,
    require_org: bool = True,
) -> HumanAuthContext:
    """Verify a WorkOS bearer token and resolve local identity.

    Raises AuthError(401) for credential problems, AuthError(403) when the
    token's organization is not linked locally (or missing when required).
    """
    if not token:
        logger.info("human auth reject: missing bearer token")
        raise AuthError("missing_token", status_code=401)

    claims = get_verifier().verify(token)

    org_id = claims.get("org_id") or None
    if require_org and not org_id:
        logger.info("human auth reject: token has no org_id (sub present)")
        raise AuthError("missing_org", status_code=403)

    local_user_id = _touch_user(claims)

    local_org: Organization | None = None
    if org_id:
        local_org = db.scalar(
            select(Organization).where(Organization.workos_org_id == org_id)
        )
        if require_org and local_org is None:
            # Deliberate: organizations are linked only via the admin CLI.
            logger.info("human auth reject: unlinked organization")
            raise AuthError("organization_not_linked", status_code=403)

    permissions = claims.get("permissions") or []
    return HumanAuthContext(
        workos_user_id=claims["sub"],
        workos_session_id=claims["sid"],
        workos_org_id=org_id,
        role=claims.get("role"),
        permissions=tuple(permissions) if isinstance(permissions, (list, tuple)) else (),
        expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
        local_user_id=local_user_id,
        local_org_id=str(local_org.id) if local_org else None,
        organization_slug=local_org.slug if local_org else None,
        organization_name=local_org.name if local_org else None,
    )
