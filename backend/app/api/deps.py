from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, params, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import bind_org, get_session
from app.core.security import Claims, decode_token
from app.models import Membership, Role, User, UserSession
from app.services import billing, sessions

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False)


@dataclass
class _Access:
    """Ce que le contrôle du jeton a déjà lu : évite une requête par dépendance suivante."""

    user: User
    org_id: UUID | None
    membership: Membership | None


_ACCESS_KEY = "access"


def _path_org(request: Request) -> UUID | None:
    try:
        return UUID(request.path_params.get("org_id", ""))
    except ValueError:
        return None


async def get_claims(
    request: Request,
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
    if claims is None:
        raise unauthorized
    # Une seule requête pour la session, l'utilisateur et, sur une route d'organisation, son
    # appartenance : `get_current_user` et `require_membership` réutilisent ce résultat.
    org_id = _path_org(request)
    query = (
        select(UserSession, User, Membership)
        .join(User, User.id == UserSession.user_id)
        .outerjoin(
            Membership,
            and_(Membership.user_id == User.id, Membership.organization_id == org_id),
        )
        .where(UserSession.id == claims.session_id)
    )
    row = (await session.execute(query)).one_or_none()
    # Session révoquée (déconnexion, mot de passe changé) : le jeton d'accès ne vaut plus rien.
    if row is None or not sessions.record_is_active(row[0], claims):
        raise unauthorized
    session.info[_ACCESS_KEY] = _Access(user=row[1], org_id=org_id, membership=row[2])
    return claims


CurrentClaims = Annotated[Claims, Depends(get_claims)]


async def get_current_user(session: SessionDep, claims: CurrentClaims) -> User:
    access: _Access | None = session.info.get(_ACCESS_KEY)
    user = access.user if access else await session.get(User, claims.user_id)
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
        access: _Access | None = session.info.get(_ACCESS_KEY)
        if access and access.org_id == org_id and access.user.id == user.id:
            membership = access.membership
        else:
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
