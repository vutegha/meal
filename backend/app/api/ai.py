from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, UploadFile, status
from sqlalchemy import func, literal_column, select

from app.api.deps import AnyMember, OrgAdmin, SessionDep
from app.api.projects import Planner, _log
from app.core.config import get_settings
from app.documents.storage import get_storage
from app.models import (
    AiCall,
    AiProposal,
    DocumentPage,
    DocumentStatus,
    Job,
    ProposalStatus,
    SourceDocument,
)
from app.schemas.ai import (
    AiUsage,
    ApplyLogframeIn,
    DocumentOut,
    JobOut,
    ProposalOut,
    SearchHit,
)
from app.services import projects as svc
from app.services.ai import month_cost, month_start
from app.services.documents import ingest
from app.services.jobs import enqueue
from app.services.proposals import apply_logframe

router = APIRouter(prefix="/orgs/{org_id}", tags=["documents et IA"])
PROJECT = "/projects/{project_id}"


# --- Documents -------------------------------------------------------------


@router.get(f"{PROJECT}/documents", response_model=list[DocumentOut])
async def list_documents(
    org_id: UUID, project_id: UUID, _: AnyMember, session: SessionDep
) -> list[SourceDocument]:
    project = await svc.get_project(session, org_id, project_id)
    rows = await session.scalars(
        select(SourceDocument)
        .where(SourceDocument.project_id == project.id)
        .order_by(SourceDocument.created_at)
    )
    return list(rows)


@router.post(
    f"{PROJECT}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED
)
async def upload_document(
    org_id: UUID, project_id: UUID, file: UploadFile, member: Planner, session: SessionDep
) -> SourceDocument:
    project = await svc.get_project(session, org_id, project_id)
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    document = await ingest(
        session,
        project=project,
        filename=file.filename or "document",
        content_type=file.content_type,
        data=data,
        uploaded_by=member.user_id,
    )
    _log(
        session,
        member,
        "document.uploaded",
        "source_document",
        document.id,
        {"name": document.filename},
    )
    await session.commit()
    await session.refresh(document)
    return document


@router.delete(f"{PROJECT}/documents/{{document_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    org_id: UUID, project_id: UUID, document_id: UUID, member: Planner, session: SessionDep
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    document = await session.scalar(
        select(SourceDocument).where(
            SourceDocument.id == document_id, SourceDocument.project_id == project.id
        )
    )
    if document is None:
        raise svc.not_found("Document")
    _log(
        session,
        member,
        "document.deleted",
        "source_document",
        document.id,
        {"name": document.filename},
    )
    await session.delete(document)
    await session.commit()
    await get_storage().delete(document.storage_key)


@router.get(f"{PROJECT}/documents/search", response_model=list[SearchHit])
async def search_documents(
    org_id: UUID,
    project_id: UUID,
    _: AnyMember,
    session: SessionDep,
    q: str = Query(min_length=2, max_length=200),
) -> list[SearchHit]:
    project = await svc.get_project(session, org_id, project_id)
    query = func.websearch_to_tsquery(literal_column("'french'"), q)
    rank = func.ts_rank(DocumentPage.search, query)
    snippet = func.ts_headline(
        literal_column("'french'"),
        DocumentPage.text,
        query,
        "StartSel=«, StopSel=», MaxWords=30, MinWords=10",
    )
    rows = await session.execute(
        select(
            DocumentPage.document_id, SourceDocument.filename, DocumentPage.number, snippet, rank
        )
        .join(SourceDocument)
        .where(SourceDocument.project_id == project.id, DocumentPage.search.op("@@")(query))
        .order_by(rank.desc())
        .limit(20)
    )
    return [
        SearchHit(document_id=d, filename=f, page=p, snippet=s, rank=float(r))
        for d, f, p, s, r in rows
    ]


# --- Extraction et propositions ---------------------------------------------------


@router.post(
    f"{PROJECT}/ai/logframe-extraction", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED
)
async def start_logframe_extraction(
    org_id: UUID, project_id: UUID, member: Planner, session: SessionDep
) -> Job:
    project = await svc.get_project(session, org_id, project_id)
    ready = await session.scalar(
        select(func.count())
        .select_from(SourceDocument)
        .where(
            SourceDocument.project_id == project.id,
            SourceDocument.status == DocumentStatus.EXTRACTED,
        )
    )
    if not ready:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Importez d'abord au moins un document lisible"
        )
    job = Job(
        organization_id=org_id,
        project_id=project.id,
        kind="logframe_extraction",
        created_by=member.user_id,
    )
    session.add(job)
    await session.flush()
    _log(session, member, "ai.extraction_started", "job", job.id, {"title": project.title})
    await session.commit()
    await enqueue(job)
    await session.refresh(job)
    return job


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(org_id: UUID, job_id: UUID, _: AnyMember, session: SessionDep) -> Job:
    job = await session.scalar(select(Job).where(Job.id == job_id, Job.organization_id == org_id))
    if job is None:
        raise svc.not_found("Tâche")
    return job


