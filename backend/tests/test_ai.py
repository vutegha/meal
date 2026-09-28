from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.llm.client import set_llm
from tests.conftest import register
from tests.fake_llm import FakeLLM
from tests.test_organizations import add_member, login
from tests.test_projects import create_project

SAMPLE = Path(__file__).parents[1] / "app/llm/evals/proposition_avec.txt"


@pytest.fixture
def fake_llm() -> Iterator[FakeLLM]:
    llm = FakeLLM()
    set_llm(llm)
    yield llm
    set_llm(None)


async def upload(
    client: AsyncClient, ctx: dict[str, Any], base: str, name: str, data: bytes, mime: str
) -> Any:
    return await client.post(
        f"{base}/documents", headers=ctx["headers"], files={"file": (name, data, mime)}
    )


async def project_with_document(client: AsyncClient) -> tuple[dict[str, Any], str]:
    ctx = await register(client, "meal@example.org")
    base = f"/api/v1/orgs/{ctx['org_id']}/projects/{await create_project(client, ctx)}"
    r = await upload(client, ctx, base, "proposition.txt", SAMPLE.read_bytes(), "text/plain")
    assert r.status_code == 201, r.text
    return ctx, base


async def extract(client: AsyncClient, ctx: dict[str, Any], base: str) -> Any:
    r = await client.post(f"{base}/ai/logframe-extraction", headers=ctx["headers"])
    assert r.status_code == 202, r.text
    return r.json()


async def test_upload_search_and_delete(client: AsyncClient) -> None:
    ctx, base = await project_with_document(client)
    documents = (await client.get(f"{base}/documents", headers=ctx["headers"])).json()
    assert documents[0]["status"] == "extracted"
    assert documents[0]["page_count"] >= 1

    dup = await upload(client, ctx, base, "copie.txt", SAMPLE.read_bytes(), "text/plain")
    assert dup.status_code == 409
    bad = await upload(client, ctx, base, "clip.mp4", b"\x00\x00", "video/mp4")
    assert bad.status_code == 415
    broken = await upload(client, ctx, base, "photo.jpg", b"\xff\xd8", "image/jpeg")
    assert broken.json()["status"] == "failed" and broken.json()["error"] == "Image illisible"
    empty = await upload(client, ctx, base, "vide.txt", b"   ", "text/plain")
    assert empty.json()["status"] == "failed"

    hits = (
        await client.get(
            f"{base}/documents/search", params={"q": "épargne"}, headers=ctx["headers"]
        )
    ).json()
    assert hits and hits[0]["filename"] == "proposition.txt"
    assert "«" in hits[0]["snippet"]

    r = await client.delete(f"{base}/documents/{documents[0]['id']}", headers=ctx["headers"])
    assert r.status_code == 204
    names = [
        d["filename"]
        for d in (await client.get(f"{base}/documents", headers=ctx["headers"])).json()
    ]
    assert names == ["photo.jpg", "vide.txt"]


