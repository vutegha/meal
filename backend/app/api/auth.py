from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.models import Membership, User
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenPair
from app.schemas.organization import MeOut, my_organization
from app.services.organizations import create_organization

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_token(user.id, "access"),
        refresh_token=create_token(user.id, "refresh"),
    )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, session: SessionDep) -> TokenPair:
    email = body.email.lower()
    if await session.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette adresse e-mail est déjà utilisée")
    user = User(email=email, full_name=body.full_name, password_hash=hash_password(body.password))
    session.add(user)
    await session.flush()
    await create_organization(session, name=body.organization_name, owner=user)
    await session.commit()
    return _tokens(user)


@router.post("/login", response_model=TokenPair)
async def login(body: LoginIn, session: SessionDep) -> TokenPair:
    user = await session.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants invalides")
    return _tokens(user)


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshIn, session: SessionDep) -> TokenPair:
    user_id = decode_token(body.refresh_token, "refresh")
    user = await session.get(User, user_id) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton de rafraîchissement invalide")
    return _tokens(user)


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser, session: SessionDep) -> MeOut:
    memberships = await session.scalars(
        select(Membership)
        .where(Membership.user_id == user.id)
        .options(selectinload(Membership.organization))
    )
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        organizations=[
            my_organization(m)
            for m in sorted(memberships, key=lambda m: m.organization.name.lower())
        ],
    )
