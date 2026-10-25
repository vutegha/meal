"""Durcissement avant la production : rôle de la base, tâches longues, fichiers déposés, verrous."""

import asyncio
import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import role_problems, system_session
from app.documents.filetypes import DOCX, XLSX, ImageTooLarge, open_image, sniff
from app.models import Evidence, Job, JobStatus, SourceDocument
from app.services import jobs
from tests.conftest import register
from tests.test_admin import platform_admin
from tests.test_ai import project_with_document, upload
from tests.test_executions import execution_body, setup
from tests.test_payments import announce

# --- Rôle de la base ----------------------------------------------------------------------


async def test_role_check(monkeypatch: pytest.MonkeyPatch) -> None:
    blocking, warnings = await role_problems()
    # Les tests se connectent en superutilisateur, puis endossent meal_app : RLS active.
    assert blocking == []
    assert any("superutilisateur" in w for w in warnings)

    monkeypatch.setattr(get_settings(), "db_app_role", "role_absent")
    blocking, _ = await role_problems()
    assert blocking and "role_absent" in blocking[0]


# --- Tâches longues -----------------------------------------------------------------------


async def new_job(org_id: str, **values: Any) -> UUID:
    async with system_session() as session:
        job = Job(organization_id=UUID(org_id), kind="essai", **values)
        session.add(job)
        await session.commit()
        return job.id


async def job_of(job_id: UUID) -> Job:
    async with system_session() as session:
        return await session.get_one(Job, job_id)


