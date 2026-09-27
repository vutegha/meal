"""Termes de référence : modèle de sections, contexte de rédaction, génération IA, rendu."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Text, cast, func, literal_column, select
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.documents.render import RenderedDocument, Section
from app.llm.client import LLMError
from app.llm.prompts import tor_generation as prompt
from app.models import (
    BudgetLine,
    DocumentPage,
    Indicator,
    Job,
    LogframeNode,
    Project,
    SourceDocument,
    TermsOfReference,
    TorStatus,
    TorVersion,
)
from app.schemas.tor import TorDraft
from app.services import audit
from app.services import projects as svc
from app.services.ai import call_structured

# Sections proposées par défaut. La section budget est calculée à partir du budget du projet,
# jamais rédigée par l'IA, pour que les montants des TdR restent ceux du budget.
DEFAULT_SECTIONS: list[tuple[str, str]] = [
    ("contexte", "Contexte et justification"),
    ("objectifs", "Objectifs de l'activité"),
    ("resultats", "Résultats attendus"),
    ("methodologie", "Méthodologie et déroulement"),
    ("participants", "Participants et critères de sélection"),
    ("lieu_calendrier", "Lieu, dates et calendrier"),
    ("budget", "Budget"),
    ("roles", "Rôles et responsabilités"),
    ("suivi", "Suivi, évaluation et indicateurs"),
    ("redevabilite", "Redevabilité envers les populations et protection"),
    ("risques", "Risques et mesures d'atténuation"),
    ("livrables", "Livrables"),
]
BUDGET_KEY = "budget"
TO_COMPLETE = "[À compléter]"
STATUS_LABELS = {
    TorStatus.DRAFT: "Brouillon",
    TorStatus.SUBMITTED: "Soumis pour validation",
    TorStatus.APPROVED: "Approuvé",
}
MAX_PASSAGES = 6
MAX_PASSAGE_CHARS = 3000


def blank_sections() -> list[dict[str, Any]]:
    return [{"key": key, "title": title, "content": ""} for key, title in DEFAULT_SECTIONS]


def fmt(value: Decimal | float, decimals: int = 2) -> str:
    """Nombre au format français : espace pour les milliers, virgule décimale."""
    text = f"{Decimal(str(value)):,.{decimals}f}".replace(",", " ").replace(".", ",")
    return text.removesuffix(",00") if decimals == 2 else text


async def get_tor(session: AsyncSession, project: Project, tor_id: UUID) -> TermsOfReference:
    tor = await session.scalar(
        select(TermsOfReference).where(
            TermsOfReference.id == tor_id, TermsOfReference.project_id == project.id
        )
    )
    if tor is None:
        raise svc.not_found("TdR")
    return tor


async def get_activity(session: AsyncSession, project: Project, node_id: UUID) -> LogframeNode:
    node = await svc.get_node(session, project, node_id)
    if node.level not in svc.ACTIVITY_LEVELS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Les TdR se rédigent pour une activité ou une sous-activité",
        )
    return node


def snapshot(session: AsyncSession, tor: TermsOfReference, user_id: UUID | None, note: str) -> None:
    session.add(
        TorVersion(
            organization_id=tor.organization_id,
            tor_id=tor.id,
            version=tor.version,
            title=tor.title,
            sections=tor.sections,
            note=note,
            created_by=user_id,
        )
    )


async def activity_lines(session: AsyncSession, activity: LogframeNode) -> list[BudgetLine]:
    """Lignes de l'activité et de ses sous-activités."""
    children = select(LogframeNode.id).where(LogframeNode.parent_id == activity.id)
    rows = await session.scalars(
        select(BudgetLine)
        .where((BudgetLine.activity_id == activity.id) | BudgetLine.activity_id.in_(children))
        .order_by(BudgetLine.donor_line_code, BudgetLine.created_at)
    )
    return list(rows)


