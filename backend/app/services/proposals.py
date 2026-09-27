"""Application d'une proposition validée : cadre logique, indicateurs et budget."""

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
from app.schemas.ai import ApplyLogframeIn
from app.services import projects as svc


def _invalid(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


async def apply_logframe(
    session: AsyncSession, project: Project, body: ApplyLogframeIn
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

    ids: dict[str, UUID] = {}
    positions: dict[UUID | None, int] = {}
    for ref in ordered:
        node = by_ref[ref]
        parent_id = ids[node.parent_ref] if node.parent_ref else None
        if parent_id not in positions:
            positions[parent_id] = await svc.next_position(session, project.id, parent_id)
        created = LogframeNode(
            organization_id=project.organization_id,
            project_id=project.id,
            parent_id=parent_id,
            level=NodeLevel(node.level),
            code=node.code[:40],
            title=node.title,
            assumptions=node.assumptions,
            position=positions[parent_id],
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
    return {
        "nodes": len(ids),
        "indicators": len(body.indicators),
        "budget_lines": len(body.budget_lines),
    }
