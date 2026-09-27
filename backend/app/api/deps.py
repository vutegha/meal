from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import bind_org, get_session
from app.core.security import decode_token
from app.models import Membership, Role, User

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification requise",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    user_id = decode_token(credentials.credentials, "access")
    if user_id is None:
        raise unauthorized
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
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
