from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import bind_org, get_session
from app.core.security import Claims, decode_token
from app.models import Membership, Role, User
from app.services import sessions

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False)


async def get_claims(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Claims:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification requise",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    claims = decode_token(credentials.credentials, "access")
    # Session révoquée (déconnexion, mot de passe changé) : le jeton d'accès ne vaut plus rien.
    if claims is None or not await sessions.is_active(session, claims):
        raise unauthorized
    return claims


CurrentClaims = Annotated[Claims, Depends(get_claims)]


async def get_current_user(session: SessionDep, claims: CurrentClaims) -> User:
    user = await session.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_membership(
    *roles: Role,
) -> Callable[[UUID, CurrentUser, AsyncSession], Awaitable[Membership]]:
    """Vérifie que l'utilisateur est membre de `org_id` (404 sinon) et a l'un des rôles."""

    async def dependency(org_id: UUID, user: CurrentUser, session: SessionDep) -> Membership:
        membership = await session.scalar(
            select(Membership).where(
                Membership.organization_id == org_id, Membership.user_id == user.id
            )
        )
        if membership is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Organisation introuvable")
        if roles and membership.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants")
        await bind_org(session, org_id)
        return membership

    return dependency


AnyMember = Annotated[Membership, Depends(require_membership())]
OrgAdmin = Annotated[Membership, Depends(require_membership(Role.ADMIN))]
