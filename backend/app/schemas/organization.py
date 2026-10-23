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


class PrivacySettings(ORMModel):
    """Réglages de protection des données de l'espace."""

    ai_enabled: bool
    feedback_retention_months: int = Field(ge=0, le=240)
    sms_acknowledgement: bool
    privacy_contact: str = Field(max_length=200)


class OrganizationCloseIn(BaseModel):
    # Nom de l'espace recopié et mot de passe : deux confirmations pour un geste définitif.
    name: str = Field(max_length=200)
    password: str = Field(max_length=128)
    code: str | None = Field(default=None, max_length=10)
    # Supprimer aussi son compte quand cet espace était le seul.
    delete_account: bool = False


class PrivacyUpdate(BaseModel):
    ai_enabled: bool | None = None
    feedback_retention_months: int | None = Field(default=None, ge=0, le=240)
    sms_acknowledgement: bool | None = None
    privacy_contact: str | None = Field(default=None, max_length=200)


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
    organizations: list[MyOrganizationOut]
    must_change_password: bool = False
    totp_enabled: bool = False
    mfa_recommended: bool = False


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
