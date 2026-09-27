import re
import secrets
import unicodedata

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import bind_org
from app.models import Membership, Organization, Role, User
from app.services import audit


def slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug[:60] or "organisation"


async def unique_slug(session: AsyncSession, name: str) -> str:
    base = slugify(name)
    slug = base
    while await session.scalar(select(Organization.id).where(Organization.slug == slug)):
        slug = f"{base}-{secrets.token_hex(3)}"
    return slug


async def create_organization(
    session: AsyncSession, *, name: str, owner: User, default_language: str = "fr"
) -> Organization:
    org = Organization(
        name=name, slug=await unique_slug(session, name), default_language=default_language
    )
    session.add(org)
    await session.flush()
    await bind_org(session, org.id)
    session.add(Membership(organization_id=org.id, user_id=owner.id, role=Role.ADMIN))
    audit.record(
        session,
        organization_id=org.id,
        actor_id=owner.id,
        action="organization.created",
        entity_type="organization",
        entity_id=org.id,
        data={"name": name},
    )
    return org
