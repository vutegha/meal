from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, params, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import bind_org, get_session
from app.core.security import Claims, decode_token
from app.models import Membership, Role, User, UserSession
from app.services import billing, sessions

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification requise",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _decode(credentials: HTTPAuthorizationCredentials | None) -> Claims:
    if credentials is None:
        raise _unauthorized()
    claims = decode_token(credentials.credentials, "access")
    if claims is None:
        raise _unauthorized()
    return claims


Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


async def get_claims(session: SessionDep, credentials: Credentials) -> Claims:
    claims = _decode(credentials)
    # Session révoquée (déconnexion, mot de passe changé) : le jeton d'accès ne vaut plus rien.
    if not await sessions.is_active(session, claims):
        raise _unauthorized()
    return claims


CurrentClaims = Annotated[Claims, Depends(get_claims)]


async def get_current_user(session: SessionDep, credentials: Credentials) -> User:
    """Utilisateur actif d'une session ouverte : une seule requête, à chaque appel de l'API."""
    claims = _decode(credentials)
    user = await session.scalar(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            User.id == claims.user_id,
            User.is_active.is_(True),
            UserSession.id == claims.session_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > func.now(),
        )
    )
    if user is None:
        raise _unauthorized()
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


def plan_feature(feature: str) -> params.Depends:
    """Réserve une route aux formules qui ouvrent `feature` (402 sinon), après le contrôle
    d'appartenance : un non-membre reçoit toujours 404."""

    async def dependency(org_id: UUID, _: AnyMember, session: SessionDep) -> None:
        await billing.require_feature(session, org_id, feature)

    return params.Depends(dependency)
