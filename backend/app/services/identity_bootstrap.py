"""Idempotent, concurrency-safe local bootstrap from verified WorkOS claims.

Checkpoint 24 (public beta foundation): a verified WorkOS user, and — when the
verified access token carries a verified active organization — that
organization, are mapped into local Helios records the first time they are
seen. No manual admin CLI step (``python -m app.cli.organizations``) is
required for a normal invited tester anymore.

Security contract
-----------------
- The authoritative WorkOS user ID (``sub``) and organization ID (``org_id``)
  come ONLY from a signature-verified access token. This module is never given
  a client-supplied identifier; a caller must pass values already verified by
  ``WorkOSTokenVerifier``.
- An implausible organization identifier is refused (returns ``None``) so junk
  can never be materialized as a local organization; the caller fails closed to
  onboarding.
- Uniqueness is enforced by the database (``uq_users_workos_user_id``,
  ``uq_organizations_workos_org_id``, ``uq_organizations_slug``). Concurrent
  first requests converge on a single row via integrity-conflict retry; we
  never rely on read-then-write TOCTOU checks alone.
- No WorkOS API key is used or required here. This is a pure local mapping —
  the org must already exist in WorkOS for the verified token to carry its
  ``org_id`` claim.

Isolated sessions
-----------------
Both helpers use their own committed ``SessionLocal`` session, independent of
the request transaction (the same pattern the previous JIT ``_touch_user`` used).
That way a read-only GET still persists the mapping and a request-scoped
rollback never discards it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models_identity import Organization, User

logger = logging.getLogger("helios.identity.bootstrap")

# WorkOS org IDs look like org_<ULID-ish>; reuse the loose shape the admin
# service accepts so an implausible value never becomes a local organization.
_WORKOS_ORG_ID_RE = re.compile(r"^org_[A-Za-z0-9]{5,60}$")
# Bounded slug-collision disambiguation. Collisions are essentially impossible
# because the base slug derives from a globally-unique WorkOS org id, but the
# loop stays bounded and fail-closed regardless.
_MAX_SLUG_ATTEMPTS = 6


@dataclass(frozen=True)
class BootstrappedOrg:
    id: str
    slug: str
    name: str


@dataclass(frozen=True)
class BootstrapResult:
    local_user_id: str
    org: BootstrappedOrg | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _valid_workos_org_id(workos_org_id: str) -> bool:
    return bool(_WORKOS_ORG_ID_RE.match(workos_org_id or ""))


def _derive_org_slug(workos_org_id: str) -> str:
    """Deterministic, unique-by-construction slug for an auto-created org.

    The WorkOS org id is globally unique, so a normalization of it yields a
    unique base slug. Truncated to leave headroom under ``organizations.slug``
    (``String(128)``) for a ``-N`` disambiguating suffix.
    """
    base = re.sub(r"[^a-z0-9]+", "-", workos_org_id.lower()).strip("-")
    return (base or "workspace")[:117]


def _derive_org_name(workos_org_id: str) -> str:
    """Human-facing placeholder name.

    A WorkOS access token carries no human-readable organization name, so we
    derive a stable placeholder from the id suffix. There is intentionally no
    ``name`` uniqueness constraint; renaming is a future enhancement.
    """
    suffix = re.sub(r"[^A-Za-z0-9]+", "", workos_org_id)[-6:].upper() or "NEW"
    return f"Workspace {suffix}"


def bootstrap_user(workos_user_id: str) -> str:
    """Get-or-create the local user for a verified WorkOS subject.

    Returns the local user UUID as a string. Concurrency-safe: a losing INSERT
    hits ``uq_users_workos_user_id``; we roll back, re-read the winning row, and
    touch it, so concurrent first requests produce exactly one identity.
    """
    now = _utc_now()
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.workos_user_id == workos_user_id))
        if user is not None:
            user.last_seen_at = now
            session.commit()
            return str(user.id)
        user = User(workos_user_id=workos_user_id, first_seen_at=now, last_seen_at=now)
        session.add(user)
        try:
            session.commit()
            return str(user.id)
        except IntegrityError:
            session.rollback()
            existing = session.scalar(
                select(User).where(User.workos_user_id == workos_user_id)
            )
            if existing is None:
                raise
            existing.last_seen_at = now
            session.commit()
            return str(existing.id)


def bootstrap_organization(workos_org_id: str) -> BootstrappedOrg | None:
    """Idempotently map a verified WorkOS organization to a local organization.

    Returns ``None`` when the identifier is implausible (caller fails closed to
    onboarding). Otherwise returns the (existing or newly created) local org.
    """
    if not _valid_workos_org_id(workos_org_id):
        logger.info("bootstrap reject: implausible workos org id")
        return None
    with SessionLocal() as session:
        org = _get_or_create_org(session, workos_org_id)
        return BootstrappedOrg(id=str(org.id), slug=org.slug, name=org.name)


def _get_or_create_org(session: Session, workos_org_id: str) -> Organization:
    org = session.scalar(
        select(Organization).where(Organization.workos_org_id == workos_org_id)
    )
    if org is not None:
        return org
    base_slug = _derive_org_slug(workos_org_id)
    name = _derive_org_name(workos_org_id)
    for attempt in range(_MAX_SLUG_ATTEMPTS):
        slug = base_slug if attempt == 0 else f"{base_slug}-{attempt + 1}"
        org = Organization(workos_org_id=workos_org_id, slug=slug, name=name)
        session.add(org)
        try:
            session.commit()
            return org
        except IntegrityError:
            session.rollback()
            # A concurrent request may have won the unique workos_org_id race.
            existing = session.scalar(
                select(Organization).where(Organization.workos_org_id == workos_org_id)
            )
            if existing is not None:
                return existing
            # Otherwise the derived slug collided with a *different* org; the
            # next attempt appends a disambiguating suffix.
    raise RuntimeError("could not allocate a unique organization slug")


def bootstrap_identity(
    *, workos_user_id: str, workos_org_id: str | None
) -> BootstrapResult:
    """Bootstrap the local user and (when present and valid) organization.

    ``workos_org_id`` may be ``None`` (a WorkOS user with no active
    organization); in that case ``org`` is ``None`` and the caller surfaces the
    onboarding state.
    """
    local_user_id = bootstrap_user(workos_user_id)
    org = bootstrap_organization(workos_org_id) if workos_org_id else None
    return BootstrapResult(local_user_id=local_user_id, org=org)
