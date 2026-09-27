"""Choix du modèle d'un document : sections, consignes de rédaction et mise en page.

Ordre de priorité : le modèle choisi pour le document, puis le modèle du bailleur du projet,
puis le modèle par défaut de l'organisation, et enfin les sections intégrées à l'application.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.documents.render import Layout
from app.models import DocumentTemplate, Project

SectionSpec = tuple[str, str, str]  # clé, titre, consigne


@dataclass
class Plan:
    template_id: UUID | None
    sections: list[SectionSpec]
    layout: Layout | None


def layout_of(template: DocumentTemplate | None) -> Layout | None:
    if template is None or not template.layout:
        return None
    data: dict[str, Any] = template.layout
    return Layout(
        header=str(data.get("header", "")),
        footer=str(data.get("footer", "")),
        color=str(data.get("color") or Layout.color),
    )


async def pick(
    session: AsyncSession, project: Project, kind: str, template_id: UUID | None = None
) -> DocumentTemplate | None:
    candidates = list(
        await session.scalars(
            select(DocumentTemplate)
            .where(
                DocumentTemplate.organization_id == project.organization_id,
                DocumentTemplate.kind == kind,
            )
            .order_by(DocumentTemplate.created_at)
        )
    )
    if template_id:
        chosen = next((t for t in candidates if t.id == template_id), None)
        if chosen:
            return chosen
    donor = project.donor.strip().casefold()
    for_donor = [t for t in candidates if donor and t.donor.strip().casefold() == donor]
    if for_donor:
        return next((t for t in for_donor if t.is_default), for_donor[0])
    return next((t for t in candidates if t.is_default and not t.donor.strip()), None)


async def resolve(
    session: AsyncSession,
    project: Project,
    kind: str,
    builtin: list[tuple[str, str]],
    template_id: UUID | None = None,
) -> Plan:
    template = await pick(session, project, kind, template_id)
    if template is None or not template.sections:
        return Plan(None, [(k, t, "") for k, t in builtin], layout_of(template))
    return Plan(
        template.id,
        [(s["key"], s["title"], s.get("guidance", "")) for s in template.sections],
        layout_of(template),
    )


async def layout_for(
    session: AsyncSession, project: Project, kind: str, template_id: UUID | None
) -> Layout | None:
    return layout_of(await pick(session, project, kind, template_id))


def wanted(plan: Plan, computed: set[str]) -> list[SectionSpec]:
    """Sections à rédiger par l'IA : celles du modèle, hors tableaux calculés."""
    return [spec for spec in plan.sections if spec[0] not in computed]


def assemble(plan: Plan, contents: dict[str, str], fallback: str) -> list[dict[str, Any]]:
    return [
        {"key": key, "title": title, "content": contents.get(key) or fallback}
        for key, title, _ in plan.sections
    ]
