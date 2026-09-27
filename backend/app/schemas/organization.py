from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Membership, Role


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class OrganizationIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    default_language: str = Field(default="fr", pattern="^(fr|en)$")


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    default_language: str | None = Field(default=None, pattern="^(fr|en)$")


class OrganizationOut(ORMModel):
    id: UUID
    name: str
    slug: str
    default_language: str
    created_at: datetime


class MyOrganizationOut(OrganizationOut):
    role: Role


class UserOut(ORMModel):
    id: UUID
    email: str
    full_name: str
    is_active: bool


class MeOut(UserOut):
    organizations: list[MyOrganizationOut]


class MemberIn(BaseModel):
    email: EmailStr
    role: Role
    full_name: str | None = Field(default=None, max_length=200)
    initial_password: str | None = Field(default=None, min_length=8, max_length=128)


class MemberUpdate(BaseModel):
    role: Role


class MemberOut(ORMModel):
    id: UUID
    role: Role
    user: UserOut
    created_at: datetime


class AuditLogOut(ORMModel):
    id: UUID
    actor_id: UUID | None
    action: str
    entity_type: str
    entity_id: UUID | None
    data: dict[str, Any]
    created_at: datetime


def my_organization(membership: Membership) -> MyOrganizationOut:
    return MyOrganizationOut.model_validate(
        {
            **OrganizationOut.model_validate(membership.organization).model_dump(),
            "role": membership.role,
        }
    )
