"""Modèles de documents de l'organisation (TdR, rapports d'activité, rapports périodiques)."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select

from app.api.deps import AnyMember, SessionDep, require_membership
from app.api.projects import _log
from app.models import DocumentTemplate, Membership, Role
from app.schemas.template import (
    BuiltinSection,
    BuiltinTemplates,
    TemplateIn,
    TemplateOut,
    TemplateUpdate,
)
from app.services import periodic as periodic_svc
from app.services import projects as svc
from app.services import report as report_svc
from app.services import tor as tor_svc

router = APIRouter(prefix="/orgs/{org_id}/templates", tags=["modèles"])

Manager = Annotated[Membership, Depends(require_membership(Role.ADMIN, Role.PROJECT_MANAGER))]


def _builtin(sections: list[tuple[str, str]], computed: set[str]) -> list[BuiltinSection]:
    return [BuiltinSection(key=k, title=t, computed=k in computed) for k, t in sections]


@router.get("/builtin", response_model=BuiltinTemplates)
async def builtin_templates(org_id: UUID, _: AnyMember) -> BuiltinTemplates:
    """Sections intégrées à l'application, point de départ d'un nouveau modèle."""
    return BuiltinTemplates(
        tor=_builtin(tor_svc.DEFAULT_SECTIONS, {tor_svc.BUDGET_KEY}),
        report=_builtin(report_svc.REPORT_SECTIONS, report_svc.COMPUTED),
        periodic=_builtin(periodic_svc.PERIODIC_SECTIONS, periodic_svc.COMPUTED),
    )


@router.get("", response_model=list[TemplateOut])
async def list_templates(org_id: UUID, _: AnyMember, session: SessionDep) -> list[DocumentTemplate]:
    rows = await session.scalars(
        select(DocumentTemplate)
        .where(DocumentTemplate.organization_id == org_id)
        .order_by(DocumentTemplate.kind, DocumentTemplate.donor, DocumentTemplate.name)
    )
    return list(rows)


async def _get(session: SessionDep, org_id: UUID, template_id: UUID) -> DocumentTemplate:
    template = await session.scalar(
        select(DocumentTemplate).where(
            DocumentTemplate.id == template_id, DocumentTemplate.organization_id == org_id
        )
    )
    if template is None:
        raise svc.not_found("Modèle")
    return template


async def _single_default(session: SessionDep, template: DocumentTemplate) -> None:
    """Un seul modèle par défaut par type de document et par bailleur."""
    if not template.is_default:
        return
    others = await session.scalars(
        select(DocumentTemplate).where(
            DocumentTemplate.organization_id == template.organization_id,
            DocumentTemplate.kind == template.kind,
            func.lower(DocumentTemplate.donor) == template.donor.lower(),
            DocumentTemplate.id != template.id,
        )
    )
    for other in others:
        other.is_default = False


def _dump(body: TemplateIn | TemplateUpdate) -> dict[str, Any]:
    return body.model_dump(exclude_unset=isinstance(body, TemplateUpdate))


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    org_id: UUID, body: TemplateIn, member: Manager, session: SessionDep
) -> DocumentTemplate:
    template = DocumentTemplate(**_dump(body), organization_id=org_id, created_by=member.user_id)
    session.add(template)
    await session.flush()
    await _single_default(session, template)
    _log(session, member, "template.created", "template", template.id, {"name": template.name})
    await session.commit()
    await session.refresh(template)
    return template


@router.patch("/{template_id}", response_model=TemplateOut)
async def update_template(
    org_id: UUID, template_id: UUID, body: TemplateUpdate, member: Manager, session: SessionDep
) -> DocumentTemplate:
    template = await _get(session, org_id, template_id)
    for field, value in _dump(body).items():
        setattr(template, field, value.strip() if isinstance(value, str) else value)
    await session.flush()
    await _single_default(session, template)
    _log(session, member, "template.updated", "template", template.id, {"name": template.name})
    await session.commit()
    await session.refresh(template)
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    org_id: UUID, template_id: UUID, member: Manager, session: SessionDep
) -> None:
    """Les documents déjà rédigés gardent leurs sections ; seule la mise en page change."""
    template = await _get(session, org_id, template_id)
    _log(session, member, "template.deleted", "template", template.id, {"name": template.name})
    await session.delete(template)
    await session.commit()
