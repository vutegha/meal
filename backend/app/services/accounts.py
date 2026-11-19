"""Suppression d'un compte et fermeture d'un espace (droit à l'effacement).

Un compte supprimé est anonymisé plutôt qu'effacé : les saisies, réponses et validations qu'il
a faites restent celles de l'organisation, sans plus porter son nom ni son adresse e-mail.
Fermer un espace efface toutes ses données et tous ses fichiers ; seules les sauvegardes
chiffrées les gardent encore, le temps de leur rotation.
"""

import logging
import secrets
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import crypto
from app.core.db import bind_org
from app.core.security import hash_password, verify_password
from app.documents.storage import get_storage
from app.models import Membership, Organization, PasswordReset, Role, User, UserSession
from app.services import audit

logger = logging.getLogger(__name__)

DELETED_NAME = "Compte supprimé"


def confirmation_error(user: User, password: str, code: str | None) -> str | None:
    """Geste définitif : mot de passe, et code de double authentification quand elle est active."""
    if not verify_password(password, user.password_hash):
        return "Mot de passe incorrect"
    if user.totp_enabled_at:
        secret = crypto.decrypt(user.totp_secret) if user.totp_secret else None
        if secret is None or not crypto.verify_totp(secret, code or ""):
            return "Code de vérification incorrect"
    return None


async def blocking_organizations(session: AsyncSession, user: User) -> list[str]:
    """Espaces qui empêchent la suppression : la personne en est le seul administrateur."""
    memberships = await session.scalars(
        select(Membership)
        .where(Membership.user_id == user.id, Membership.role == Role.ADMIN)
        .options(selectinload(Membership.organization))
    )
    blocking = []
    for membership in memberships:
        admins = await session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(
                Membership.organization_id == membership.organization_id,
                Membership.role == Role.ADMIN,
            )
        )
        if (admins or 0) <= 1:
            blocking.append(membership.organization.name)
    return sorted(blocking, key=str.lower)


async def delete_account(session: AsyncSession, user: User) -> None:
    memberships = list(
        await session.scalars(select(Membership).where(Membership.user_id == user.id))
    )
    for membership in memberships:
        # Le journal de chaque espace n'accepte que des lignes de cet espace (RLS).
        await bind_org(session, membership.organization_id)
        audit.record(
            session,
            organization_id=membership.organization_id,
            actor_id=user.id,
            action="member.account_deleted",
            entity_type="membership",
            entity_id=membership.id,
            data={"role": membership.role.value},
        )
        await session.delete(membership)
        await session.flush()
    await session.execute(delete(UserSession).where(UserSession.user_id == user.id))
    await session.execute(delete(PasswordReset).where(PasswordReset.user_id == user.id))
    user.email = f"supprime-{user.id}@invalid"
    user.full_name = DELETED_NAME
    user.password_hash = hash_password(secrets.token_urlsafe(32))
    user.totp_secret = None
    user.totp_enabled_at = None
    user.must_change_password = False
    user.is_active = False


async def close_organization(session: AsyncSession, org_id: UUID) -> int:
    """Efface l'espace (toutes ses tables suivent) puis ses fichiers. Renvoie le nombre de
    fichiers effacés."""
    # Suppression en SQL : la base efface elle-même, en cascade, tout ce qui en dépend.
    await session.execute(delete(Organization).where(Organization.id == org_id))
    await session.commit()
    files = await get_storage().delete_prefix(f"{org_id}/")
    logger.info("Espace %s fermé : %s fichier(s) effacé(s)", org_id, files)
    return files
