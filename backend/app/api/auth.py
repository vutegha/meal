import base64
from datetime import UTC, datetime

import segno
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentClaims, CurrentUser, SessionDep
from app.core import crypto
from app.core.config import get_settings
from app.core.security import decode_token, hash_password, verify_password
from app.models import Membership, Role, User, UserSession
from app.schemas.auth import (
    AccountDeleteIn,
    LoginIn,
    PasswordChangeIn,
    PasswordForgotIn,
    PasswordResetIn,
    RefreshIn,
    RegisterIn,
    SessionOut,
    TokenPair,
    TotpCodeIn,
    TotpSetupOut,
)
from app.schemas.organization import MeOut, my_organization
from app.services import accounts, billing, mailer, passwords, ratelimit, sessions
from app.services.organizations import create_organization

router = APIRouter(prefix="/auth", tags=["auth"])

OTP_HEADER = "X-OTP-Required"


def _agent(request: Request) -> str:
    return request.headers.get("user-agent", "")


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterIn, request: Request, session: SessionDep) -> TokenPair:
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
    pair = await sessions.open_session(session, user, _agent(request))
    await session.commit()
    return pair


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
    if user.totp_enabled_at and user.totp_secret:
        if not body.otp:
            # Mot de passe correct : l'interface demande le code de l'application.
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Code de vérification requis",
                headers={OTP_HEADER: "1"},
            )
        secret = crypto.decrypt(user.totp_secret)
        if secret is None or not crypto.verify_totp(secret, body.otp):
            for key in keys:
                await ratelimit.add_failure(key)
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Code de vérification incorrect",
                headers={OTP_HEADER: "1"},
            )
    await ratelimit.reset(f"email:{email}")
    pair = await sessions.open_session(session, user, _agent(request))
    await session.commit()
    return pair


@router.post("/refresh", response_model=TokenPair)
async def refresh(body: RefreshIn, session: SessionDep) -> TokenPair:
    claims = decode_token(body.refresh_token, "refresh")
    user = await session.get(User, claims.user_id) if claims else None
    pair = (
        await sessions.rotate(session, user, claims) if user and user.is_active and claims else None
    )
    await session.commit()
    if pair is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton de rafraîchissement invalide")
    return pair


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(claims: CurrentClaims, session: SessionDep) -> None:
    """Ferme la session en cours : ses jetons ne sont plus acceptés, même volés."""
    await sessions.revoke(session, claims.session_id)
    await session.commit()


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(claims: CurrentClaims, session: SessionDep) -> None:
    """Ferme toutes les sessions de la personne, sur tous ses appareils."""
    await sessions.revoke_all(session, claims.user_id)
    await session.commit()


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(claims: CurrentClaims, session: SessionDep) -> list[SessionOut]:
    rows = await session.scalars(
        select(UserSession)
        .where(UserSession.user_id == claims.user_id, UserSession.revoked_at.is_(None))
        .order_by(UserSession.created_at.desc())
    )
    return [
        SessionOut(
            id=r.id,
            created_at=r.created_at,
            rotated_at=r.rotated_at,
            user_agent=r.user_agent,
            current=r.id == claims.session_id,
        )
        for r in rows
    ]


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChangeIn, user: CurrentUser, claims: CurrentClaims, session: SessionDep
) -> None:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Mot de passe actuel incorrect")
    if body.new_password == body.current_password:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Choisissez un mot de passe différent"
        )
    await passwords.set_password(session, user, body.new_password, keep_session=claims.session_id)
    await session.commit()