def budget_markdown(lines: list[BudgetLine], currency: str) -> str:
    if not lines:
        return (
            "[À compléter : aucune ligne budgétaire n'est rattachée à cette activité dans le "
            "budget du projet.]"
        )
    rows = [
        f"| Ligne | Quantité | Coût unitaire ({currency}) | Fréquence | Montant ({currency}) |",
        "|---|---|---|---|---|",
    ]
    for line in lines:
        label = f"{line.donor_line_code} {line.label}".strip()
        if line.is_estimate:
            label += " (estimation)"
        quantity = f"{fmt(line.quantity)} {line.unit}".strip()
        rows.append(
            f"| {label} | {quantity} | {fmt(line.unit_cost)} | {fmt(line.frequency)} "
            f"| {fmt(line.planned)} |"
        )
    total = sum((line.planned for line in lines), Decimal(0))
    rows.append(f"| **Total** | | | | **{fmt(total)}** |")
    return "\n".join(rows)


async def relevant_passages(
    session: AsyncSession, project: Project, text: str
) -> list[tuple[str, int, str]]:
    """Pages des documents du projet qui partagent le plus de termes avec l'activité."""
    # plainto_tsquery exige tous les termes (&) ; on accepte n'importe lequel (|).
    words = cast(func.plainto_tsquery(literal_column("'french'"), text), Text)
    query = cast(func.replace(words, "&", "|"), TSQUERY)
    rank = func.ts_rank(DocumentPage.search, query)
    rows = await session.execute(
        select(SourceDocument.filename, DocumentPage.number, DocumentPage.text)
        .join(SourceDocument)
        .where(SourceDocument.project_id == project.id, DocumentPage.search.op("@@")(query))
        .order_by(rank.desc())
        .limit(MAX_PASSAGES)
    )
    return [(f, n, t[:MAX_PASSAGE_CHARS]) for f, n, t in rows]


async def build_context(
    session: AsyncSession, project: Project, activity: LogframeNode, instructions: str
) -> str:
    nodes = {node.id: node for node in await svc.list_nodes(session, project.id)}
    chain = [activity]
    while chain[0].parent_id and chain[0].parent_id in nodes:
        chain.insert(0, nodes[chain[0].parent_id])
    sub_activities = [n for n in nodes.values() if n.parent_id == activity.id]
    indicators = (
        await session.scalars(select(Indicator).where(Indicator.node_id.in_([n.id for n in chain])))
    ).all()
    lines = await activity_lines(session, activity)

    parts = [
        "<projet>",
        f"Titre : {project.title} ({project.code})",
        f"Bailleur : {project.donor or 'non précisé'}",
        f"Période : {project.start_date or '?'} au {project.end_date or '?'}",
        f"Zones : {', '.join(project.zones) or 'non précisées'}",
        f"Groupes cibles : {', '.join(project.target_groups) or 'non précisés'}",
        f"Langue : {project.language}",
        f"Description : {project.description or 'non fournie'}",
        "</projet>",
        "<cadre_logique>",
    ]
    for depth, node in enumerate(chain):
        marker = "  " * depth + "- "
        parts.append(f"{marker}{node.level.value} {node.code} : {node.title}")
        if node.assumptions:
            parts.append(f"{'  ' * depth}  Hypothèses : {node.assumptions}")
    for node in sub_activities:
        parts.append(f"{'  ' * len(chain)}- sub_activity {node.code} : {node.title}")
    parts.append("</cadre_logique>")
    parts.append("<indicateurs>")
    for indicator in indicators:
        target_node = nodes.get(indicator.node_id)
        parts.append(
            f"- {indicator.code} ({target_node.code if target_node else ''}) {indicator.name} : "
            f"référence {indicator.baseline if indicator.baseline is not None else 'inconnue'}, "
            f"cible {indicator.target if indicator.target is not None else 'inconnue'} "
            f"{indicator.unit} ; source : {indicator.source_of_verification or 'non précisée'}"
        )
    parts.append("</indicateurs>")
    parts.append(f"<budget devise='{project.currency}'>")
    parts.append(budget_markdown(lines, project.currency))
    parts.append("</budget>")
    passages = await relevant_passages(session, project, f"{activity.title} {activity.code}")
    for filename, page, text in passages:
        parts.append(f'<extrait document="{filename}" page="{page}">\n{text.strip()}\n</extrait>')
    if instructions.strip():
        parts.append(f"<consignes_utilisateur>\n{instructions.strip()}\n</consignes_utilisateur>")
    return "\n".join(parts)


