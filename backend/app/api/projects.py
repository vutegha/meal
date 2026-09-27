from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.api.deps import AnyMember, SessionDep, require_membership
from app.models import (
    PARENT_LEVEL,
    BudgetLine,
    Expense,
    Indicator,
    IndicatorValue,
    LogframeNode,
    Membership,
    NodeLevel,
    Project,
    Role,
)
from app.schemas.project import (
    BudgetLineIn,
    BudgetLineOut,
    BudgetLineUpdate,
    BudgetSummary,
    ExpenseIn,
    ExpenseOut,
    IndicatorIn,
    IndicatorOut,
    IndicatorUpdate,
    IndicatorValueIn,
    IndicatorValueOut,
    LogframeCheck,
    NodeIn,
    NodeOut,
    NodeTree,
    NodeUpdate,
    ProjectIn,
    ProjectOut,
    ProjectUpdate,
)
from app.services import audit
from app.services import projects as svc
from app.services.export import logframe_workbook

router = APIRouter(prefix="/orgs/{org_id}/projects", tags=["projets"])

# Qui peut modifier quoi.
Planner = Annotated[
    Membership,
    Depends(require_membership(Role.ADMIN, Role.PROJECT_MANAGER, Role.MEAL_OFFICER)),
]
FinanceEditor = Annotated[
    Membership, Depends(require_membership(Role.ADMIN, Role.PROJECT_MANAGER, Role.FINANCE))
]
Collector = Annotated[
    Membership,
    Depends(
        require_membership(Role.ADMIN, Role.PROJECT_MANAGER, Role.MEAL_OFFICER, Role.FIELD_AGENT)
    ),
]
ProjectAdmin = Annotated[Membership, Depends(require_membership(Role.ADMIN, Role.PROJECT_MANAGER))]


def _log(
    session: SessionDep,
    member: Membership,
    action: str,
    entity_type: str,
    entity_id: UUID,
    data: dict[str, Any] | None = None,
) -> None:
    audit.record(
        session,
        organization_id=member.organization_id,
        actor_id=member.user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        data=data,
    )


async def _flush(session: SessionDep, conflict: str) -> None:
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, conflict) from exc


# --- Projets ---------------------------------------------------------------


@router.get("", response_model=list[ProjectOut])
async def list_projects(org_id: UUID, _: AnyMember, session: SessionDep) -> list[Project]:
    rows = await session.scalars(
        select(Project).where(Project.organization_id == org_id).order_by(Project.code)
    )
    return list(rows)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    org_id: UUID, body: ProjectIn, member: ProjectAdmin, session: SessionDep
) -> Project:
    project = Project(organization_id=org_id, **body.model_dump())
    session.add(project)
    await _flush(session, "Un projet porte déjà ce code")
    _log(session, member, "project.created", "project", project.id, {"code": body.code})
    await session.commit()
    return project


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(org_id: UUID, project_id: UUID, _: AnyMember, session: SessionDep) -> Project:
    return await svc.get_project(session, org_id, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    org_id: UUID, project_id: UUID, body: ProjectUpdate, member: ProjectAdmin, session: SessionDep
) -> Project:
    project = await svc.get_project(session, org_id, project_id)
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        if value is None and field not in {"start_date", "end_date"}:
            continue
        setattr(project, field, value)
    if project.start_date and project.end_date and project.end_date < project.start_date:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "La date de fin doit suivre la date de début"
        )
    await _flush(session, "Un projet porte déjà ce code")
    _log(
        session,
        member,
        "project.updated",
        "project",
        project.id,
        body.model_dump(mode="json", exclude_unset=True),
    )
    await session.commit()
    await session.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    org_id: UUID, project_id: UUID, member: ProjectAdmin, session: SessionDep
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    _log(session, member, "project.deleted", "project", project.id, {"code": project.code})
    await session.delete(project)
    await session.commit()


@router.get("/{project_id}/export.xlsx", response_class=Response)
async def export_project(
    org_id: UUID, project_id: UUID, _: AnyMember, session: SessionDep
) -> Response:
    project = await svc.get_project(session, org_id, project_id)
    content = await logframe_workbook(session, project)
    filename = f"cadre-logique-{project.code}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Cadre logique --------------------------------------------------------


@router.get("/{project_id}/logframe", response_model=list[NodeTree])
async def get_logframe(
    org_id: UUID, project_id: UUID, _: AnyMember, session: SessionDep
) -> list[NodeTree]:
    project = await svc.get_project(session, org_id, project_id)
    return svc.build_tree(await svc.list_nodes(session, project.id))


