from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.security import create_token, decode_token, hash_password, verify_password
from app.models import Membership, User
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenPair
from app.schemas.organization import MeOut, my_organization
from app.services import billing, ratelimit
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
    plan = body.plan or billing.DEFAULT_PLAN[body.account_type]
    if billing.get_plan(plan).account_type != body.account_type:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Cette formule ne correspond pas au type de compte",
        )
    if await session.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette adresse e-mail est déjà utilisée")
    user = User(email=email, full_name=body.full_name, password_hash=hash_password(body.password))
    session.add(user)
    await session.flush()
    name = body.organization_name or f"Espace de {body.full_name}"[:200]
    await create_organization(session, name=name, owner=user, plan=plan, cycle=body.cycle)
    await session.commit()
    return _tokens(user)


@router.post(
    "/login",
    response_model=TokenPair,
    responses={429: {"description": "Trop de tentatives, réessayer plus tard"}},
)
async def login(body: LoginIn, request: Request, session: SessionDep) -> TokenPair:
    settings = get_settings()
    email = body.email.lower()
    keys = {
        f"email:{email}": settings.login_max_failures,
        f"ip:{request.client.host if request.client else 'inconnue'}": (
            settings.login_max_failures_per_ip
        ),
    }
    for key, limit in keys.items():
        if await ratelimit.failures(key) >= limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Trop de tentatives de connexion. Réessayez dans "
                f"{settings.login_window_minutes} minutes.",
                headers={"Retry-After": str(settings.login_window_minutes * 60)},
            )
    user = await session.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        for key in keys:
            await ratelimit.add_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Identifiants invalides")
    await ratelimit.reset(f"email:{email}")
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
