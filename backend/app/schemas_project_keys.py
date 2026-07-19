"""Browser-safe schemas for self-serve project and API-key management.

``CreatedProjectApiKeyRead`` is the only schema that may carry plaintext key
material, and only in the successful creation response.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.security.api_keys import VALID_SCOPES


class CreateUserProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=128)
    environment: (
        Literal["production", "staging", "development", "test"] | None
    ) = None


class CreateProjectApiKeyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=128)
    scopes: list[str] = Field(..., min_length=1)

    @field_validator("scopes")
    @classmethod
    def _scopes_non_empty_items(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("at least one scope is required")
        return value


class ProjectApiKeyMetadataRead(BaseModel):
    """Redacted key metadata safe for list and revoke responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    key_identifier: str
    scopes: list[str]
    created_at: datetime
    revoked_at: datetime | None
    status: Literal["active", "revoked"]

    @model_validator(mode="before")
    @classmethod
    def _from_orm(cls, data: object) -> object:
        if isinstance(data, dict):
            return data
        # ORM ProjectAPIKey → dict with derived fields.
        from app.services.user_api_key_service import display_key_identifier

        scopes = list(getattr(data, "scopes", []) or [])
        # Stable scope order for serialization.
        scopes = sorted(scopes, key=lambda s: (s not in VALID_SCOPES, s))
        revoked_at = getattr(data, "revoked_at", None)
        return {
            "id": getattr(data, "id"),
            "name": getattr(data, "name"),
            "key_identifier": display_key_identifier(getattr(data, "key_prefix")),
            "scopes": scopes,
            "created_at": getattr(data, "created_at"),
            "revoked_at": revoked_at,
            "status": "revoked" if revoked_at is not None else "active",
        }


class CreatedProjectApiKeyRead(BaseModel):
    """One-time creation response. Never reuse for list/log payloads."""

    key: ProjectApiKeyMetadataRead
    plaintext_key: str

    def __repr__(self) -> str:
        return (
            f"CreatedProjectApiKeyRead(key={self.key!r}, plaintext_key='***REDACTED***')"
        )

    def __str__(self) -> str:
        return self.__repr__()
