from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import AnyMember, CurrentUser, OrgAdmin, SessionDep
from app.core.security import hash_password
from app.models import AuditLog, Membership, Organization, Role, User
from app.schemas.organization import (
    AuditLogOut,
    MemberIn,
    MemberOut,
    MemberUpdate,
    MyOrganizationOut,
    OrganizationIn,
    OrganizationOut,
    OrganizationUpdate,
    my_organization,
)
from app.services import audit
from app.services.organizations import create_organization

router = APIRouter(prefix="/orgs", tags=["organisations"])


@router.get("", response_model=list[MyOrganizationOut])
async def list_my_organizations(user: CurrentUser, session: SessionDep) -> list[MyOrganizationOut]:
    memberships = await session.scalars(
        select(Membership)
        .where(Membership.user_id == user.id)
        .options(selectinload(Membership.organization))
    )
    return sorted((my_organization(m) for m in memberships), key=lambda o: o.name.lower())


@router.post("", response_model=MyOrganizationOut, status_code=status.HTTP_201_CREATED)
async def create(body: OrganizationIn, user: CurrentUser, session: SessionDep) -> MyOrganizationOut:
    org = await create_organization(
        session, name=body.name, owner=user, default_language=body.default_language
    )
    await session.commit()
    return MyOrganizationOut.model_validate(
        {**OrganizationOut.model_validate(org).model_dump(), "role": Role.ADMIN}
    )


@router.get("/{org_id}", response_model=MyOrganizationOut)
async def get(membership: AnyMember, session: SessionDep) -> MyOrganizationOut:
    await session.refresh(membership, ["organization"])
    return my_organization(membership)


@router.patch("/{org_id}", response_model=OrganizationOut)
async def update(
    org_id: UUID, body: OrganizationUpdate, admin: OrgAdmin, session: SessionDep
) -> Organization:
    org = await session.get_one(Organization, org_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(org, field, value)
    audit.record(
        session,
        organization_id=org_id,
        actor_id=admin.user_id,
        action="organization.updated",
        entity_type="organization",
        entity_id=org_id,
        data=changes,
    )
    await session.commit()
    await session.refresh(org)
    return org


@router.get("/{org_id}/members", response_model=list[MemberOut])
async def list_members(org_id: UUID, _: AnyMember, session: SessionDep) -> list[Membership]:
    members = await session.scalars(
        select(Membership)
        .join(Membership.user)
        .where(Membership.organization_id == org_id)
        .options(selectinload(Membership.user))
        .order_by(User.full_name)
    )
    return list(members)


@router.post("/{org_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
async def add_member(
    org_id: UUID, body: MemberIn, admin: OrgAdmin, session: SessionDep
) -> Membership:
    email = body.email.lower()
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        if not body.full_name or not body.initial_password:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Nom complet et mot de passe initial requis pour un nouvel utilisateur",
            )
        user = User(
            email=email,
            full_name=body.full_name,
            password_hash=hash_password(body.initial_password),
        )
        session.add(user)
        await session.flush()
    elif await session.scalar(
        select(Membership.id).where(
            Membership.organization_id == org_id, Membership.user_id == user.id
        )
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette personne est déjà membre")

    membership = Membership(organization_id=org_id, user_id=user.id, role=body.role)
    session.add(membership)
    await session.flush()
    audit.record(
        session,
        organization_id=org_id,
        actor_id=admin.user_id,
        action="member.added",
        entity_type="membership",
        entity_id=membership.id,
        data={"email": email, "role": body.role.value},
    )
    await session.commit()
    await session.refresh(membership, ["user"])
    return membership


async def _get_member(session: SessionDep, org_id: UUID, member_id: UUID) -> Membership:
    membership = await session.scalar(
        select(Membership)
        .where(Membership.id == member_id, Membership.organization_id == org_id)
        .options(selectinload(Membership.user))
    )
    if membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membre introuvable")
    return membership


async def _ensure_other_admin(session: SessionDep, org_id: UUID) -> None:
    admins = await session.scalar(
        select(func.count())
        .select_from(Membership)
        .where(Membership.organization_id == org_id, Membership.role == Role.ADMIN)
    )
    if (admins or 0) <= 1:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "L'organisation doit garder au moins un administrateur"
        )


@router.patch("/{org_id}/members/{member_id}", response_model=MemberOut)
async def update_member(
    org_id: UUID, member_id: UUID, body: MemberUpdate, admin: OrgAdmin, session: SessionDep
) -> Membership:
    membership = await _get_member(session, org_id, member_id)
    if membership.role == Role.ADMIN and body.role != Role.ADMIN:
        await _ensure_other_admin(session, org_id)
    previous = membership.role
    membership.role = body.role
    audit.record(
        session,
        organization_id=org_id,
        actor_id=admin.user_id,
        action="member.role_changed",
        entity_type="membership",
        entity_id=membership.id,
        data={"email": membership.user.email, "from": previous.value, "to": body.role.value},
    )
    await session.commit()
    return membership


@router.delete("/{org_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    org_id: UUID, member_id: UUID, admin: OrgAdmin, session: SessionDep
) -> None:
    membership = await _get_member(session, org_id, member_id)
    if membership.role == Role.ADMIN:
        await _ensure_other_admin(session, org_id)
    audit.record(
        session,
        organization_id=org_id,
        actor_id=admin.user_id,
        action="member.removed",
        entity_type="membership",
        entity_id=membership.id,
        data={"email": membership.user.email, "role": membership.role.value},
    )
    await session.delete(membership)
    await session.commit()


@router.get("/{org_id}/audit", response_model=list[AuditLogOut])
async def list_audit(
    org_id: UUID,
    _: OrgAdmin,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[AuditLog]:
    entries = await session.scalars(
        select(AuditLog)
        .where(AuditLog.organization_id == org_id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id)
        .limit(limit)
        .offset(offset)
    )
    return list(entries)
