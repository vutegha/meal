"""Formulaires de collecte personnalisés : conception, réponses terrain, synthèse, export.

Les réponses acceptent un `client_uuid` : une réponse saisie hors ligne et renvoyée après une
coupure réseau n'est enregistrée qu'une fois.
"""

import asyncio
from io import BytesIO
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from openpyxl import Workbook
from sqlalchemy import func, select

from app.api.deps import AnyMember, SessionDep
from app.api.projects import Collector, Planner, ProjectAdmin, _log
from app.models import CollectionForm, FormSubmission, Project, User
from app.schemas.form import (
    FormField,
    FormIn,
    FormOut,
    FormSummary,
    FormUpdate,
    SubmissionIn,
    SubmissionOut,
)
from app.services import forms as forms_svc
from app.services import projects as svc
from app.services.export import _sheet, _wrap

router = APIRouter(prefix="/orgs/{org_id}/projects/{project_id}/forms", tags=["formulaires"])


async def _get(session: SessionDep, project: Project, form_id: UUID) -> CollectionForm:
    form = await session.scalar(
        select(CollectionForm).where(
            CollectionForm.id == form_id, CollectionForm.project_id == project.id
        )
    )
    if form is None:
        raise svc.not_found("Formulaire")
    return form


async def _count(session: SessionDep, form: CollectionForm) -> int:
    return (
        await session.scalar(select(func.count()).where(FormSubmission.form_id == form.id))
    ) or 0


def _out(form: CollectionForm, submissions: int) -> FormOut:
    return FormOut.model_validate(form).model_copy(update={"submissions": submissions})


def _fields(form: CollectionForm) -> list[FormField]:
    return [FormField.model_validate(f) for f in form.fields]


async def _check_activity(session: SessionDep, project: Project, activity_id: UUID | None) -> None:
    if activity_id:
        await svc.get_node(session, project, activity_id)


@router.get("", response_model=list[FormOut])
async def list_forms(
    org_id: UUID, project_id: UUID, _: AnyMember, session: SessionDep
) -> list[FormOut]:
    project = await svc.get_project(session, org_id, project_id)
    counts = {
        form_id: count
        for form_id, count in await session.execute(
            select(FormSubmission.form_id, func.count())
            .where(FormSubmission.project_id == project.id)
            .group_by(FormSubmission.form_id)
        )
    }
    forms = await session.scalars(
        select(CollectionForm)
        .where(CollectionForm.project_id == project.id)
        .order_by(CollectionForm.created_at.desc())
    )
    return [_out(f, counts.get(f.id, 0)) for f in forms]


@router.post("", response_model=FormOut, status_code=status.HTTP_201_CREATED)
async def create_form(
    org_id: UUID, project_id: UUID, body: FormIn, member: Planner, session: SessionDep
) -> FormOut:
    project = await svc.get_project(session, org_id, project_id)
    await _check_activity(session, project, body.activity_id)
    form = CollectionForm(
        **body.model_dump(),
        organization_id=org_id,
        project_id=project.id,
        created_by=member.user_id,
    )
    session.add(form)
    await session.flush()
    _log(session, member, "form.created", "form", form.id, {"title": form.title})
    await session.commit()
    await session.refresh(form)
    return _out(form, 0)


@router.get("/{form_id}", response_model=FormOut)
async def get_form(
    org_id: UUID, project_id: UUID, form_id: UUID, _: AnyMember, session: SessionDep
) -> FormOut:
    project = await svc.get_project(session, org_id, project_id)
    form = await _get(session, project, form_id)
    return _out(form, await _count(session, form))


@router.patch("/{form_id}", response_model=FormOut)
async def update_form(
    org_id: UUID,
    project_id: UUID,
    form_id: UUID,
    body: FormUpdate,
    member: Planner,
    session: SessionDep,
) -> FormOut:
    project = await svc.get_project(session, org_id, project_id)
    form = await _get(session, project, form_id)
    submissions = await _count(session, form)
    data = body.model_dump(exclude_unset=True)
    if "fields" in data and submissions:
        # Les réponses déjà reçues doivent garder leur sens.
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Des réponses ont déjà été reçues : les questions ne peuvent plus changer. "
            "Dupliquez le formulaire pour en créer une nouvelle version.",
        )
    if "activity_id" in data:
        await _check_activity(session, project, body.activity_id)
    for key, value in data.items():
        setattr(form, key, value)
    _log(
        session,
        member,
        "form.updated",
        "form",
        form.id,
        {"title": form.title, **({"status": body.status} if body.status else {})},
    )
    await session.commit()
    await session.refresh(form)
    return _out(form, submissions)


