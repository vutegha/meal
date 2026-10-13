from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import AccountType, Membership, Role
from app.services.billing import account_type_of, features_of


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
    account_type: AccountType
    plan: str | None
    features: list[str]


class UserOut(ORMModel):
    id: UUID
    email: str
    full_name: str
    is_active: bool


class MeOut(UserOut):
    is_platform_admin: bool
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
    """L'organisation doit être chargée (avec son abonnement, chargé d'office avec elle)."""
    org = membership.organization
    return MyOrganizationOut.model_validate(
        {
            **OrganizationOut.model_validate(org).model_dump(),
            "role": membership.role,
            "account_type": account_type_of(org.subscription),
            "plan": org.subscription.plan if org.subscription else None,
            "features": features_of(org.subscription),
        }
    )