@router.post("/password/forgot", status_code=status.HTTP_204_NO_CONTENT)
async def forgot_password(body: PasswordForgotIn, request: Request, session: SessionDep) -> None:
    """Envoie un lien par e-mail si l'adresse existe ; la réponse ne dit jamais si elle existe."""
    settings = get_settings()
    key = f"forgot:{request.client.host if request.client else 'inconnue'}"
    if await ratelimit.failures(key) >= settings.login_max_failures_per_ip:
        return
    await ratelimit.add_failure(key)
    user = await session.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.is_active or not mailer.enabled():
        return
    token, _ = await passwords.create_reset(session, user, created_by=None)
    await session.commit()
    link = settings.public_url.rstrip("/") + passwords.reset_path(token)
    await mailer.send(
        user.email,
        "We MEAL : réinitialisation du mot de passe",
        f"Bonjour {user.full_name},\n\nPour choisir un nouveau mot de passe, ouvrez ce lien "
        f"(valable {settings.password_reset_hours} heures, une seule fois) :\n{link}\n\n"
        "Si vous n'avez rien demandé, ignorez ce message.",
    )


@router.post("/password/reset", response_model=TokenPair)
async def reset_password(body: PasswordResetIn, request: Request, session: SessionDep) -> TokenPair:
    user = await passwords.use_reset(session, body.token)
    if user is None or not user.is_active:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Lien invalide ou expiré : demandez-en un nouveau",
        )
    await passwords.set_password(session, user, body.new_password)
    pair = await sessions.open_session(session, user, _agent(request))
    await session.commit()
    return pair


# --- Double authentification -------------------------------------------------------------


@router.post("/totp/setup", response_model=TotpSetupOut)
async def totp_setup(user: CurrentUser, session: SessionDep) -> TotpSetupOut:
    """Prépare un nouveau secret ; il n'est actif qu'une fois confirmé par un code."""
    if user.totp_enabled_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "La double authentification est déjà active")
    secret = crypto.new_totp_secret()
    user.totp_secret = crypto.encrypt(secret)
    await session.commit()
    uri = crypto.totp_uri(secret, user.email, get_settings().app_name)
    svg = segno.make(uri, error="m").svg_inline(scale=4)
    return TotpSetupOut(
        secret=secret,
        uri=uri,
        qr_svg="data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode(),
    )


@router.post("/totp/enable", status_code=status.HTTP_204_NO_CONTENT)
async def totp_enable(body: TotpCodeIn, user: CurrentUser, session: SessionDep) -> None:
    secret = crypto.decrypt(user.totp_secret) if user.totp_secret else None
    if secret is None or not crypto.verify_totp(secret, body.code):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Code incorrect")
    user.totp_enabled_at = user.totp_enabled_at or datetime.now(UTC)
    await session.commit()


@router.post("/totp/disable", status_code=status.HTTP_204_NO_CONTENT)
async def totp_disable(body: TotpCodeIn, user: CurrentUser, session: SessionDep) -> None:
    secret = crypto.decrypt(user.totp_secret) if user.totp_secret else None
    if not user.totp_enabled_at or secret is None or not crypto.verify_totp(secret, body.code):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Code incorrect")
    user.totp_secret = None
    user.totp_enabled_at = None
    await session.commit()


@router.post("/me/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(body: AccountDeleteIn, user: CurrentUser, session: SessionDep) -> None:
    """Supprime son propre compte : il est anonymisé et ne peut plus se connecter."""
    if error := accounts.confirmation_error(user, body.password, body.code):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, error)
    if blocking := await accounts.blocking_organizations(session, user):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Vous êtes le seul administrateur de : "
            + ", ".join(blocking)
            + ". Nommez un autre administrateur ou fermez l'espace avant de supprimer "
            "votre compte.",
        )
    await accounts.delete_account(session, user)
    await session.commit()


@router.get("/me", response_model=MeOut)
async def me(user: CurrentUser, session: SessionDep) -> MeOut:
    memberships = list(
        await session.scalars(
            select(Membership)
            .where(Membership.user_id == user.id)
            .options(selectinload(Membership.organization))
        )
    )
    admin = any(m.role == Role.ADMIN for m in memberships)
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        totp_enabled=user.totp_enabled_at is not None,
        # Administrateur sans double authentification : l'interface le lui recommande.
        mfa_recommended=admin and user.totp_enabled_at is None,
        organizations=[
            my_organization(m)
            for m in sorted(memberships, key=lambda m: m.organization.name.lower())
        ],
    )
