from datetime import date, timedelta
from typing import Any
from uuid import uuid4

from httpx import AsyncClient

from tests.conftest import register
from tests.test_organizations import add_member, login
from tests.test_projects import build_logframe, create_project


async def setup(client: AsyncClient) -> tuple[dict[str, Any], str, dict[str, Any]]:
    ctx = await register(client, "pm@example.org")
    base = f"/api/v1/orgs/{ctx['org_id']}/projects/{await create_project(client, ctx)}"
    return ctx, base, await build_logframe(client, ctx, base)


async def test_feedback_register_and_response_delays(client: AsyncClient) -> None:
    ctx, base, nodes = await setup(client)
    h = ctx["headers"]
    await add_member(client, ctx, "terrain@example.org", "field_agent")
    field = await login(client, "terrain@example.org")
    old = str(date.today() - timedelta(days=20))

    token = str(uuid4())
    body = {
        "received_on": old,
        "channel": "community_meeting",
        "category": "complaint",
        "description": "Les kits sont arrivés incomplets à Kiwanja.",
        "location": "Kiwanja",
        "activity_id": nodes["activity"]["id"],
        "contact": "+243 000 000",
        "client_uuid": token,
    }
    r = await client.post(f"{base}/feedback", headers=field, json=body)
    assert r.status_code == 201, r.text
    complaint = r.json()
    assert complaint["reference"] == "RET-0001" and complaint["sensitive"] is False
    assert complaint["overdue"] is True and complaint["contact"] == "+243 000 000"
    again = await client.post(f"{base}/feedback", headers=field, json=body)
    assert again.status_code == 200 and again.json()["id"] == complaint["id"]

    r = await client.post(
        f"{base}/feedback",
        headers=h,
        json={
            "channel": "hotline",
            "category": "information",
            "description": "Quand a lieu la prochaine distribution ?",
            "anonymous": True,
            "contact": "ne pas garder",
        },
    )
    assert r.json()["reference"] == "RET-0002" and r.json()["contact"] == ""

    url = f"{base}/feedback/{complaint['id']}"
    # L'agent terrain saisit mais ne traite pas.
    assert (
        await client.patch(url, headers=field, json={"status": "in_progress"})
    ).status_code == 403
    r = await client.patch(url, headers=h, json={"status": "responded"})
    assert r.status_code == 422  # pas de réponse renseignée
    r = await client.patch(
        url,
        headers=h,
        json={
            "status": "closed",
            "response": "Kits complétés le lendemain.",
            "responded_on": str(date.today() - timedelta(days=15)),
        },
    )
    closed = r.json()
    assert closed["status"] == "closed" and closed["closed_on"] == str(date.today())
    assert closed["response_days"] == 5 and closed["overdue"] is False

    stats = (await client.get(f"{base}/feedback/stats", headers=h)).json()
    assert stats["total"] == 2 and stats["open"] == 1 and stats["overdue"] == 0
    assert stats["response_rate"] == 0.5 and stats["average_response_days"] == 5
    assert stats["by_category"] == {"complaint": 1, "information": 1}

    listed = (await client.get(f"{base}/feedback?status=closed", headers=h)).json()
    assert [e["reference"] for e in listed] == ["RET-0001"]


async def test_sensitive_feedback_is_confidential(client: AsyncClient) -> None:
    ctx, base, _ = await setup(client)
    h = ctx["headers"]
    await add_member(client, ctx, "terrain@example.org", "field_agent")
    field = await login(client, "terrain@example.org")
    meal_member = await add_member(client, ctx, "meal@example.org", "meal_officer")
    meal = await login(client, "meal@example.org")

    r = await client.post(
        f"{base}/feedback",
        headers=field,
        json={
            "channel": "hotline",
            "category": "sexual_exploitation",
            "description": "Signalement concernant un distributeur.",
            "contact": "confidentiel",
        },
    )
    entry = r.json()
    assert entry["sensitive"] is True
    url = f"{base}/feedback/{entry['id']}"

    # Le chargé MEAL ne voit ni l'entrée ni son détail, seulement qu'elle existe.
    assert (await client.get(f"{base}/feedback", headers=meal)).json() == []
    assert (
        await client.patch(url, headers=meal, json={"status": "in_progress"})
    ).status_code == 404
    stats = (await client.get(f"{base}/feedback/stats", headers=meal)).json()
    assert stats["total"] == 1 and stats["hidden_sensitive"] == 1
    # La personne qui l'a saisie le voit ; le chef de projet aussi, et l'attribue.
    assert len((await client.get(f"{base}/feedback", headers=field)).json()) == 1
    r = await client.patch(url, headers=h, json={"assigned_to": meal_member["user"]["id"]})
    assert r.status_code == 200, r.text
    assert (await client.get(f"{base}/feedback", headers=meal)).json()[0][
        "contact"
    ] == "confidentiel"
    r = await client.patch(url, headers=meal, json={"sensitive": False})
    assert r.status_code == 403

    other = await register(client, "autre@example.org")
    assert (await client.get(f"{base}/feedback", headers=other["headers"])).status_code == 404
    outsider = (await client.get("/api/v1/auth/me", headers=other["headers"])).json()["id"]
    r = await client.patch(url, headers=h, json={"assigned_to": outsider})
    assert r.status_code == 422


async def test_lessons_register(client: AsyncClient) -> None:
    ctx, base, nodes = await setup(client)
    h = ctx["headers"]
    r = await client.post(
        f"{base}/lessons",
        headers=h,
        json={
            "title": "Prévoir des salles plus grandes",
            "description": "Deux groupes au lieu d'un faute de salle.",
            "recommendation": "Visiter les lieux avant la formation.",
            "tags": ["Logistique", " logistique ", "Formation"],
            "activity_id": nodes["activity"]["id"],
        },
    )
    assert r.status_code == 201, r.text
    lesson = r.json()
    assert lesson["tags"] == ["logistique", "formation"] and lesson["project_code"] == "P1"
    await client.post(
        f"{base}/lessons",
        headers=h,
        json={"title": "Impliquer les chefs locaux", "tags": ["communauté"]},
    )

    assert len((await client.get(f"{base}/lessons", headers=h)).json()) == 2
    found = (await client.get(f"{base}/lessons?q=SALLE", headers=h)).json()
    assert [x["id"] for x in found] == [lesson["id"]]
    found = (await client.get(f"{base}/lessons?tag=communauté", headers=h)).json()
    assert [x["title"] for x in found] == ["Impliquer les chefs locaux"]
    org_wide = (await client.get(f"/api/v1/orgs/{ctx['org_id']}/lessons", headers=h)).json()
    assert len(org_wide) == 2

    r = await client.patch(f"{base}/lessons/{lesson['id']}", headers=h, json={"tags": ["salle"]})
    assert r.json()["tags"] == ["salle"] and r.json()["title"] == lesson["title"]

    await add_member(client, ctx, "terrain@example.org", "field_agent")
    field = await login(client, "terrain@example.org")
    assert (await client.get(f"{base}/lessons", headers=field)).status_code == 200
    assert (
        await client.post(f"{base}/lessons", headers=field, json={"title": "Non autorisé"})
    ).status_code == 403
    r = await client.post(
        f"{base}/lessons",
        headers=h,
        json={"title": "Source inconnue", "source_report_id": str(uuid4())},
    )
    assert r.status_code == 404
    assert (await client.delete(f"{base}/lessons/{lesson['id']}", headers=h)).status_code == 204
