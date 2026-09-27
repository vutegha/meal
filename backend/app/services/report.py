"""Rapport narratif : sources, contexte de rédaction, génération IA, contrôle des renvois, rendu."""

import asyncio
import re
from decimal import Decimal
from io import BytesIO
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.documents.render import Figure, RenderedDocument, Section
from app.documents.storage import get_storage
from app.llm.client import LLMError
from app.llm.prompts import narrative_report as prompt
from app.models import (
    ActivityExecution,
    Evidence,
    EvidenceKind,
    Expense,
    Indicator,
    Job,
    LogframeNode,
    NarrativeReport,
    Project,
    ReportStatus,
    ReportVersion,
    TermsOfReference,
)
from app.schemas.execution import Participants
from app.schemas.report import ReportDraft
from app.services import audit, templates
from app.services import projects as svc
from app.services.ai import call_structured
from app.services.tor import TO_COMPLETE, activity_lines, fmt

REPORT_SECTIONS: list[tuple[str, str]] = [
    ("resume", "Résumé"),
    ("contexte", "Rappel du contexte et des objectifs"),
    ("deroulement", "Déroulement de l'activité"),
    ("participants", "Participants"),
    ("resultats", "Résultats obtenus : prévu et réalisé"),
    ("ecarts", "Écarts et explications"),
    ("budget", "Exécution budgétaire"),
    ("difficultes", "Difficultés rencontrées et solutions"),
    ("redevabilite", "Redevabilité : retours des participants et protection"),
    ("lecons", "Leçons apprises et recommandations"),
]
# Sections calculées à partir des données saisies, jamais rédigées par le modèle.
COMPUTED = {"participants", "budget"}
MAX_SOURCE_CHARS = 15_000
MAX_FIGURES = 12
STATUS_LABELS = {
    ReportStatus.DRAFT: "Brouillon",
    ReportStatus.SUBMITTED: "Soumis pour validation",
    ReportStatus.APPROVED: "Approuvé",
}
_REF = re.compile(r"\[([SP]\d+)\]")


async def get_execution(
    session: AsyncSession, project: Project, execution_id: UUID
) -> ActivityExecution:
    execution = await session.scalar(
        select(ActivityExecution)
        .where(ActivityExecution.id == execution_id, ActivityExecution.project_id == project.id)
        .options(selectinload(ActivityExecution.evidence))
    )
    if execution is None:
        raise svc.not_found("Exécution")
    return execution


async def get_report(session: AsyncSession, project: Project, report_id: UUID) -> NarrativeReport:
    report = await session.scalar(
        select(NarrativeReport).where(
            NarrativeReport.id == report_id, NarrativeReport.project_id == project.id
        )
    )
    if report is None:
        raise svc.not_found("Rapport")
    return report


def snapshot(
    session: AsyncSession, report: NarrativeReport, user_id: UUID | None, note: str
) -> None:
    session.add(
        ReportVersion(
            organization_id=report.organization_id,
            report_id=report.id,
            version=report.version,
            title=report.title,
            sections=report.sections,
            note=note,
            created_by=user_id,
        )
    )


def reportable_photos(execution: ActivityExecution) -> list[Evidence]:
    """Photos reprises dans le rapport : seulement celles dont le consentement est acquis."""
    return [
        e
        for e in execution.evidence
        if e.kind == EvidenceKind.PHOTO and e.consent_given and e.thumbnail_key
    ][:MAX_FIGURES]


def participants_markdown(execution: ActivityExecution) -> str:
    p = Participants.model_validate(execution.participants)
    if p.total == 0:
        return "[À compléter : aucun participant n'a été saisi pour cette exécution.]"
    table = "\n".join(
        [
            "| Femmes | Hommes | Filles | Garçons | Total |",
            "|---|---|---|---|---|",
            f"| {p.women} | {p.men} | {p.girls} | {p.boys} | **{p.total}** |",
        ]
    )
    if p.with_disability:
        table += f"\n\nDont {p.with_disability} personne(s) en situation de handicap."
    return table


