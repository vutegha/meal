from typing import Literal, Self

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


class RefreshIn(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