def merge_sections(draft: TorDraft, budget: str) -> list[dict[str, Any]]:
    written = {section.key: section.content.strip() for section in draft.sections}
    return [
        {
            "key": key,
            "title": title,
            "content": budget if key == BUDGET_KEY else written.get(key) or TO_COMPLETE,
        }
        for key, title in DEFAULT_SECTIONS
    ]


async def run_tor_generation(session: AsyncSession, job: Job) -> dict[str, Any]:
    project = await session.get_one(Project, job.project_id)
    activity = await get_activity(session, project, UUID(job.params["activity_id"]))
    tor = await session.scalar(
        select(TermsOfReference).where(TermsOfReference.activity_id == activity.id)
    )
    if tor is not None and tor.status != TorStatus.DRAFT:
        raise LLMError("Ces TdR sont soumis ou approuvés : repassez-les en brouillon d'abord.")

    context = await build_context(session, project, activity, job.params.get("instructions", ""))
    wanted = [(key, title) for key, title in DEFAULT_SECTIONS if key != BUDGET_KEY]
    result = await call_structured(
        session,
        organization_id=project.organization_id,
        project_id=project.id,
        purpose="tor_generation",
        prompt_version=prompt.VERSION,
        model=get_settings().llm_model_drafting,
        system=prompt.SYSTEM,
        content=prompt.build_content(context, wanted),
        output_type=TorDraft,
        effort="medium",
    )
    draft = result.output
    sections = merge_sections(
        draft, budget_markdown(await activity_lines(session, activity), project.currency)
    )
    if tor is None:
        tor = TermsOfReference(
            organization_id=project.organization_id,
            project_id=project.id,
            activity_id=activity.id,
            created_by=job.created_by,
        )
        session.add(tor)
    else:
        tor.version += 1
    tor.title = draft.title[:300] or f"TdR : {activity.title}"[:300]
    tor.sections = sections
    tor.missing_information = draft.missing_information
    await session.flush()
    snapshot(session, tor, job.created_by, "Rédigé par l'IA")
    audit.record(
        session,
        organization_id=project.organization_id,
        actor_id=job.created_by,
        action="tor.generated",
        entity_type="tor",
        entity_id=tor.id,
        data={"title": tor.title, "version": tor.version},
    )
    await session.flush()
    return {"tor_id": str(tor.id), "missing_information": len(draft.missing_information)}


async def render_document(
    session: AsyncSession, project: Project, tor: TermsOfReference
) -> RenderedDocument:
    activity = await session.get_one(LogframeNode, tor.activity_id)
    parent = await session.get(LogframeNode, activity.parent_id) if activity.parent_id else None
    meta = [
        ("Projet", f"{project.title} ({project.code})"),
        ("Bailleur", project.donor or "–"),
        ("Activité", f"{activity.code} {activity.title}".strip()),
    ]
    if parent:
        meta.append(("Rattachée à", f"{parent.code} {parent.title}".strip()))
    meta.append(("Statut", f"{STATUS_LABELS[tor.status]}, version {tor.version}"))
    if tor.approved_at:
        meta.append(("Approuvé le", tor.approved_at.strftime("%d/%m/%Y")))
    return RenderedDocument(
        title=tor.title,
        subtitle="Termes de référence",
        meta=meta,
        sections=[Section(s["title"], s["content"]) for s in tor.sections],
    )