async def test_upload_size_limit(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = await register(client, "meal@example.org")
    base = f"/api/v1/orgs/{ctx['org_id']}/projects/{await create_project(client, ctx)}"
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    r = await upload(client, ctx, base, "gros.txt", b"x" * 10, "text/plain")
    assert r.status_code == 413


async def test_extraction_creates_verified_proposal(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx, base = await project_with_document(client)
    job = await extract(client, ctx, base)
    assert job["status"] == "succeeded", job
    assert job["result"]["nodes"] == 7

    # Le modèle reçoit les documents balisés par page, et le prompt versionné.
    sent = fake_llm.calls[0]
    assert sent["model"] == get_settings().llm_model_extraction
    assert '<document index="1" filename="proposition.txt">' in sent["content"][0]["text"]
    assert sent["content"][0]["cache_control"] == {"type": "ephemeral"}

    fetched = (
        await client.get(f"/api/v1/orgs/{ctx['org_id']}/jobs/{job['id']}", headers=ctx["headers"])
    ).json()
    assert fetched["status"] == "succeeded"

    proposal = (
        await client.get(f"{base}/proposals/{job['result']['proposal_id']}", headers=ctx["headers"])
    ).json()
    assert proposal["status"] == "pending"
    verified = {n["ref"]: n["verified"] for n in proposal["payload"]["nodes"]}
    # Guillemets typographiques et apostrophes normalisés : la citation reste reconnue.
    assert verified["R1.1"] is True
    # Citation inventée : signalée comme non vérifiée.
    assert verified["A1.2.1"] is False
    assert all(i["verified"] for i in proposal["payload"]["indicators"])
    assert proposal["payload"]["documents"] == ["proposition.txt"]

    usage = (
        await client.get(f"/api/v1/orgs/{ctx['org_id']}/ai/usage", headers=ctx["headers"])
    ).json()
    assert usage["calls_this_month"] == 1
    # 12 000 × 4 + 3 000 × 20 + 10 000 × 5 (écriture du cache), par million de jetons.
    assert usage["month_cost_usd"] == "0.158000"
    [purpose] = usage["by_purpose"]
    assert purpose["key"] == "logframe_extraction"
    assert purpose["calls"] == 1 and purpose["errors"] == 0
    assert usage["by_project"][0]["label"].startswith("P1 · ")
    assert usage["by_month"][-1]["cost_usd"] == "0.158000"
    assert usage["recent"][0]["project_code"] == "P1"


async def test_apply_selected_items(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx, base = await project_with_document(client)
    job = await extract(client, ctx, base)
    url = f"{base}/proposals/{job['result']['proposal_id']}"
    payload = (await client.get(url, headers=ctx["headers"])).json()["payload"]

    # L'utilisateur écarte R1.2 mais garde A1.2.1 : refusé, rien n'est créé.
    kept = [n for n in payload["nodes"] if n["ref"] != "R1.2"]
    r = await client.post(f"{url}/apply", headers=ctx["headers"], json={"nodes": kept})
    assert r.status_code == 422
    assert (await client.get(f"{base}/logframe", headers=ctx["headers"])).json() == []

    # Il écarte la branche R1.2 et corrige un intitulé.
    kept = [n for n in payload["nodes"] if n["ref"] not in ("R1.2", "A1.2.1")]
    kept[0]["title"] = "Améliorer durablement les conditions de vie"
    r = await client.post(
        f"{url}/apply",
        headers=ctx["headers"],
        json={
            "nodes": kept,
            "indicators": payload["indicators"],
            "budget_lines": payload["budget_lines"],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "applied"

    tree = (await client.get(f"{base}/logframe", headers=ctx["headers"])).json()
    assert tree[0]["title"] == "Améliorer durablement les conditions de vie"
    outputs = tree[0]["children"][0]["children"]
    assert [o["code"] for o in outputs] == ["R1.1"]
    assert [a["code"] for a in outputs[0]["children"]] == ["A1.1.1", "A1.1.2"]

    indicators = {
        i["code"]: i
        for i in (await client.get(f"{base}/indicators", headers=ctx["headers"])).json()
    }
    assert indicators["OS1.a"]["baseline"] == "38.0000"
    assert indicators["R1.1.a"]["disaggregations"] == ["sexe"]
    summary = (await client.get(f"{base}/budget/summary", headers=ctx["headers"])).json()
    assert summary["planned"] == "44400.00"

    again = await client.post(f"{url}/apply", headers=ctx["headers"], json={"nodes": kept})
    assert again.status_code == 409


async def test_reject_proposal(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx, base = await project_with_document(client)
    job = await extract(client, ctx, base)
    url = f"{base}/proposals/{job['result']['proposal_id']}"
    assert (await client.post(f"{url}/reject", headers=ctx["headers"])).json()[
        "status"
    ] == "rejected"
    proposals = (await client.get(f"{base}/proposals", headers=ctx["headers"])).json()
    assert [p["status"] for p in proposals] == ["rejected"]


async def test_extraction_failures(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = await register(client, "meal@example.org")
    base = f"/api/v1/orgs/{ctx['org_id']}/projects/{await create_project(client, ctx)}"
    r = await client.post(f"{base}/ai/logframe-extraction", headers=ctx["headers"])
    assert r.status_code == 409  # aucun document

    await upload(client, ctx, base, "p.txt", SAMPLE.read_bytes(), "text/plain")
    set_llm(FakeLLM(error="Clé API Anthropic absente ou invalide."))
    try:
        job = await extract(client, ctx, base)
    finally:
        set_llm(None)
    assert job["status"] == "failed"
    assert job["error"] == "Clé API Anthropic absente ou invalide."
    assert (await client.get(f"{base}/proposals", headers=ctx["headers"])).json() == []

    # Plafond atteint : l'appel n'est même pas tenté.
    llm = FakeLLM()
    set_llm(llm)
    monkeypatch.setattr(get_settings(), "ai_monthly_budget_usd", 0.1)
    try:
        assert (await extract(client, ctx, base))["status"] == "succeeded"
        job = await extract(client, ctx, base)
    finally:
        set_llm(None)
    assert job["status"] == "failed"
    assert "plafond" in job["error"]
    assert len(llm.calls) == 1

    # Documents trop volumineux : erreur explicite plutôt que troncature.
    set_llm(FakeLLM())
    monkeypatch.setattr(get_settings(), "ai_monthly_budget_usd", 0)
    monkeypatch.setattr(get_settings(), "llm_max_document_chars", 100)
    try:
        job = await extract(client, ctx, base)
    finally:
        set_llm(None)
    assert "trop volumineux" in job["error"]


async def test_roles_and_isolation(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx, base = await project_with_document(client)
    job = await extract(client, ctx, base)
    proposal_url = f"{base}/proposals/{job['result']['proposal_id']}"

    await add_member(client, ctx, "terrain@example.org", "field_agent")
    field = await login(client, "terrain@example.org")
    assert (await client.get(f"{base}/documents", headers=field)).status_code == 200
    r = await client.post(
        f"{base}/documents", headers=field, files={"file": ("a.txt", b"texte", "text/plain")}
    )
    assert r.status_code == 403
    assert (await client.post(f"{base}/ai/logframe-extraction", headers=field)).status_code == 403
    assert (await client.post(f"{proposal_url}/reject", headers=field)).status_code == 403

    other = await register(client, "autre@example.org", org="Autre ONG")
    assert (await client.get(f"{base}/documents", headers=other["headers"])).status_code == 404
    assert (await client.get(proposal_url, headers=other["headers"])).status_code == 404
    job_url = f"/api/v1/orgs/{other['org_id']}/jobs/{job['id']}"
    assert (await client.get(job_url, headers=other["headers"])).status_code == 404
