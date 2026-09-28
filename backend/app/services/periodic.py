"""Rapports périodiques et bailleur : agrégation des rapports d'activité, des indicateurs, du
budget, des retours communautaires et des leçons apprises sur une période."""

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date

from app.core.config import get_settings
from app.documents.render import RenderedDocument, Section
from app.llm.client import LLMError
from app.llm.prompts import periodic_report as prompt
from app.models import (
    ActivityExecution,
    BudgetLine,
    Expense,
    FeedbackEntry,
    Job,
    Lesson,
    LogframeNode,
    NarrativeReport,
    PeriodicKind,
    PeriodicReport,
    PeriodicReportVersion,
    Project,
    ReportStatus,
)
from app.schemas.accountability import PeriodicDraft
from app.schemas.execution import Participants
from app.schemas.project import NodeTree
from app.services import audit, templates
from app.services import feedback as fb
from app.services import projects as svc
from app.services.ai import call_structured
from app.services.report import COMPUTED as REPORT_COMPUTED
from app.services.report import STATUS_LABELS, check_refs
from app.services.tor import TO_COMPLETE, fmt

PERIODIC_SECTIONS: list[tuple[str, str]] = [
    ("resume", "Résumé"),
    ("contexte", "Contexte et évolution de la situation"),
    ("progres", "Progrès vers les résultats"),
    ("activites", "Activités réalisées sur la période"),
    ("indicateurs", "Suivi des indicateurs"),
    ("budget", "Exécution budgétaire"),
    ("redevabilite", "Redevabilité : plaintes et retours"),
    ("difficultes", "Difficultés rencontrées et mesures prises"),
    ("lecons", "Leçons apprises"),
    ("perspectives", "Perspectives pour la période suivante"),
]
COMPUTED = {"activites", "indicateurs", "budget"}
KIND_LABELS = {
    PeriodicKind.MONTHLY: "Rapport mensuel",
    PeriodicKind.QUARTERLY: "Rapport trimestriel",
    PeriodicKind.ANNUAL: "Rapport annuel",
    PeriodicKind.DONOR: "Rapport au bailleur",
}
MAX_SOURCE_CHARS = 8_000
FEEDBACK_LABELS = {
    "information": "demande d'information",
    "suggestion": "suggestion",
    "appreciation": "appréciation",
    "complaint": "plainte",
    "fraud": "fraude",
    "sexual_exploitation": "exploitation et abus sexuels",
    "safety": "sécurité",
    "other": "autre",
}