async def budget_markdown(
    session: AsyncSession, project: Project, execution: ActivityExecution
) -> str:
    activity = await session.get_one(LogframeNode, execution.activity_id)
    lines = await activity_lines(session, activity)
    if not lines:
        return "[À compléter : aucune ligne budgétaire n'est rattachée à cette activité.]"
    ids = [line.id for line in lines]
    here = dict(
        (
            await session.execute(
                select(Expense.budget_line_id, func.sum(Expense.amount))
                .where(Expense.execution_id == execution.id, Expense.budget_line_id.in_(ids))
                .group_by(Expense.budget_line_id)
            )
        ).all()
    )
    total_spent = dict(
        (
            await session.execute(
                select(Expense.budget_line_id, func.sum(Expense.amount))
                .where(Expense.budget_line_id.in_(ids))
                .group_by(Expense.budget_line_id)
            )
        ).all()
    )
    c = project.currency
    rows = [
        f"| Ligne | Prévu ({c}) | Dépensé pour cette exécution ({c}) | Dépensé cumulé ({c}) "
        "| Exécution cumulée |",
        "|---|---|---|---|---|",
    ]
    for line in lines:
        spent = total_spent.get(line.id, Decimal(0))
        rate = f"{fmt(spent / line.planned * 100, 0)} %" if line.planned else "–"
        rows.append(
            f"| {line.donor_line_code} {line.label} | {fmt(line.planned)} "
            f"| {fmt(here.get(line.id, Decimal(0)))} | {fmt(spent)} | {rate} |"
        )
    table = "\n".join(rows)
    if not here:
        table += "\n\n[À compléter : aucune dépense réelle n'a été saisie pour cette exécution.]"
    return table


async def build_sources(
    session: AsyncSession, execution: ActivityExecution
) -> tuple[list[dict[str, Any]], list[str]]:
    """Sources numérotées (S pour les textes, P pour les photos) et leur texte pour le modèle."""
    sources: list[dict[str, Any]] = []
    blocks: list[str] = []
    p = Participants.model_validate(execution.participants)
    period = str(execution.start_date)
    if execution.end_date and execution.end_date != execution.start_date:
        period += f" au {execution.end_date}"
    field_notes = "\n".join(
        [
            f"Intitulé : {execution.title or 'non précisé'}",
            f"Dates : {period}",
            f"Lieu : {execution.location or 'non précisé'}",
            f"État : {'réalisée' if execution.status == 'completed' else 'en cours'}",
            f"Participants : {p.women} femmes, {p.men} hommes, {p.girls} filles, {p.boys} garçons "
            f"(total {p.total}, dont {p.with_disability} en situation de handicap)",
            f"Notes de l'équipe : {execution.notes or 'aucune'}",
        ]
    )
    sources.append({"ref": "S1", "label": "Saisie de l'exécution et notes de terrain"})
    blocks.append(f'<source ref="S1">\n{field_notes}\n</source>')

    tor = await session.scalar(
        select(TermsOfReference).where(TermsOfReference.activity_id == execution.activity_id)
    )
    if tor is not None:
        ref = f"S{len(sources) + 1}"
        sources.append({"ref": ref, "label": f"TdR de l'activité (version {tor.version})"})
        body = "\n\n".join(f"## {s['title']}\n{s['content']}" for s in tor.sections)
        blocks.append(f'<source ref="{ref}" type="tdr">\n{body[:MAX_SOURCE_CHARS]}\n</source>')

    for evidence in execution.evidence:
        if evidence.kind == EvidenceKind.PHOTO or not evidence.text.strip():
            continue
        ref = f"S{len(sources) + 1}"
        label = f"{evidence.filename}"
        sources.append({"ref": ref, "label": label, "evidence_id": str(evidence.id)})
        text = evidence.text.strip()
        if len(text) > MAX_SOURCE_CHARS:
            text = text[:MAX_SOURCE_CHARS] + "\n[… document tronqué]"
        blocks.append(
            f'<source ref="{ref}" type="{evidence.kind.value}" fichier="{evidence.filename}">'
            f"\n{text}\n</source>"
        )

    for index, photo in enumerate(reportable_photos(execution), start=1):
        ref = f"P{index}"
        caption = photo.caption or "sans légende"
        sources.append({"ref": ref, "label": f"Photo : {caption}", "evidence_id": str(photo.id)})
        taken = f", prise le {photo.taken_at:%d/%m/%Y}" if photo.taken_at else ""
        blocks.append(f'<source ref="{ref}" type="photo">Légende : {caption}{taken}</source>')
    return sources, blocks


async def build_context(
    session: AsyncSession, project: Project, execution: ActivityExecution, blocks: list[str]
) -> str:
    nodes = {n.id: n for n in await svc.list_nodes(session, project.id)}
    chain = [nodes[execution.activity_id]]
    while chain[0].parent_id and chain[0].parent_id in nodes:
        chain.insert(0, nodes[chain[0].parent_id])
    indicators = (
        await session.scalars(select(Indicator).where(Indicator.node_id.in_([n.id for n in chain])))
    ).all()
    parts = [
        "<projet>",
        f"Titre : {project.title} ({project.code}) ; bailleur : {project.donor or 'non précisé'}",
        f"Langue : {project.language}",
        "</projet>",
        "<cadre_logique>",
        *[f"{'  ' * d}- {n.level.value} {n.code} : {n.title}" for d, n in enumerate(chain)],
        "</cadre_logique>",
        "<indicateurs>",
        *[
            f"- code {i.code} ({nodes[i.node_id].code}) : {i.name} ; unité {i.unit or '?'} ; "
            f"cible {i.target if i.target is not None else 'inconnue'} ; "
            f"calcul {'somme des valeurs' if i.aggregation == 'sum' else 'dernière valeur'}"
            for i in indicators
        ],
        "</indicateurs>",
        "<sources>",
        *blocks,
        "</sources>",
    ]
    return "\n".join(parts)


