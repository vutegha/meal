"""Application d'une proposition validée : cadre logique, indicateurs et budget."""

import calendar
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    PARENT_LEVEL,
    Aggregation,
    BudgetLine,
    Indicator,
    LogframeNode,
    NodeLevel,
    Project,
)
from app.schemas.ai import ApplyLogframeIn, ApplyNode, ExtractedProject
from app.services import projects as svc


def _invalid(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def month_start(origin: date, month: int) -> date:
    """Premier jour du `month`-ième mois du projet (1 = mois de `origin`)."""
    index = origin.year * 12 + origin.month - 1 + month - 1
    return date(index // 12, index % 12 + 1, 1)


def month_end(origin: date, month: int) -> date:
    start = month_start(origin, month)
    return start.replace(day=calendar.monthrange(start.year, start.month)[1])


def planned_period(origin: date | None, node: ApplyNode) -> tuple[date | None, date | None]:
    """Période au chronogramme d'une activité à partir des mois relatifs du document."""
    if origin is None or node.level not in ("activity", "sub_activity"):
        return None, None
    first = node.start_month or node.end_month
    if first is None:
        return None, None
    first = max(first, 1)
    last = max(node.end_month or first, first)
    return month_start(origin, first), month_end(origin, last)


def _iso(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def complete_project(project: Project, info: ExtractedProject | None, summary: str) -> list[str]:
    """Complète la fiche du projet avec ce que les documents disent, sans écraser la saisie."""
    filled: list[str] = []
    if summary and not project.description:
        project.description = summary
        filled.append("description")
    if info is None:
        return filled
    if info.donor and not project.donor:
        project.donor = info.donor[:200]
        filled.append("donor")
    start, end = _iso(info.start_date), _iso(info.end_date)
    if (
        project.start_date is None
        and start is not None
        and (project.end_date is None or project.end_date >= start)
    ):
        project.start_date = start
        filled.append("start_date")
    if project.end_date is None and project.start_date is not None:
        if end is None and info.duration_months:
            end = month_end(project.start_date, info.duration_months)
        if end is not None and end >= project.start_date:
            project.end_date = end
            filled.append("end_date")
    if info.zones and not project.zones:
        project.zones = info.zones
        filled.append("zones")
    if info.target_groups and not project.target_groups:
        project.target_groups = info.target_groups
        filled.append("target_groups")
    return filled


async def apply_logframe(
    session: AsyncSession,
    project: Project,
    body: ApplyLogframeIn,
    info: ExtractedProject | None = None,
    summary: str = "",
) -> dict[str, Any]:
    by_ref = {node.ref: node for node in body.nodes}
    if len(by_ref) != len(body.nodes):
        raise _invalid("Deux éléments portent la même référence")

    # Vérifie la hiérarchie et ordonne les parents avant leurs enfants.
    ordered: list[str] = []
    visiting: set[str] = set()

    def visit(ref: str) -> None:
        if ref in ordered:
            return
        if ref in visiting:
            raise _invalid(f"Cycle dans le cadre logique autour de « {ref} »")
        visiting.add(ref)
        node = by_ref[ref]
        level = NodeLevel(node.level)
        expected = PARENT_LEVEL[level]
        if node.parent_ref is None:
            if expected is not None:
                raise _invalid(f"« {node.code or ref} » n'a pas de parent retenu")
        else:
            parent = by_ref.get(node.parent_ref)
            if parent is None:
                raise _invalid(
                    f"Le parent de « {node.code or ref} » n'est pas retenu : "
                    "retenez-le aussi ou écartez cet élément"
                )
            if NodeLevel(parent.level) != expected:
                raise _invalid(f"« {node.code or ref} » est rattaché à un niveau incohérent")
            visit(node.parent_ref)
        visiting.discard(ref)
        ordered.append(ref)

    for ref in by_ref:
        visit(ref)

    filled = complete_project(project, info, summary)

    ids: dict[str, UUID] = {}
    positions: dict[UUID | None, int] = {}
    for ref in ordered:
        node = by_ref[ref]
        parent_id = ids[node.parent_ref] if node.parent_ref else None
        if parent_id not in positions:
            positions[parent_id] = await svc.next_position(session, project.id, parent_id)
        planned_start, planned_end = planned_period(project.start_date, node)
        created = LogframeNode(
            organization_id=project.organization_id,
            project_id=project.id,
            parent_id=parent_id,
            level=NodeLevel(node.level),
            code=node.code[:40],
            title=node.title,
            assumptions=node.assumptions,
            position=positions[parent_id],
            planned_start=planned_start,
            planned_end=planned_end,
        )
        positions[parent_id] += 1
        session.add(created)
        await session.flush()
        ids[ref] = created.id

    for indicator in body.indicators:
        if indicator.node_ref not in ids:
            raise _invalid(f"L'indicateur « {indicator.name} » vise un élément non retenu")
        session.add(
            Indicator(
                organization_id=project.organization_id,
                project_id=project.id,
                node_id=ids[indicator.node_ref],
                code=indicator.code[:40],
                name=indicator.name,
                unit=indicator.unit[:40],
                baseline=_decimal(indicator.baseline),
                target=_decimal(indicator.target),
                aggregation=Aggregation(indicator.aggregation),
                disaggregations=indicator.disaggregations,
                source_of_verification=indicator.source_of_verification,
            )
        )

    activity_levels = {level.value for level in svc.ACTIVITY_LEVELS}
    for line in body.budget_lines:
        activity_id = None
        if line.activity_ref is not None:
            target = by_ref.get(line.activity_ref)
            if target is None or target.level not in activity_levels:
                raise _invalid(f"La ligne « {line.label} » vise une activité non retenue")
            activity_id = ids[line.activity_ref]
        if min(line.quantity, line.unit_cost, line.frequency) < 0:
            raise _invalid(f"La ligne « {line.label} » contient une valeur négative")
        session.add(
            BudgetLine(
                organization_id=project.organization_id,
                project_id=project.id,
                activity_id=activity_id,
                donor_line_code=line.donor_line_code[:40],
                label=line.label[:300],
                category=line.category[:100],
                quantity=Decimal(str(line.quantity)),
                unit=line.unit[:40],
                unit_cost=Decimal(str(line.unit_cost)).quantize(Decimal("0.01")),
                frequency=Decimal(str(line.frequency)),
                is_estimate=line.is_estimate,
            )
        )
    await session.flush()
    scheduled = sum(1 for node in body.nodes if planned_period(project.start_date, node)[0])
    return {
        "project_fields": filled,
        "scheduled": scheduled,
        "nodes": len(ids),
        "indicators": len(body.indicators),
        "budget_lines": len(body.budget_lines),
    }
