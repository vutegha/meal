from io import BytesIO

import docx
from httpx import AsyncClient

from tests.fake_llm import FakeLLM
from tests.test_organizations import add_member, login
from tests.test_reports import generate, prepare
from tests.test_tor import fake_llm  # noqa: F401

__all__ = ["fake_llm"]

MARCH = {"kind": "quarterly", "period_start": "2026-01-01", "period_end": "2026-03-31"}


async def test_periodic_report_aggregates_the_period(
    client: AsyncClient, fake_llm: FakeLLM
) -> None:
    ctx, base, nodes, execution = await prepare(client)
    h = ctx["headers"]
    report_id = (await generate(client, ctx, base, execution))["result"]["report_id"]
    await client.post(f"{base}/reports/{report_id}/submit", headers=h)
    await client.post(f"{base}/reports/{report_id}/approve", headers=h, json={})
    indicator = (await client.get(f"{base}/indicators", headers=h)).json()[0]["id"]
    await client.post(
        f"{base}/indicators/{indicator}/values",
        headers=h,
        json={"period_start": "2026-03-14", "period_end": "2026-03-16", "value": 36},
    )
    await client.post(
        f"{base}/feedback",
        headers=h,
        json={
            "received_on": "2026-03-17",
            "channel": "community_meeting",
            "category": "complaint",
            "description": "Horaires de formation trop tardifs.",
        },
    )
    await client.post(
        f"{base}/feedback",
        headers=h,
        json={
            "received_on": "2026-03-18",
            "channel": "hotline",
            "category": "fraud",
            "description": "Détail confidentiel à ne jamais citer.",
        },
    )

    assert (
        await client.post(
            f"{base}/periodic-reports", headers=h, json={**MARCH, "period_end": "2025-12-01"}
        )
    ).status_code == 422
    r = await client.post(
        f"{base}/periodic-reports",
        headers=h,
        json={**MARCH, "instructions": "Insister sur les AVEC"},
    )
    assert r.status_code == 201, r.text
    periodic = r.json()
    assert periodic["title"] == "Rapport trimestriel du 01/01/2026 au 31/03/2026"
    sections = {s["key"]: s["content"] for s in periodic["sections"]}
    assert (
        "Formation AVEC de Kiwanja" in sections["activites"]
        and "| **36** |" in sections["activites"]
    )
    assert "Approuvé" in sections["activites"]
    assert "| I1 |" in sections["indicateurs"] and "| 36 |" in sections["indicateurs"]
    assert "3 200" in sections["budget"] and "19 200" in sections["budget"]
    assert sections["resume"] == "[À compléter]"

    url = f"{base}/periodic-reports/{periodic['id']}"
    r = await client.post(f"{url}/generate", headers=h)
    assert r.status_code == 202, r.text
    job = (
        await client.get(f"/api/v1/orgs/{ctx['org_id']}/jobs/{r.json()['id']}", headers=h)
    ).json()
    assert job["status"] == "succeeded", job["error"]

    context = fake_llm.calls[-1]["content"][0]["text"]
    assert '<source ref="S1" type="rapport_activite">' in context
    assert "Horaires de formation trop tardifs" in context
    assert "Détail confidentiel" not in context and "1 retour(s) sensible(s)" in context
    assert "Insister sur les AVEC" in fake_llm.calls[-1]["content"][1]["text"]
    assert "- activites :" not in fake_llm.calls[-1]["content"][1]["text"]

    periodic = (await client.get(url, headers=h)).json()
    assert periodic["title"] == "Rapport trimestriel T1 2026" and periodic["version"] == 2
    sections = {s["key"]: s["content"] for s in periodic["sections"]}
    assert sections["redevabilite"] == "Un retour reçu et traité [S2] [source introuvable]."
    assert "ignoré" not in sections["budget"]
    assert [s["label"] for s in periodic["sources"]] == [
        "Rapport d'activité : A1.1.1 Formation AVEC de Kiwanja (approuvé)",
        "Registre des plaintes et retours",
    ]
    assert periodic["missing_information"] == ["Évolution du contexte sécuritaire"]

    # Une dépense ajoutée ensuite : les tableaux se recalculent sans toucher au texte.
    line = (await client.get(f"{base}/budget/lines", headers=h)).json()[0]["id"]
    await client.post(
        f"{base}/executions/{execution}/expenses",
        headers=h,
        json={"budget_line_id": line, "amount": "800", "spent_on": "2026-03-20"},
    )
    r = await client.post(f"{url}/refresh", headers=h)
    sections = {s["key"]: s["content"] for s in r.json()["sections"]}
    assert "4 000" in sections["budget"] and sections["resume"].startswith("Trois AVEC")
    assert r.json()["version"] == 3

    r = await client.get(f"{url}/export.docx", headers=h)
    text = "\n".join(p.text for p in docx.Document(BytesIO(r.content)).paragraphs)
    assert "Rapport trimestriel T1 2026" in text and "Sources" in text


async def test_periodic_workflow_and_roles(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx, base, _, _ = await prepare(client)
    h = ctx["headers"]
    await add_member(client, ctx, "meal@example.org", "meal_officer")
    meal = await login(client, "meal@example.org")
    await add_member(client, ctx, "terrain@example.org", "field_agent")
    field = await login(client, "terrain@example.org")

    assert (
        await client.post(f"{base}/periodic-reports", headers=field, json=MARCH)
    ).status_code == 403
    periodic = (await client.post(f"{base}/periodic-reports", headers=meal, json=MARCH)).json()
    url = f"{base}/periodic-reports/{periodic['id']}"
    body = {"title": "Rapport T1", "sections": periodic["sections"]}
    assert (await client.put(url, headers=meal, json=body)).json()["version"] == 2
    assert (await client.post(f"{url}/submit", headers=meal)).status_code == 200
    assert (await client.post(f"{url}/generate", headers=meal)).status_code == 409
    assert (await client.put(url, headers=meal, json=body)).status_code == 409
    assert (await client.post(f"{url}/approve", headers=meal)).status_code == 403
    assert (await client.post(f"{url}/approve", headers=h, json={})).json()["status"] == "approved"
    assert (await client.post(f"{url}/reopen", headers=h)).json()["status"] == "draft"
    assert (await client.post(f"{url}/archive", headers=h)).status_code == 404
    versions = (await client.get(f"{url}/versions", headers=field)).json()
    assert [v["version"] for v in versions] == [2, 1]
    listed = (await client.get(f"{base}/periodic-reports", headers=field)).json()
    assert [r["title"] for r in listed] == ["Rapport T1"]
    assert (await client.delete(url, headers=meal)).status_code == 403
    assert (await client.delete(url, headers=h)).status_code == 204
