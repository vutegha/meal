from io import BytesIO
from typing import Any

import docx
import pymupdf
from httpx import AsyncClient

from app.services.report import check_refs
from tests.conftest import register
from tests.fake_llm import FakeLLM
from tests.test_executions import execution_body, photo, setup
from tests.test_organizations import add_member, login
from tests.test_tor import fake_llm  # noqa: F401

__all__ = ["fake_llm"]

MINUTES = "Compte rendu : 36 participants, dont 22 femmes. Les AVEC ont élu leurs comités."


async def prepare(client: AsyncClient) -> tuple[dict[str, Any], str, dict[str, Any], str]:
    """Projet avec un indicateur, une exécution, un compte rendu et une photo consentie."""
    ctx, base, nodes, line = await setup(client)
    h = ctx["headers"]
    r = await client.post(
        f"{base}/indicators",
        headers=h,
        json={
            "node_id": nodes["output"]["id"],
            "code": "I1",
            "name": "Nombre de membres d'AVEC formés",
            "unit": "personnes",
            "target": 600,
        },
    )
    assert r.status_code == 201, r.text
    execution = (
        await client.post(
            f"{base}/executions", headers=h, json=execution_body(nodes["activity"]["id"])
        )
    ).json()
    url = f"{base}/executions/{execution['id']}/evidence"
    await client.post(
        url,
        headers=h,
        files={"file": ("compte-rendu.txt", MINUTES.encode(), "text/plain")},
        data={"kind": "minutes"},
    )
    await client.post(
        url,
        headers=h,
        files={"file": ("seance.jpg", photo(), "image/jpeg")},
        data={"caption": "Séance de formation", "consent_given": "true"},
    )
    await client.post(
        url,
        headers=h,
        files={"file": ("visage.jpg", photo(), "image/jpeg")},
        data={"caption": "Sans consentement"},
    )
    await client.post(
        f"{base}/executions/{execution['id']}/expenses",
        headers=h,
        json={"budget_line_id": line, "amount": "3200", "spent_on": "2026-03-16"},
    )
    return ctx, base, nodes, execution["id"]


async def generate(client: AsyncClient, ctx: dict[str, Any], base: str, execution: str) -> Any:
    r = await client.post(f"{base}/executions/{execution}/report/generate", headers=ctx["headers"])
    assert r.status_code == 202, r.text
    job = (
        await client.get(
            f"/api/v1/orgs/{ctx['org_id']}/jobs/{r.json()['id']}", headers=ctx["headers"]
        )
    ).json()
    assert job["status"] == "succeeded", job["error"]
    return job


def test_check_refs() -> None:
    assert (
        check_refs("Fait [S1][P2] et [S7].", {"S1", "P2"})
        == "Fait [S1][P2] et [source introuvable]."
    )


