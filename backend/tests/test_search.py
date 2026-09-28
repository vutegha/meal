from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient

from app.llm.embeddings import set_embedder
from tests.conftest import register
from tests.fake_embeddings import FakeEmbedder
from tests.test_ai import upload
from tests.test_projects import create_project

SAVINGS = "Les membres des AVEC constituent une épargne collective chaque semaine."
WELL = "Réhabilitation du forage de Kiwanja et comité de gestion de l'eau."


@pytest.fixture
def embedder() -> Iterator[FakeEmbedder]:
    fake = FakeEmbedder()
    set_embedder(fake)
    yield fake
    set_embedder(None, active=False)


async def project(client: AsyncClient) -> tuple[dict[str, Any], str]:
    ctx = await register(client, "meal@example.org")
    base = f"/api/v1/orgs/{ctx['org_id']}/projects/{await create_project(client, ctx)}"
    for name, text in (("avec.txt", SAVINGS), ("eau.txt", WELL)):
        r = await upload(client, ctx, base, name, text.encode(), "text/plain")
        assert r.status_code == 201, r.text
    return ctx, base


async def search(client: AsyncClient, ctx: dict[str, Any], base: str, q: str) -> Any:
    r = await client.get(f"{base}/documents/search", headers=ctx["headers"], params={"q": q})
    assert r.status_code == 200, r.text
    return r.json()


async def test_full_text_only_without_embeddings(client: AsyncClient) -> None:
    ctx, base = await project(client)
    assert await search(client, ctx, base, "économies") == []
    hits = await search(client, ctx, base, "forage")
    assert [h["filename"] for h in hits] == ["eau.txt"] and not hits[0]["semantic"]


async def test_semantic_search(client: AsyncClient, embedder: FakeEmbedder) -> None:
    ctx, base = await project(client)
    # Aucun mot en commun : trouvée par le sens.
    hits = await search(client, ctx, base, "économies")
    assert [h["filename"] for h in hits] == ["avec.txt"] and hits[0]["semantic"]
    assert embedder.calls == [("document", 2), ("query", 1)]

    # Pages déjà vectorisées : seule la requête est envoyée.
    hits = await search(client, ctx, base, "forage")
    assert hits[0]["filename"] == "eau.txt" and not hits[0]["semantic"]
    assert embedder.calls[2:] == [("query", 1)]

    usage = (
        await client.get(f"/api/v1/orgs/{ctx['org_id']}/ai/usage", headers=ctx["headers"])
    ).json()
    purposes = {row["key"] for row in usage["by_purpose"]}
    assert {"document_embeddings", "search_embeddings"} <= purposes


async def test_semantic_failure_falls_back(client: AsyncClient, embedder: FakeEmbedder) -> None:
    ctx, base = await project(client)
    embedder.fail = True
    hits = await search(client, ctx, base, "forage")
    assert [h["filename"] for h in hits] == ["eau.txt"]
    assert await search(client, ctx, base, "économies") == []