def check_refs(content: str, known: set[str]) -> str:
    """Signale les renvois vers des sources inconnues, pour que le relecteur les voie."""
    return _REF.sub(lambda m: m[0] if m[1] in known else "[source introuvable]", content)


async def run_report_generation(session: AsyncSession, job: Job) -> dict[str, Any]:
    project = await session.get_one(Project, job.project_id)
    execution = await get_execution(session, project, UUID(job.params["execution_id"]))
    report = await session.scalar(
        select(NarrativeReport).where(NarrativeReport.execution_id == execution.id)
    )
    if report is not None and report.status != ReportStatus.DRAFT:
        raise LLMError("Ce rapport est soumis ou approuvé : repassez-le en brouillon d'abord.")

    sources, blocks = await build_sources(session, execution)
    context = await build_context(session, project, execution, blocks)
    plan = await templates.resolve(
        session, project, "report", REPORT_SECTIONS, report.template_id if report else None
    )
    result = await call_structured(
        session,
        organization_id=project.organization_id,
        project_id=project.id,
        purpose="report_generation",
        prompt_version=prompt.VERSION,
        model=get_settings().llm_model_drafting,
        system=prompt.SYSTEM,
        content=prompt.build_content(context, templates.wanted(plan, COMPUTED)),
        output_type=ReportDraft,
        effort="medium",
    )
    draft = result.output
    known = {s["ref"] for s in sources}
    written = {s.key: check_refs(s.content.strip(), known) for s in draft.sections}
    computed = {
        "participants": participants_markdown(execution),
        "budget": await budget_markdown(session, project, execution),
    }
    sections = templates.assemble(plan, {**written, **computed}, TO_COMPLETE)

    indicators = {
        i.code: i
        for i in await session.scalars(select(Indicator).where(Indicator.project_id == project.id))
        if i.code
    }
    suggestions = [
        {
            "indicator_id": str(indicators[s.indicator_code].id),
            "code": s.indicator_code,
            "name": indicators[s.indicator_code].name,
            "unit": indicators[s.indicator_code].unit,
            "value": str(Decimal(str(s.value))),
            "justification": s.justification,
            "source_ref": s.source_ref if s.source_ref in known else "",
            "applied_value_id": None,
        }
        for s in draft.indicator_suggestions
        if s.indicator_code in indicators and s.value >= 0
    ]

    if report is None:
        report = NarrativeReport(
            organization_id=project.organization_id,
            project_id=project.id,
            execution_id=execution.id,
            created_by=job.created_by,
        )
        session.add(report)
    else:
        report.version += 1
    report.title = (draft.title or f"Rapport : {execution.title}")[:300]
    report.sections = sections
    report.template_id = plan.template_id
    report.sources = sources
    report.missing_information = draft.missing_information
    report.indicator_suggestions = suggestions
    await session.flush()
    snapshot(session, report, job.created_by, "Rédigé par l'IA")
    audit.record(
        session,
        organization_id=project.organization_id,
        actor_id=job.created_by,
        action="report.generated",
        entity_type="narrative_report",
        entity_id=report.id,
        data={"title": report.title, "version": report.version},
    )
    await session.flush()
    return {"report_id": str(report.id), "missing_information": len(draft.missing_information)}


def _to_jpeg(data: bytes) -> bytes:
    from PIL import Image

    image = Image.open(BytesIO(data)).convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()


async def render_document(
    session: AsyncSession, project: Project, report: NarrativeReport
) -> RenderedDocument:
    execution = await get_execution(session, project, report.execution_id)
    activity = await session.get_one(LogframeNode, execution.activity_id)
    period = execution.start_date.strftime("%d/%m/%Y")
    if execution.end_date and execution.end_date != execution.start_date:
        period += f" au {execution.end_date:%d/%m/%Y}"
    meta = [
        ("Projet", f"{project.title} ({project.code})"),
        ("Bailleur", project.donor or "–"),
        ("Activité", f"{activity.code} {activity.title}".strip()),
        ("Dates et lieu", f"{period}{', ' + execution.location if execution.location else ''}"),
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
    storage = get_storage()
    figures = []
    for index, photo in enumerate(reportable_photos(execution), start=1):
        data = await asyncio.to_thread(_to_jpeg, await storage.get(photo.thumbnail_key))
        figures.append(Figure(data, f"P{index} : {photo.caption or photo.filename}"))
    return RenderedDocument(
        title=report.title,
        subtitle="Rapport narratif d'activité",
        meta=meta,
        sections=sections,
        figures=figures,
    )