def day(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def default_title(kind: PeriodicKind, start: date, end: date) -> str:
    return f"{KIND_LABELS[kind]} du {day(start)} au {day(end)}"


async def get_periodic(session: AsyncSession, project: Project, report_id: UUID) -> PeriodicReport:
    report = await session.scalar(
        select(PeriodicReport).where(
            PeriodicReport.id == report_id, PeriodicReport.project_id == project.id
        )
    )
    if report is None:
        raise svc.not_found("Rapport")
    return report


def snapshot(
    session: AsyncSession, report: PeriodicReport, user_id: UUID | None, note: str
) -> None:
    session.add(
        PeriodicReportVersion(
            organization_id=report.organization_id,
            report_id=report.id,
            version=report.version,
            title=report.title,
            sections=report.sections,
            note=note,
            created_by=user_id,
        )
    )


# --- Données de la période ------------------------------------------------------------


async def executions_in(
    session: AsyncSession, project: Project, start: date, end: date
) -> list[ActivityExecution]:
    """Exécutions qui chevauchent la période."""
    rows = await session.scalars(
        select(ActivityExecution)
        .where(
            ActivityExecution.project_id == project.id,
            ActivityExecution.start_date <= end,
            func.coalesce(ActivityExecution.end_date, ActivityExecution.start_date) >= start,
        )
        .order_by(ActivityExecution.start_date, ActivityExecution.created_at)
    )
    return list(rows)


def activities_markdown(
    executions: list[ActivityExecution],
    nodes: dict[UUID, LogframeNode],
    reports: dict[UUID, NarrativeReport],
) -> str:
    if not executions:
        return "[À compléter : aucune exécution d'activité n'a été saisie sur cette période.]"
    rows = [
        "| Dates | Activité | Lieu | Femmes | Hommes | Enfants | Total | Rapport |",
        "|---|---|---|---|---|---|---|---|",
    ]
    total = Counter[str]()
    for execution in executions:
        p = Participants.model_validate(execution.participants)
        total.update(women=p.women, men=p.men, children=p.girls + p.boys, all=p.total)
        dates = day(execution.start_date)
        if execution.end_date and execution.end_date != execution.start_date:
            dates += f" – {day(execution.end_date)}"
        activity = nodes.get(execution.activity_id)
        label = f"{activity.code} {execution.title or activity.title}" if activity else "?"
        report = reports.get(execution.id)
        rows.append(
            f"| {dates} | {label.strip()} | {execution.location or '–'} | {p.women} | {p.men} "
            f"| {p.girls + p.boys} | {p.total} "
            f"| {STATUS_LABELS[report.status] if report else 'aucun'} |"
        )
    rows.append(
        f"| **Total** | {len(executions)} exécution(s) | | {total['women']} | {total['men']} "
        f"| {total['children']} | **{total['all']}** | |"
    )
    return "\n".join(rows)


async def indicators_markdown(
    session: AsyncSession, project: Project, start: date, end: date
) -> str:
    indicators = await svc.list_indicators(session, project.id)
    if not indicators:
        return "[À compléter : aucun indicateur n'est défini pour ce projet.]"
    rows = [
        "| Code | Indicateur | Référence | Cible | Sur la période | Cumul | Atteinte |",
        "|---|---|---|---|---|---|---|",
    ]

    def show(value: Decimal | None) -> str:
        return fmt(value) if value is not None else "–"

    for indicator in indicators:
        in_period = [v for v in indicator.values if start <= v.period_end <= end]
        to_date = [v for v in indicator.values if v.period_end <= end]
        period_value, _ = svc.achievement(indicator, in_period)
        cumul, rate = svc.achievement(indicator, to_date)
        percent = f"{fmt(Decimal(str(rate)) * 100, 0)} %" if rate is not None else "–"
        rows.append(
            f"| {indicator.code or '–'} | {indicator.name} ({indicator.unit or 'unité ?'}) "
            f"| {show(indicator.baseline)} | {show(indicator.target)} | {show(period_value)} "
            f"| {show(cumul)} | {percent} |"
        )
    return "\n".join(rows)


async def budget_markdown(session: AsyncSession, project: Project, start: date, end: date) -> str:
    lines = list(
        await session.scalars(select(BudgetLine).where(BudgetLine.project_id == project.id))
    )
    if not lines:
        return "[À compléter : aucun budget n'est saisi pour ce projet.]"
    nodes = {n.id: n for n in await svc.list_nodes(session, project.id)}
    spent = await session.execute(
        select(
            Expense.budget_line_id,
            func.sum(Expense.amount).filter(Expense.spent_on >= start),
            func.sum(Expense.amount),
        )
        .where(Expense.budget_line_id.in_([line.id for line in lines]), Expense.spent_on <= end)
        .group_by(Expense.budget_line_id)
    )
    by_line = {
        line_id: (period or Decimal(0), cumul or Decimal(0)) for line_id, period, cumul in spent
    }
    planned: dict[UUID | None, Decimal] = defaultdict(Decimal)
    period_spent: dict[UUID | None, Decimal] = defaultdict(Decimal)
    cumul_spent: dict[UUID | None, Decimal] = defaultdict(Decimal)
    for line in lines:
        planned[line.activity_id] += line.planned
        in_period, cumul = by_line.get(line.id, (Decimal(0), Decimal(0)))
        period_spent[line.activity_id] += in_period
        cumul_spent[line.activity_id] += cumul

    def pct(done: Decimal, total: Decimal) -> str:
        return f"{fmt(done / total * 100, 0)} %" if total else "–"

    c = project.currency
    rows = [
        f"| Poste | Prévu ({c}) | Dépensé sur la période ({c}) | Dépensé cumulé ({c}) "
        "| Exécution |",
        "|---|---|---|---|---|",
    ]
    order = sorted(planned, key=lambda a: (a is None, nodes[a].code if a in nodes else ""))
    for activity_id in order:
        node = nodes.get(activity_id) if activity_id else None
        label = f"{node.code} {node.title}" if node else "Coûts de support"
        rows.append(
            f"| {label} | {fmt(planned[activity_id])} | {fmt(period_spent[activity_id])} "
            f"| {fmt(cumul_spent[activity_id])} "
            f"| {pct(cumul_spent[activity_id], planned[activity_id])} |"
        )
    total_planned = sum(planned.values(), Decimal(0))
    total_period = sum(period_spent.values(), Decimal(0))
    total_cumul = sum(cumul_spent.values(), Decimal(0))
    rows.append(
        f"| **Total** | **{fmt(total_planned)}** | **{fmt(total_period)}** "
        f"| **{fmt(total_cumul)}** | **{pct(total_cumul, total_planned)}** |"
    )
    return "\n".join(rows)


async def computed_sections(
    session: AsyncSession, project: Project, start: date, end: date
) -> dict[str, str]:
    executions = await executions_in(session, project, start, end)
    nodes = {n.id: n for n in await svc.list_nodes(session, project.id)}
    reports = await reports_for(session, executions)
    return {
        "activites": activities_markdown(executions, nodes, reports),
        "indicateurs": await indicators_markdown(session, project, start, end),
        "budget": await budget_markdown(session, project, start, end),
    }


async def reports_for(
    session: AsyncSession, executions: list[ActivityExecution]
) -> dict[UUID, NarrativeReport]:
    if not executions:
        return {}
    rows = await session.scalars(
        select(NarrativeReport).where(NarrativeReport.execution_id.in_([e.id for e in executions]))
    )
    return {r.execution_id: r for r in rows}


# --- Sources pour la rédaction -------------------------------------------------------------


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= MAX_SOURCE_CHARS else text[:MAX_SOURCE_CHARS] + "\n[… tronqué]"


async def build_sources(
    session: AsyncSession, project: Project, start: date, end: date
) -> tuple[list[dict[str, Any]], list[str]]:
    sources: list[dict[str, Any]] = []
    blocks: list[str] = []

    def add(label: str, kind: str, text: str) -> None:
        ref = f"S{len(sources) + 1}"
        sources.append({"ref": ref, "label": label})
        blocks.append(f'<source ref="{ref}" type="{kind}">\n{_clip(text)}\n</source>')

    executions = await executions_in(session, project, start, end)
    nodes = {n.id: n for n in await svc.list_nodes(session, project.id)}
    reports = await reports_for(session, executions)
    for execution in executions:
        activity = nodes.get(execution.activity_id)
        name = f"{activity.code} " if activity else ""
        name += execution.title or (activity.title if activity else "")
        report = reports.get(execution.id)
        if report is not None:
            body = "\n\n".join(
                f"## {s['title']}\n{s['content']}"
                for s in report.sections
                if s["key"] not in REPORT_COMPUTED
            )
            add(
                f"Rapport d'activité : {name} ({STATUS_LABELS[report.status].lower()})",
                "rapport_activite",
                f"Activité : {name}, {day(execution.start_date)}, {execution.location}\n{body}",
            )
        else:
            p = Participants.model_validate(execution.participants)
            add(
                f"Saisie de l'exécution : {name} (sans rapport)",
                "execution",
                f"Activité : {name}\nDates : {day(execution.start_date)}\n"
                f"Lieu : {execution.location or 'non précisé'}\n"
                f"Participants : {p.total} ({p.women} femmes, {p.men} hommes)\n"
                f"Notes : {execution.notes or 'aucune'}",
            )

    entries = list(
        await session.scalars(
            select(FeedbackEntry)
            .where(
                FeedbackEntry.project_id == project.id,
                FeedbackEntry.received_on >= start,
                FeedbackEntry.received_on <= end,
            )
            .order_by(FeedbackEntry.received_on)
        )
    )
    if entries:
        stats = fb.stats(entries, hidden=0, today=end)
        lines = [
            f"Retours reçus sur la période : {stats.total}",
            "Par type : "
            + ", ".join(f"{FEEDBACK_LABELS[k]} {v}" for k, v in stats.by_category.items()),
            f"Répondus ou clos : {stats.total - stats.open} ; en attente : {stats.open} ; "
            f"hors délai à la fin de la période : {stats.overdue}",
            "Délai moyen de réponse : "
            + (f"{stats.average_response_days} jours" if stats.average_response_days else "–"),
        ]
        sensitive = sum(1 for e in entries if e.sensitive)
        if sensitive:
            lines.append(
                f"Dont {sensitive} retour(s) sensible(s), traités de façon confidentielle."
            )
        for e in entries:
            if e.sensitive:
                continue
            line = f"- {e.reference} ({FEEDBACK_LABELS[e.category.value]}, {day(e.received_on)}) : "
            line += e.description[:300]
            if e.response:
                line += f" → Réponse : {e.response[:300]}"
            lines.append(line)
        add("Registre des plaintes et retours", "retours", "\n".join(lines))

    lessons = list(
        await session.scalars(
            select(Lesson)
            .where(
                Lesson.project_id == project.id,
                cast(Lesson.created_at, Date) >= start,
                cast(Lesson.created_at, Date) <= end,
            )
            .order_by(Lesson.created_at)
        )
    )
    if lessons:
        add(
            "Leçons apprises enregistrées",
            "lecons",
            "\n".join(
                f"- {x.title} : {x.description} Recommandation : {x.recommendation}".strip()
                for x in lessons
            ),
        )
    return sources, blocks


async def build_context(
    session: AsyncSession,
    project: Project,
    report: PeriodicReport,
    computed: dict[str, str],
    blocks: list[str],
) -> str:
    tree_lines: list[str] = []

    def walk(items: list[NodeTree], depth: int) -> None:
        for item in items:
            tree_lines.append(f"{'  ' * depth}- {item.level.value} {item.code} : {item.title}")
            walk(item.children, depth + 1)

    walk(svc.build_tree(await svc.list_nodes(session, project.id)), 0)
    return "\n".join(
        [
            "<projet>",
            f"Titre : {project.title} ({project.code}) ; "
            f"bailleur : {project.donor or 'non précisé'}",
            f"Langue : {project.language} ; devise : {project.currency}",
            f"Période du rapport : {day(report.period_start)} au {day(report.period_end)} "
            f"({KIND_LABELS[report.kind].lower()})",
            "</projet>",
            "<cadre_logique>",
            *tree_lines,
            "</cadre_logique>",
            "<tableaux_calcules>",
            *[f"## {key}\n{content}" for key, content in computed.items()],
            "</tableaux_calcules>",
            "<sources>",
            *blocks,
            "</sources>",
        ]
    )


async def run_periodic_generation(session: AsyncSession, job: Job) -> dict[str, Any]:
    project = await session.get_one(Project, job.project_id)
    report = await get_periodic(session, project, UUID(job.params["report_id"]))
    if report.status != ReportStatus.DRAFT:
        raise LLMError("Ce rapport est soumis ou approuvé : repassez-le en brouillon d'abord.")
    start, end = report.period_start, report.period_end
    computed = await computed_sections(session, project, start, end)
    sources, blocks = await build_sources(session, project, start, end)
    context = await build_context(session, project, report, computed, blocks)
    plan = await templates.resolve(
        session, project, "periodic", PERIODIC_SECTIONS, report.template_id
    )
    result = await call_structured(
        session,
        organization_id=project.organization_id,
        project_id=project.id,
        purpose="periodic_generation",
        prompt_version=prompt.VERSION,
        model=get_settings().llm_model_drafting,
        system=prompt.SYSTEM,
        content=prompt.build_content(
            context, templates.wanted(plan, COMPUTED), report.instructions
        ),
        output_type=PeriodicDraft,
        effort="medium",
    )
    draft = result.output
    known = {s["ref"] for s in sources}
    written = {s.key: check_refs(s.content.strip(), known) for s in draft.sections}
    report.sections = templates.assemble(plan, {**written, **computed}, TO_COMPLETE)
    report.template_id = plan.template_id
    report.sources = sources
    report.missing_information = draft.missing_information
    if draft.title.strip():
        report.title = draft.title.strip()[:300]
    report.version += 1
    snapshot(session, report, job.created_by, "Rédigé par l'IA")
    audit.record(
        session,
        organization_id=project.organization_id,
        actor_id=job.created_by,
        action="periodic.generated",
        entity_type="periodic_report",
        entity_id=report.id,
        data={"title": report.title, "version": report.version},
    )
    await session.flush()
    return {"report_id": str(report.id), "missing_information": len(draft.missing_information)}


def render_document(project: Project, report: PeriodicReport) -> RenderedDocument:
    meta = [
        ("Projet", f"{project.title} ({project.code})"),
        ("Bailleur", project.donor or "–"),
        ("Période", f"du {day(report.period_start)} au {day(report.period_end)}"),
        ("Statut", f"{STATUS_LABELS[report.status]}, version {report.version}"),
    ]
    if report.approved_at:
        meta.append(("Approuvé le", report.approved_at.strftime("%d/%m/%Y")))
    sections = [Section(s["title"], s["content"]) for s in report.sections]
    if report.sources:
        sections.append(
            Section(
                "Sources", "\n".join(f"- **{s['ref']}** : {s['label']}" for s in report.sources)
            )
        )
    return RenderedDocument(
        title=report.title, subtitle=KIND_LABELS[report.kind], meta=meta, sections=sections
    )
