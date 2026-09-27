from collections.abc import Iterator
from io import BytesIO
from typing import Any

import docx
import pymupdf
import pytest
from httpx import AsyncClient

from app.documents.render import parse
from app.llm.client import set_llm
from tests.conftest import register
from tests.fake_llm import FakeLLM
from tests.test_ai import SAMPLE, upload
from tests.test_organizations import add_member, login
from tests.test_projects import build_logframe, create_project


@pytest.fixture
def fake_llm() -> Iterator[FakeLLM]:
    llm = FakeLLM()
    set_llm(llm)
    yield llm
    set_llm(None)


async def setup(client: AsyncClient) -> tuple[dict[str, Any], str, dict[str, Any]]:
    ctx = await register(client, "pm@example.org")
    base = f"/api/v1/orgs/{ctx['org_id']}/projects/{await create_project(client, ctx)}"
    nodes = await build_logframe(client, ctx, base)
    r = await client.post(
        f"{base}/budget/lines",
        headers=ctx["headers"],
        json={
            "label": "Formateurs",
            "activity_id": nodes["activity"]["id"],
            "quantity": "4",
            "unit": "personne",
            "unit_cost": "800",
            "frequency": "6",
            "donor_line_code": "1.1",
        },
    )
    assert r.status_code == 201, r.text
    return ctx, base, nodes


def test_markdown_parser() -> None:
    blocks = parse(
        "Intro **gras**\nsuite\n\n- un\n- deux\n1. premier\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n## Titre"
    )
    assert [b.kind for b in blocks] == ["paragraph", "bullets", "numbered", "table", "heading"]
    assert blocks[0].text == "Intro **gras** suite"
    assert blocks[1].items == ["un", "deux"]
    assert blocks[3].rows == [["A", "B"], ["1", "2"]]


async def test_blank_tor_edit_and_workflow(client: AsyncClient) -> None:
    ctx, base, nodes = await setup(client)
    h = ctx["headers"]
    activity = nodes["activity"]["id"]

    r = await client.post(f"{base}/activities/{nodes['output']['id']}/tor", headers=h)
    assert r.status_code == 422  # un résultat n'a pas de TdR

    r = await client.post(f"{base}/activities/{activity}/tor", headers=h)
    assert r.status_code == 201, r.text
    tor = r.json()
    assert tor["status"] == "draft" and tor["version"] == 1
    budget = next(s for s in tor["sections"] if s["key"] == "budget")
    assert "| 1.1 Formateurs | 4 personne | 800 | 6 | 19 200 |" in budget["content"]
    assert (await client.post(f"{base}/activities/{activity}/tor", headers=h)).status_code == 409

    url = f"{base}/tors/{tor['id']}"
    sections = tor["sections"]
    sections[0]["content"] = "Contexte rédigé à la main."
    r = await client.put(url, headers=h, json={"title": "TdR formation AVEC", "sections": sections})
    assert r.json()["version"] == 2
    # Enregistrer sans changement ne crée pas de version.
    r = await client.put(url, headers=h, json={"title": "TdR formation AVEC", "sections": sections})
    assert r.json()["version"] == 2

    assert (await client.post(f"{url}/submit", headers=h)).json()["status"] == "submitted"
    r = await client.put(url, headers=h, json={"title": "Autre", "sections": sections})
    assert r.status_code == 409
    assert (await client.post(f"{url}/return", headers=h, json={})).status_code == 422
    r = await client.post(f"{url}/return", headers=h, json={"comment": "Préciser le lieu"})
    assert r.json()["status"] == "draft" and r.json()["review_comment"] == "Préciser le lieu"

    await client.post(f"{url}/submit", headers=h)
    r = await client.post(f"{url}/approve", headers=h, json={"comment": "Bon pour exécution"})
    assert r.json()["status"] == "approved" and r.json()["approved_at"]
    r = await client.post(f"{url}/reopen", headers=h)
    assert r.json()["status"] == "draft" and r.json()["approved_at"] is None

    versions = (await client.get(f"{url}/versions", headers=h)).json()
    assert [v["version"] for v in versions] == [2, 1]
    summary = (await client.get(f"{base}/tors", headers=h)).json()
    assert [t["title"] for t in summary] == ["TdR formation AVEC"]

    audit = (await client.get(f"/api/v1/orgs/{ctx['org_id']}/audit", headers=h)).json()
    actions = {entry["action"] for entry in audit}
    assert {
        "tor.created",
        "tor.updated",
        "tor.submitted",
        "tor.returned",
        "tor.approved",
    } <= actions