async def test_generation_sources_and_sections(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx, base, _, execution = await prepare(client)
    h = ctx["headers"]
    job = await generate(client, ctx, base, execution)

    context = fake_llm.calls[0]["content"][0]["text"]
    assert '<source ref="S1">' in context and "Deux groupes au lieu d'un" in context
    assert '<source ref="S2" type="minutes" fichier="compte-rendu.txt">' in context
    assert "Légende : Séance de formation" in context
    assert "Sans consentement" not in context  # photo sans consentement exclue
    assert "code I1 (R1.1)" in context
    wanted = fake_llm.calls[0]["content"][1]["text"]
    assert "- deroulement :" in wanted and "- participants :" not in wanted

    report = (await client.get(f"{base}/reports/{job['result']['report_id']}", headers=h)).json()
    assert report["title"] == "Rapport : formation AVEC de Kiwanja"
    assert report["status"] == "draft" and report["version"] == 1
    sections = {s["key"]: s["content"] for s in report["sections"]}
    assert sections["deroulement"] == "Deux groupes ont été constitués [S1] [source introuvable]."
    assert "| 22 | 14 | 0 | 0 | **36** |" in sections["participants"]
    assert "ignoré" not in sections["participants"]
    assert "19 200" in sections["budget"] and "3 200" in sections["budget"]
    assert sections["ecarts"] == "[À compléter]"
    assert [s["ref"] for s in report["sources"]] == ["S1", "S2", "P1"]
    assert report["missing_information"] == ["Retours des participants"]
    assert [s["code"] for s in report["indicator_suggestions"]] == ["I1"]

    listed = (await client.get(f"{base}/reports?execution_id={execution}", headers=h)).json()
    assert [r["id"] for r in listed] == [report["id"]]

    # Nouvelle génération sur un brouillon : même rapport, version suivante.
    await generate(client, ctx, base, execution)
    again = (await client.get(f"{base}/reports/{report['id']}", headers=h)).json()
    assert again["version"] == 2


async def test_apply_indicator_suggestion(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx, base, _, execution = await prepare(client)
    h = ctx["headers"]
    report_id = (await generate(client, ctx, base, execution))["result"]["report_id"]
    url = f"{base}/reports/{report_id}/suggestions"

    r = await client.post(f"{url}/0/apply", headers=h, json={"value": "35"})
    assert r.status_code == 200, r.text
    suggestion = r.json()["indicator_suggestions"][0]
    assert suggestion["applied_value_id"] and suggestion["value"] == "35"
    assert (await client.post(f"{url}/0/apply", headers=h, json={})).status_code == 409
    assert (await client.post(f"{url}/5/apply", headers=h, json={})).status_code == 404

    indicators = (await client.get(f"{base}/indicators", headers=h)).json()
    assert indicators[0]["achieved"] == "35.0000"


async def test_workflow_roles_and_export(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx, base, _, execution = await prepare(client)
    h = ctx["headers"]
    report_id = (await generate(client, ctx, base, execution))["result"]["report_id"]
    report = (await client.get(f"{base}/reports/{report_id}", headers=h)).json()
    url = f"{base}/reports/{report['id']}"

    await add_member(client, ctx, "meal@example.org", "meal_officer")
    meal = await login(client, "meal@example.org")
    await add_member(client, ctx, "terrain@example.org", "field_agent")
    field = await login(client, "terrain@example.org")

    sections = report["sections"]
    sections[0]["content"] = "Résumé revu par l'équipe MEAL [S1]."
    body = {"title": report["title"], "sections": sections}
    assert (await client.put(url, headers=field, json=body)).status_code == 403
    r = await client.put(url, headers=meal, json=body)
    assert r.status_code == 200 and r.json()["version"] == 2

    assert (await client.post(f"{url}/submit", headers=meal)).status_code == 200
    assert (await client.put(url, headers=meal, json=body)).status_code == 409
    assert (await client.post(f"{url}/approve", headers=meal)).status_code == 403
    r = await client.post(f"{base}/executions/{execution}/report/generate", headers=h)
    assert r.status_code == 409
    assert (await client.post(f"{url}/return", headers=h, json={"comment": ""})).status_code == 422
    r = await client.post(f"{url}/return", headers=h, json={"comment": "Ajouter les retours"})
    assert r.json()["status"] == "draft" and r.json()["review_comment"] == "Ajouter les retours"
    await client.post(f"{url}/submit", headers=meal)
    r = await client.post(f"{url}/approve", headers=h, json={"comment": "Bon travail"})
    assert r.json()["status"] == "approved" and r.json()["approved_at"]
    versions = (await client.get(f"{url}/versions", headers=h)).json()
    assert [v["version"] for v in versions] == [2, 1]

    r = await client.get(f"{url}/export.docx", headers=field)
    assert r.status_code == 200
    document = docx.Document(BytesIO(r.content))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "Résumé revu par l'équipe MEAL" in text and "Sources" in text
    assert len(document.inline_shapes) == 1  # seule la photo consentie

    r = await client.get(f"{url}/export.pdf", headers=h)
    with pymupdf.open(stream=r.content, filetype="pdf") as pdf:  # type: ignore[no-untyped-call]
        content = "".join(page.get_text() for page in pdf)
        images = sum(len(page.get_images()) for page in pdf)
    assert "Séance de formation" in content and images == 1

    assert (await client.delete(url, headers=meal)).status_code == 403
    assert (await client.delete(url, headers=h)).status_code == 204


async def test_isolation(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx, base, _, execution = await prepare(client)
    report_id = (await generate(client, ctx, base, execution))["result"]["report_id"]
    other = await register(client, "autre@example.org")
    r = await client.get(f"{base}/reports/{report_id}", headers=other["headers"])
    assert r.status_code == 404