async def test_job_runs_once_and_survives_cancellation(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = await register(client, "taches@x.org")
    calls: list[UUID] = []

    async def handler(session: Any, job: Job) -> dict[str, Any]:
        calls.append(job.id)
        return {"ok": True}

    monkeypatch.setitem(jobs.HANDLERS, "essai", handler)
    job_id = await new_job(ctx["org_id"])
    await jobs.run_job(job_id)
    # Seconde livraison (worker redémarré, relance d'ARQ) : le modèle n'est pas rappelé.
    await jobs.run_job(job_id)
    assert calls == [job_id]
    job = await job_of(job_id)
    assert job.status == JobStatus.SUCCEEDED and job.started_at and job.finished_at

    async def cancelled(session: Any, job: Job) -> dict[str, Any]:
        raise asyncio.CancelledError

    monkeypatch.setitem(jobs.HANDLERS, "essai", cancelled)
    job_id = await new_job(ctx["org_id"])
    with pytest.raises(asyncio.CancelledError):
        await jobs.run_job(job_id)
    job = await job_of(job_id)
    assert job.status == JobStatus.FAILED and job.error == jobs.INTERRUPTED


async def test_lost_jobs_are_failed(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = await register(client, "perdues@x.org")
    now = datetime.now(UTC)
    abandoned: list[str] = []

    async def hook(session: Any, job: Job, message: str) -> None:
        abandoned.append(message)

    monkeypatch.setitem(jobs.ON_ABANDON, "essai", hook)
    lost = await new_job(
        ctx["org_id"], status=JobStatus.RUNNING, started_at=now - timedelta(hours=1)
    )
    running = await new_job(ctx["org_id"], status=JobStatus.RUNNING, started_at=now)
    forgotten = await new_job(ctx["org_id"], created_at=now - timedelta(hours=3))
    waiting = await new_job(ctx["org_id"])

    assert await jobs.fail_stale() == 2
    assert (await job_of(lost)).error == jobs.INTERRUPTED
    assert (await job_of(forgotten)).error == jobs.NOT_STARTED
    assert (await job_of(running)).status == JobStatus.RUNNING
    assert (await job_of(waiting)).status == JobStatus.QUEUED
    assert abandoned == [jobs.INTERRUPTED, jobs.NOT_STARTED]


async def test_queue_down_fails_the_job(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx, base = await project_with_document(client)
    monkeypatch.setattr(get_settings(), "jobs_inline", False)
    monkeypatch.setattr(get_settings(), "redis_url", "redis://127.0.0.1:1/0")
    r = await client.post(f"{base}/ai/logframe-extraction", headers=ctx["headers"])
    assert r.status_code == 503 and r.json()["detail"] == jobs.QUEUE_DOWN
    async with system_session() as session:
        [job] = await session.scalars(select(Job))
    # La tâche ne reste pas « en attente » pour toujours.
    assert job.status == JobStatus.FAILED and job.error == jobs.QUEUE_DOWN


# --- Fichiers déposés ---------------------------------------------------------------------


def office(name: str) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, "<xml/>")
    return buffer.getvalue()


def test_sniff_reads_the_content() -> None:
    assert sniff(b"%PDF-1.7 ...", "photo.jpg", "image/jpeg") == "application/pdf"
    assert sniff(office("word/document.xml"), "x.bin", None) == DOCX
    assert sniff(office("xl/workbook.xml"), "x", "application/octet-stream") == XLSX
    assert sniff(office("autre.xml"), "x.docx", DOCX) is None
    assert sniff(b"ID3\x04rest", "memo", None) == "audio/mpeg"
    assert sniff(b"OggS\x00", "memo.ogg", None) == "audio/ogg"
    assert sniff(b"RIFF\x00\x00\x00\x00WAVEfmt ", "memo", None) == "audio/wav"
    assert sniff(b"#!AMR\n", "memo", None) == "audio/amr"
    assert sniff(b"\x00\x00\x00\x18ftypisom", "clip", None) == "video/mp4"
    assert sniff(b"\x00\x00\x00\x18ftyp3gp4", "memo", "audio/3gpp") == "audio/3gpp"
    # Texte : seulement avec une extension ou un type de texte, et toujours en texte brut.
    assert sniff(b"<script>alert(1)</script>", "note.txt", "text/html") == "text/plain"
    assert sniff(b"<html><script>alert(1)</script>", "page.html", "text/html") is None
    assert sniff(b"\x00\x01binaire", "note.txt", "text/plain") is None


def png(width: int, height: int) -> bytes:
    buffer = BytesIO()
    Image.new("1", (width, height)).save(buffer, "PNG")
    return buffer.getvalue()


def test_giant_images_are_refused_before_decoding() -> None:
    assert open_image(png(64, 48)).size == (64, 48)
    with pytest.raises(ImageTooLarge):
        open_image(png(12_000, 11_000))
    # Au-delà du double, Pillow lui-même refuse d'ouvrir le fichier.
    with pytest.raises(ImageTooLarge):
        open_image(png(16_000, 16_000))


async def test_evidence_is_typed_by_content(client: AsyncClient) -> None:
    ctx, base, nodes, _ = await setup(client)
    h = ctx["headers"]
    execution = (
        await client.post(
            f"{base}/executions", headers=h, json=execution_body(nodes["activity"]["id"])
        )
    ).json()
    url = f"{base}/executions/{execution['id']}/evidence"

    # Page web annoncée comme texte : gardée en texte brut, téléchargée, jamais affichée.
    r = await client.post(
        url, headers=h, files={"file": ("note<x>.txt", b"<script>alert(1)</script>", "text/html")}
    )
    assert r.status_code == 201, r.text
    assert r.json()["content_type"] == "text/plain"
    served = await client.get(f"{base}/evidence/{r.json()['id']}/file", headers=h)
    assert served.headers["content-type"].startswith("text/plain")
    assert served.headers["content-disposition"] == 'attachment; filename="note_x_.txt"'
    assert served.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in served.headers["content-security-policy"]
    async with system_session() as session:
        evidence = await session.get_one(Evidence, UUID(r.json()["id"]))
    # Le nom choisi par l'utilisateur n'entre pas dans le chemin du fichier.
    assert evidence.storage_key.endswith(".txt") and "note" not in evidence.storage_key

    page = b"<html><script>alert(1)</script></html>"
    r = await client.post(url, headers=h, files={"file": ("page.html", page, "text/html")})
    assert r.status_code == 415

    r = await client.post(url, headers=h, files={"file": ("vue.png", png(12_000, 11_000), "")})
    assert r.status_code == 415 and "trop grande" in r.json()["detail"]

    # Enregistrement : copié et relu par morceaux, contenu intact.
    recording = b"OggS" + bytes(range(256)) * 9000
    r = await client.post(url, headers=h, files={"file": ("memo.bin", recording, "")})
    assert r.status_code == 201 and r.json()["kind"] == "audio"
    assert r.json()["content_type"] == "audio/ogg"
    played = await client.get(f"{base}/evidence/{r.json()['id']}/file", headers=h)
    assert played.content == recording
    assert played.headers["content-disposition"].startswith("inline")


async def test_documents_are_typed_by_content(client: AsyncClient) -> None:
    ctx, base = await project_with_document(client)
    r = await upload(client, ctx, base, "notes.txt", b"Compte rendu <b>terrain</b>", "text/html")
    assert r.status_code == 201, r.text
    async with system_session() as session:
        document = await session.get_one(SourceDocument, UUID(r.json()["id"]))
    assert document.mime_type == "text/plain" and "notes" not in document.storage_key
    r = await upload(client, ctx, base, "carte.png", png(12_000, 11_000), "image/png")
    assert r.json()["status"] == "failed" and "trop grande" in r.json()["error"]


# --- Verrous ------------------------------------------------------------------------------


async def test_double_confirmation_applies_the_payment_once(client: AsyncClient) -> None:
    admin = await platform_admin(client)
    ctx = await register(client, "double@x.org")
    out = await announce(client, ctx, plan="team", cycle="annual", method="bank_transfer")
    confirm = f"/api/v1/admin/payments/{out['payment']['id']}/confirm"
    first, second = await asyncio.gather(
        client.post(confirm, headers=admin["headers"], json={}),
        client.post(confirm, headers=admin["headers"], json={}),
    )
    assert sorted([first.status_code, second.status_code]) == [200, 409]