async def _get_proposal(
    session: SessionDep, org_id: UUID, project_id: UUID, proposal_id: UUID
) -> AiProposal:
    project = await svc.get_project(session, org_id, project_id)
    proposal = await session.scalar(
        select(AiProposal).where(AiProposal.id == proposal_id, AiProposal.project_id == project.id)
    )
    if proposal is None:
        raise svc.not_found("Proposition")
    return proposal


@router.get(f"{PROJECT}/proposals", response_model=list[ProposalOut])
async def list_proposals(
    org_id: UUID, project_id: UUID, _: AnyMember, session: SessionDep
) -> list[AiProposal]:
    project = await svc.get_project(session, org_id, project_id)
    rows = await session.scalars(
        select(AiProposal)
        .where(AiProposal.project_id == project.id)
        .order_by(AiProposal.created_at.desc())
    )
    return list(rows)


@router.get(f"{PROJECT}/proposals/{{proposal_id}}", response_model=ProposalOut)
async def get_proposal(
    org_id: UUID, project_id: UUID, proposal_id: UUID, _: AnyMember, session: SessionDep
) -> AiProposal:
    return await _get_proposal(session, org_id, project_id, proposal_id)


def _ensure_pending(proposal: AiProposal) -> None:
    if proposal.status != ProposalStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Cette proposition a déjà été traitée")


@router.post(f"{PROJECT}/proposals/{{proposal_id}}/apply", response_model=ProposalOut)
async def apply_proposal(
    org_id: UUID,
    project_id: UUID,
    proposal_id: UUID,
    body: ApplyLogframeIn,
    member: Planner,
    session: SessionDep,
) -> AiProposal:
    proposal = await _get_proposal(session, org_id, project_id, proposal_id)
    _ensure_pending(proposal)
    project = await svc.get_project(session, org_id, project_id)
    counts = await apply_logframe(session, project, body)
    proposal.status = ProposalStatus.APPLIED
    proposal.reviewed_by = member.user_id
    proposal.reviewed_at = datetime.now(UTC)
    _log(session, member, "ai.proposal_applied", "ai_proposal", proposal.id, counts)
    await session.commit()
    await session.refresh(proposal)
    return proposal


@router.post(f"{PROJECT}/proposals/{{proposal_id}}/reject", response_model=ProposalOut)
async def reject_proposal(
    org_id: UUID, project_id: UUID, proposal_id: UUID, member: Planner, session: SessionDep
) -> AiProposal:
    proposal = await _get_proposal(session, org_id, project_id, proposal_id)
    _ensure_pending(proposal)
    proposal.status = ProposalStatus.REJECTED
    proposal.reviewed_by = member.user_id
    proposal.reviewed_at = datetime.now(UTC)
    _log(session, member, "ai.proposal_rejected", "ai_proposal", proposal.id)
    await session.commit()
    await session.refresh(proposal)
    return proposal


@router.get("/ai/usage", response_model=AiUsage)
async def ai_usage(org_id: UUID, _: OrgAdmin, session: SessionDep) -> AiUsage:
    calls = await session.scalar(
        select(func.count())
        .select_from(AiCall)
        .where(AiCall.organization_id == org_id, AiCall.created_at >= month_start())
    )
    cap = Decimal(str(get_settings().ai_monthly_budget_usd))
    return AiUsage(
        month_cost_usd=await month_cost(session, org_id),
        monthly_budget_usd=cap if cap > 0 else None,
        calls_this_month=calls or 0,
    )