@router.get("/{project_id}/logframe/check", response_model=LogframeCheck)
async def check_logframe(
    org_id: UUID, project_id: UUID, _: AnyMember, session: SessionDep
) -> LogframeCheck:
    project = await svc.get_project(session, org_id, project_id)
    nodes = await svc.list_nodes(session, project.id)
    indicators = await svc.list_indicators(session, project.id)
    measured = {i.node_id for i in indicators}
    budgeted = set(
        await session.scalars(
            select(BudgetLine.activity_id).where(BudgetLine.project_id == project.id)
        )
    )
    return LogframeCheck(
        nodes_without_indicator=[
            NodeOut.model_validate(n)
            for n in nodes
            if n.level in (NodeLevel.GOAL, NodeLevel.OUTCOME, NodeLevel.OUTPUT)
            and n.id not in measured
        ],
        indicators_without_source=[
            svc.indicator_out(i) for i in indicators if not i.source_of_verification.strip()
        ],
        activities_without_budget=[
            NodeOut.model_validate(n)
            for n in nodes
            if n.level in svc.ACTIVITY_LEVELS and n.id not in budgeted
        ],
    )


@router.post(
    "/{project_id}/logframe/nodes", response_model=NodeOut, status_code=status.HTTP_201_CREATED
)
async def create_node(
    org_id: UUID, project_id: UUID, body: NodeIn, member: Planner, session: SessionDep
) -> LogframeNode:
    project = await svc.get_project(session, org_id, project_id)
    expected_parent = PARENT_LEVEL[body.level]
    if body.parent_id is None:
        if expected_parent is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Un élément de niveau « {body.level.value} » doit avoir un parent "
                f"de niveau « {expected_parent.value} »",
            )
    else:
        parent = await svc.get_node(session, project, body.parent_id)
        if parent.level != expected_parent:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                f"Un élément de niveau « {body.level.value} » ne peut pas être rattaché "
                f"à un élément de niveau « {parent.level.value} »",
            )
    position = (
        body.position
        if body.position is not None
        else await svc.next_position(session, project.id, body.parent_id)
    )
    node = LogframeNode(
        organization_id=org_id,
        project_id=project.id,
        **body.model_dump(exclude={"position"}),
        position=position,
    )
    session.add(node)
    await session.flush()
    _log(
        session,
        member,
        "logframe.node_created",
        "logframe_node",
        node.id,
        {"level": body.level.value, "title": body.title},
    )
    await session.commit()
    return node


