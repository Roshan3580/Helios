"""Browser-safe response models for human-authenticated /v2/user routes.

Never include raw JWTs, WorkOS API credentials, or project API keys.
"""

from uuid import UUID

from pydantic import BaseModel


class UserOrganizationRead(BaseModel):
    id: UUID | None
    workos_org_id: str | None
    slug: str | None
    name: str | None
    linked: bool


class UserMeRead(BaseModel):
    user_id: UUID
    workos_user_id: str
    organization: UserOrganizationRead
    role: str | None
    permissions: list[str]


class UserProjectRead(BaseModel):
    id: UUID
    slug: str
    name: str
    environment: str