@router.delete("/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_form(
    org_id: UUID, project_id: UUID, form_id: UUID, member: Planner, session: SessionDep
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    form = await _get(session, project, form_id)
    if await _count(session, form) and member.role.value not in ("admin", "project_manager"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Ce formulaire a des réponses : seul un responsable peut le supprimer",
        )
    _log(session, member, "form.deleted", "form", form.id, {"title": form.title})
    await session.delete(form)
    await session.commit()


# --- Réponses ---------------------------------------------------------------------------


@router.post("/{form_id}/submissions", response_model=SubmissionOut, status_code=201)
async def submit(
    org_id: UUID,
    project_id: UUID,
    form_id: UUID,
    body: SubmissionIn,
    member: Collector,
    session: SessionDep,
    response: Response,
) -> FormSubmission:
    project = await svc.get_project(session, org_id, project_id)
    form = await _get(session, project, form_id)
    if body.client_uuid:
        existing = await session.scalar(
            select(FormSubmission).where(
                FormSubmission.client_uuid == body.client_uuid,
                FormSubmission.form_id == form.id,
            )
        )
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return existing
    if form.status != "published":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ce formulaire n'accepte pas de réponses (brouillon ou clos)",
        )
    try:
        answers = forms_svc.validate_answers(_fields(form), body.answers)
    except forms_svc.InvalidAnswers as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    data = body.model_dump(exclude={"answers"}, exclude_none=True)
    submission = FormSubmission(
        **data,
        answers=answers,
        organization_id=org_id,
        project_id=project.id,
        form_id=form.id,
        submitted_by=member.user_id,
    )
    session.add(submission)
    await session.commit()
    await session.refresh(submission)
    return submission


async def _submissions(
    session: SessionDep, form: CollectionForm
) -> list[tuple[FormSubmission, str]]:
    rows = await session.execute(
        select(FormSubmission, User.full_name)
        .outerjoin(User, User.id == FormSubmission.submitted_by)
        .where(FormSubmission.form_id == form.id)
        .order_by(FormSubmission.collected_at, FormSubmission.created_at)
    )
    return [(s, name or "") for s, name in rows]


@router.get("/{form_id}/submissions", response_model=list[SubmissionOut])
async def list_submissions(
    org_id: UUID, project_id: UUID, form_id: UUID, _: Planner, session: SessionDep
) -> list[SubmissionOut]:
    project = await svc.get_project(session, org_id, project_id)
    form = await _get(session, project, form_id)
    return [
        SubmissionOut.model_validate(s).model_copy(update={"submitter_name": name})
        for s, name in await _submissions(session, form)
    ]


@router.delete("/{form_id}/submissions/{submission_id}", status_code=204)
async def delete_submission(
    org_id: UUID,
    project_id: UUID,
    form_id: UUID,
    submission_id: UUID,
    member: ProjectAdmin,
    session: SessionDep,
) -> None:
    project = await svc.get_project(session, org_id, project_id)
    form = await _get(session, project, form_id)
    submission = await session.scalar(
        select(FormSubmission).where(
            FormSubmission.id == submission_id, FormSubmission.form_id == form.id
        )
    )
    if submission is None:
        raise svc.not_found("Réponse")
    _log(session, member, "form.submission_deleted", "form", form.id, {"title": form.title})
    await session.delete(submission)
    await session.commit()


@router.get("/{form_id}/summary", response_model=FormSummary)
async def summary(
    org_id: UUID, project_id: UUID, form_id: UUID, _: AnyMember, session: SessionDep
) -> FormSummary:
    project = await svc.get_project(session, org_id, project_id)
    form = await _get(session, project, form_id)
    rows = await session.scalars(
        select(FormSubmission)
        .where(FormSubmission.form_id == form.id)
        .order_by(FormSubmission.collected_at)
    )
    return forms_svc.summarize(_fields(form), list(rows))


def _cell(value: Any) -> Any:
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return value


def _workbook(form: CollectionForm, rows: list[tuple[FormSubmission, str]]) -> bytes:
    fields = _fields(form)
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Réponses"
    headers = ["Date de collecte", "Saisi par", "Lieu", "Latitude", "Longitude"]
    _sheet(ws, headers + [f.label for f in fields], [18, 20, 20, 11, 11] + [24] * len(fields))
    for submission, name in rows:
        ws.append(
            [
                submission.collected_at.strftime("%d/%m/%Y %H:%M"),
                name,
                submission.location,
                submission.latitude,
                submission.longitude,
                *(_cell(submission.answers.get(f.key)) for f in fields),
            ]
        )
    _wrap(ws)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


@router.get("/{form_id}/export.xlsx", response_class=Response)
async def export_submissions(
    org_id: UUID, project_id: UUID, form_id: UUID, _: Planner, session: SessionDep
) -> Response:
    project = await svc.get_project(session, org_id, project_id)
    form = await _get(session, project, form_id)
    content = await asyncio.to_thread(_workbook, form, await _submissions(session, form))
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{project.code}-formulaire.xlsx"'},
    )