@router.patch("/{project_id}/logframe/nodes/{node_id}", response_model=NodeOut)
async def update_node(
    org_id: UUID,
    project_id: UUID,
    node_id: UUID,
    body: NodeUpdate,
    member: Planner,
    session: SessionDep,
) -> LogframeNode:
    project = await svc.get_project(session, org_id, project_id)
    node = await svc.get_node(session, project, node_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    for field, value in changes.items():
        setattr(node, field, value)
    _log(session, member, "logframe.node_updated", "logframe_node", node.id, changes)
    await session.commit()
    await session.refresh(node)
    return node


@router.delete("/{project_id}/logframe/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    org_id: UUID, project_id: UUID, node_id: UUID, member: Planner, session: SessionDep
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    node = await svc.get_node(session, project, node_id)
    _log(
        session,
        member,
        "logframe.node_deleted",
        "logframe_node",
        node.id,
        {"level": node.level.value, "title": node.title},
    )
    await session.delete(node)
    await session.commit()


# --- Budget -----------------------------------------------------------------


async def _check_activity(session: SessionDep, project: Project, activity_id: UUID | None) -> None:
    if activity_id is None:
        return
    node = await svc.get_node(session, project, activity_id)
    if node.level not in svc.ACTIVITY_LEVELS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Une ligne budgétaire se rattache à une activité ou une sous-activité",
        )


async def _get_line(session: SessionDep, project: Project, line_id: UUID) -> BudgetLine:
    line = await session.scalar(
        select(BudgetLine).where(BudgetLine.id == line_id, BudgetLine.project_id == project.id)
    )
    if line is None:
        raise svc.not_found("Ligne budgétaire")
    return line


@router.get("/{project_id}/budget/lines", response_model=list[BudgetLineOut])
async def list_budget_lines(
    org_id: UUID, project_id: UUID, _: AnyMember, session: SessionDep
) -> list[BudgetLineOut]:
    project = await svc.get_project(session, org_id, project_id)
    lines = await session.scalars(
        select(BudgetLine)
        .where(BudgetLine.project_id == project.id)
        .order_by(BudgetLine.donor_line_code, BudgetLine.created_at)
    )
    spent = await svc.spent_by_line(session, project.id)
    return [svc.budget_line_out(line, spent.get(line.id)) for line in lines]


@router.get("/{project_id}/budget/summary", response_model=BudgetSummary)
async def get_budget_summary(
    org_id: UUID, project_id: UUID, _: AnyMember, session: SessionDep
) -> BudgetSummary:
    project = await svc.get_project(session, org_id, project_id)
    return await svc.budget_summary(session, project)


@router.post(
    "/{project_id}/budget/lines",
    response_model=BudgetLineOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_budget_line(
    org_id: UUID, project_id: UUID, body: BudgetLineIn, member: FinanceEditor, session: SessionDep
) -> BudgetLineOut:
    project = await svc.get_project(session, org_id, project_id)
    await _check_activity(session, project, body.activity_id)
    line = BudgetLine(organization_id=org_id, project_id=project.id, **body.model_dump())
    session.add(line)
    await session.flush()
    _log(
        session,
        member,
        "budget.line_created",
        "budget_line",
        line.id,
        {"label": body.label, "planned": str(line.planned)},
    )
    await session.commit()
    return svc.budget_line_out(line, None)


@router.patch("/{project_id}/budget/lines/{line_id}", response_model=BudgetLineOut)
async def update_budget_line(
    org_id: UUID,
    project_id: UUID,
    line_id: UUID,
    body: BudgetLineUpdate,
    member: FinanceEditor,
    session: SessionDep,
) -> BudgetLineOut:
    project = await svc.get_project(session, org_id, project_id)
    line = await _get_line(session, project, line_id)
    changes = body.model_dump(exclude_unset=True)
    if "activity_id" in changes:
        await _check_activity(session, project, body.activity_id)
    for field, value in changes.items():
        if value is None and field != "activity_id":
            continue
        setattr(line, field, value)
    _log(
        session,
        member,
        "budget.line_updated",
        "budget_line",
        line.id,
        body.model_dump(mode="json", exclude_unset=True),
    )
    await session.commit()
    await session.refresh(line)
    spent = await svc.spent_by_line(session, project.id)
    return svc.budget_line_out(line, spent.get(line.id))


@router.delete("/{project_id}/budget/lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_budget_line(
    org_id: UUID, project_id: UUID, line_id: UUID, member: FinanceEditor, session: SessionDep
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    line = await _get_line(session, project, line_id)
    _log(session, member, "budget.line_deleted", "budget_line", line.id, {"label": line.label})
    await session.delete(line)
    await session.commit()


@router.get("/{project_id}/budget/lines/{line_id}/expenses", response_model=list[ExpenseOut])
async def list_expenses(
    org_id: UUID, project_id: UUID, line_id: UUID, _: AnyMember, session: SessionDep
) -> list[Expense]:
    project = await svc.get_project(session, org_id, project_id)
    line = await _get_line(session, project, line_id)
    rows = await session.scalars(
        select(Expense).where(Expense.budget_line_id == line.id).order_by(Expense.spent_on)
    )
    return list(rows)


@router.post(
    "/{project_id}/budget/lines/{line_id}/expenses",
    response_model=ExpenseOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_expense(
    org_id: UUID,
    project_id: UUID,
    line_id: UUID,
    body: ExpenseIn,
    member: FinanceEditor,
    session: SessionDep,
) -> Expense:
    project = await svc.get_project(session, org_id, project_id)
    line = await _get_line(session, project, line_id)
    expense = Expense(organization_id=org_id, budget_line_id=line.id, **body.model_dump())
    session.add(expense)
    await session.flush()
    _log(
        session,
        member,
        "budget.expense_recorded",
        "expense",
        expense.id,
        {"line": line.label, "amount": str(body.amount)},
    )
    await session.commit()
    return expense


@router.delete(
    "/{project_id}/budget/lines/{line_id}/expenses/{expense_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_expense(
    org_id: UUID,
    project_id: UUID,
    line_id: UUID,
    expense_id: UUID,
    member: FinanceEditor,
    session: SessionDep,
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    line = await _get_line(session, project, line_id)
    expense = await session.scalar(
        select(Expense).where(Expense.id == expense_id, Expense.budget_line_id == line.id)
    )
    if expense is None:
        raise svc.not_found("Dépense")
    _log(
        session,
        member,
        "budget.expense_deleted",
        "expense",
        expense.id,
        {"line": line.label, "amount": str(expense.amount)},
    )
    await session.delete(expense)
    await session.commit()


# --- Indicateurs -----------------------------------------------------------


async def _get_indicator(session: SessionDep, project: Project, indicator_id: UUID) -> Indicator:
    indicator = await session.scalar(
        select(Indicator)
        .where(Indicator.id == indicator_id, Indicator.project_id == project.id)
        .options(selectinload(Indicator.values))
    )
    if indicator is None:
        raise svc.not_found("Indicateur")
    return indicator


async def _check_owner(session: SessionDep, org_id: UUID, owner_id: UUID | None) -> None:
    if owner_id is None:
        return
    member = await session.scalar(
        select(Membership.id).where(
            Membership.organization_id == org_id, Membership.user_id == owner_id
        )
    )
    if member is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Le responsable doit être membre de l'organisation",
        )


@router.get("/{project_id}/indicators", response_model=list[IndicatorOut])
async def list_indicators(
    org_id: UUID, project_id: UUID, _: AnyMember, session: SessionDep
) -> list[IndicatorOut]:
    project = await svc.get_project(session, org_id, project_id)
    return [svc.indicator_out(i) for i in await svc.list_indicators(session, project.id)]


@router.post(
    "/{project_id}/indicators", response_model=IndicatorOut, status_code=status.HTTP_201_CREATED
)
async def create_indicator(
    org_id: UUID, project_id: UUID, body: IndicatorIn, member: Planner, session: SessionDep
) -> IndicatorOut:
    project = await svc.get_project(session, org_id, project_id)
    await svc.get_node(session, project, body.node_id)
    await _check_owner(session, org_id, body.owner_id)
    indicator = Indicator(organization_id=org_id, project_id=project.id, **body.model_dump())
    session.add(indicator)
    await session.flush()
    _log(session, member, "indicator.created", "indicator", indicator.id, {"name": body.name})
    await session.commit()
    return svc.indicator_out(await _get_indicator(session, project, indicator.id))


@router.patch("/{project_id}/indicators/{indicator_id}", response_model=IndicatorOut)
async def update_indicator(
    org_id: UUID,
    project_id: UUID,
    indicator_id: UUID,
    body: IndicatorUpdate,
    member: Planner,
    session: SessionDep,
) -> IndicatorOut:
    project = await svc.get_project(session, org_id, project_id)
    indicator = await _get_indicator(session, project, indicator_id)
    changes = body.model_dump(exclude_unset=True)
    nullable = {"baseline", "target", "owner_id"}
    if changes.get("node_id"):
        await svc.get_node(session, project, changes["node_id"])
    if "owner_id" in changes:
        await _check_owner(session, org_id, body.owner_id)
    for field, value in changes.items():
        if value is None and field not in nullable:
            continue
        setattr(indicator, field, value)
    _log(
        session,
        member,
        "indicator.updated",
        "indicator",
        indicator.id,
        body.model_dump(mode="json", exclude_unset=True),
    )
    await session.commit()
    session.expunge(indicator)
    return svc.indicator_out(await _get_indicator(session, project, indicator_id))


@router.delete("/{project_id}/indicators/{indicator_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_indicator(
    org_id: UUID, project_id: UUID, indicator_id: UUID, member: Planner, session: SessionDep
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    indicator = await _get_indicator(session, project, indicator_id)
    _log(session, member, "indicator.deleted", "indicator", indicator.id, {"name": indicator.name})
    await session.delete(indicator)
    await session.commit()


@router.get(
    "/{project_id}/indicators/{indicator_id}/values", response_model=list[IndicatorValueOut]
)
async def list_indicator_values(
    org_id: UUID, project_id: UUID, indicator_id: UUID, _: AnyMember, session: SessionDep
) -> list[IndicatorValue]:
    project = await svc.get_project(session, org_id, project_id)
    return list((await _get_indicator(session, project, indicator_id)).values)


@router.post(
    "/{project_id}/indicators/{indicator_id}/values",
    response_model=IndicatorValueOut,
    status_code=status.HTTP_201_CREATED,
)
async def record_indicator_value(
    org_id: UUID,
    project_id: UUID,
    indicator_id: UUID,
    body: IndicatorValueIn,
    member: Collector,
    session: SessionDep,
) -> IndicatorValue:
    project = await svc.get_project(session, org_id, project_id)
    indicator = await _get_indicator(session, project, indicator_id)
    unknown = set(body.disaggregation) - set(indicator.disaggregations)
    if unknown:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Désagrégations non prévues pour cet indicateur : {', '.join(sorted(unknown))}",
        )
    value = IndicatorValue(
        organization_id=org_id,
        indicator_id=indicator.id,
        recorded_by=member.user_id,
        **body.model_dump(),
    )
    session.add(value)
    await session.flush()
    _log(
        session,
        member,
        "indicator.value_recorded",
        "indicator_value",
        value.id,
        {"indicator": indicator.name, "value": str(body.value)},
    )
    await session.commit()
    return value


@router.delete(
    "/{project_id}/indicators/{indicator_id}/values/{value_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_indicator_value(
    org_id: UUID,
    project_id: UUID,
    indicator_id: UUID,
    value_id: UUID,
    member: Planner,
    session: SessionDep,
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    indicator = await _get_indicator(session, project, indicator_id)
    value = next((v for v in indicator.values if v.id == value_id), None)
    if value is None:
        raise svc.not_found("Valeur")
    _log(
        session,
        member,
        "indicator.value_deleted",
        "indicator_value",
        value.id,
        {"indicator": indicator.name, "value": str(value.value)},
    )
    await session.delete(value)
    await session.commit()
