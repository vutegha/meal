from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.models import AccountType


class RegisterIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    # Facultatif pour un compte individuel : son espace porte alors le nom de la personne.
    organization_name: str | None = Field(default=None, min_length=2, max_length=200)
    account_type: AccountType = AccountType.ORGANIZATION
    # Formule et cycle choisis sur la page Tarifs ; par défaut la formule du type de compte.
    plan: str | None = None
    cycle: Literal["monthly", "annual", "usage"] = "monthly"

    @model_validator(mode="after")
    def _organization_named(self) -> Self:
        if self.account_type == AccountType.ORGANIZATION and not self.organization_name:
            raise ValueError("Le nom de l'organisation est requis")
        return self


class LoginIn(BaseModel):
    email: EmailStr
    # Même plafond qu'à l'inscription : un mot de passe démesuré coûterait cher à vérifier.
    password: str = Field(max_length=128)
    # Code de l'application d'authentification, quand la double authentification est active.
    otp: str | None = Field(default=None, max_length=10)


class RefreshIn(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    # Mot de passe initial fixé par un administrateur : l'interface demande d'en choisir un.
    must_change_password: bool = False


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class PasswordResetIn(BaseModel):
    token: str = Field(max_length=200)
    new_password: str = Field(min_length=8, max_length=128)


class PasswordForgotIn(BaseModel):
    email: EmailStr


class ResetLinkOut(BaseModel):
    # Chemin de l'interface à transmettre à la personne : /reset-password?token=…
    path: str
    expires_at: datetime


class TotpSetupOut(BaseModel):
    secret: str
    uri: str
    # QR code à scanner avec l'application d'authentification (image SVG en data: URL).
    qr_svg: str


class AccountDeleteIn(BaseModel):
    password: str = Field(max_length=128)
    # Code de double authentification, quand elle est active.
    code: str | None = Field(default=None, max_length=10)


class TotpCodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=10)


class SessionOut(BaseModel):
    id: UUID
    created_at: datetime
    rotated_at: datetime | None
    user_agent: str
    current: bool