async def test_export_docx_and_pdf(client: AsyncClient) -> None:
    ctx, base, nodes = await setup(client)
    h = ctx["headers"]
    tor = (await client.post(f"{base}/activities/{nodes['activity']['id']}/tor", headers=h)).json()
    tor["sections"][1]["content"] = "- Former **600** membres\n- Suivre l'épargne"
    await client.put(
        f"{base}/tors/{tor['id']}",
        headers=h,
        json={"title": tor["title"], "sections": tor["sections"]},
    )

    r = await client.get(f"{base}/tors/{tor['id']}/export.docx", headers=h)
    assert r.status_code == 200
    assert 'filename="TdR-Former-30-AVEC-v2.docx"' in r.headers["content-disposition"]
    text = "\n".join(p.text for p in docx.Document(BytesIO(r.content)).paragraphs)
    assert "Objectifs de l'activité" in text and "Former 600 membres" in text

    r = await client.get(f"{base}/tors/{tor['id']}/export.pdf", headers=h)
    assert r.headers["content-type"] == "application/pdf"
    with pymupdf.open(stream=r.content, filetype="pdf") as pdf:  # type: ignore[no-untyped-call]
        content = "".join(page.get_text() for page in pdf)
    assert "Termes de référence" in content and "19 200" in content

    assert (await client.get(f"{base}/tors/{tor['id']}/export.odt", headers=h)).status_code == 404


async def test_generation_with_ai(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx, base, nodes = await setup(client)
    h = ctx["headers"]
    r = await upload(client, ctx, base, "proposition.txt", SAMPLE.read_bytes(), "text/plain")
    assert r.status_code == 201
    activity = nodes["activity"]["id"]

    r = await client.post(
        f"{base}/activities/{activity}/tor/generate",
        headers=h,
        json={"instructions": "Formation de trois jours à Rutshuru"},
    )
    assert r.status_code == 202, r.text
    job = (
        await client.get(f"/api/v1/orgs/{ctx['org_id']}/jobs/{r.json()['id']}", headers=h)
    ).json()
    assert job["status"] == "succeeded", job["error"]

    context = fake_llm.calls[0]["content"][0]["text"]
    assert "A1.1.1 : Former 30 AVEC" in context and "R1.1 : Des AVEC sont fonctionnelles" in context
    assert "Formation de trois jours à Rutshuru" in context
    assert '<extrait document="proposition.txt"' in context  # passages retrouvés
    wanted = fake_llm.calls[0]["content"][1]["text"]
    assert "- contexte :" in wanted and "- budget :" not in wanted  # budget calculé, pas rédigé

    tor = (await client.get(f"{base}/tors/{job['result']['tor_id']}", headers=h)).json()
    assert tor["title"] == "TdR : formation des membres des AVEC"
    sections = {s["key"]: s["content"] for s in tor["sections"]}
    assert sections["contexte"].startswith("Les ménages ciblés")
    assert "19 200" in sections["budget"] and "ignoré" not in sections["budget"]
    assert sections["risques"] == "[À compléter]"
    assert tor["missing_information"] == ["Dates de la formation", "Lieu exact"]

    # Une nouvelle génération sur un brouillon crée une nouvelle version.
    await client.post(f"{base}/activities/{activity}/tor/generate", headers=h, json={})
    tor = (await client.get(f"{base}/tors/{tor['id']}", headers=h)).json()
    assert tor["version"] == 2

    await client.post(f"{base}/tors/{tor['id']}/submit", headers=h)
    r = await client.post(f"{base}/activities/{activity}/tor/generate", headers=h, json={})
    assert r.status_code == 409


async def test_roles_and_isolation(client: AsyncClient) -> None:
    ctx, base, nodes = await setup(client)
    tor = (
        await client.post(
            f"{base}/activities/{nodes['activity']['id']}/tor", headers=ctx["headers"]
        )
    ).json()
    url = f"{base}/tors/{tor['id']}"
    body = {"title": "x", "sections": tor["sections"]}

    await add_member(client, ctx, "terrain@example.org", "field_agent")
    field = await login(client, "terrain@example.org")
    assert (await client.get(url, headers=field)).status_code == 200
    assert (await client.put(url, headers=field, json=body)).status_code == 403

    await add_member(client, ctx, "meal@example.org", "meal_officer")
    meal = await login(client, "meal@example.org")
    assert (await client.put(url, headers=meal, json=body)).status_code == 200
    assert (await client.post(f"{url}/submit", headers=meal)).status_code == 200
    # Le chargé MEAL rédige et soumet ; l'approbation revient au chef de projet.
    assert (await client.post(f"{url}/approve", headers=meal, json={})).status_code == 403
    assert (await client.delete(url, headers=meal)).status_code == 403

    other = await register(client, "autre@example.org")
    foreign = f"/api/v1/orgs/{other['org_id']}/projects/{base.rsplit('/', 1)[1]}/tors/{tor['id']}"
    assert (await client.get(foreign, headers=other["headers"])).status_code == 404
    assert (await client.get(url, headers=other["headers"])).status_code == 404

    assert (await client.delete(url, headers=ctx["headers"])).status_code == 204
