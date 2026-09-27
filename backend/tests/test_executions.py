from io import BytesIO
from typing import Any
from uuid import uuid4

from httpx import AsyncClient
from PIL import Image

from tests.conftest import register
from tests.test_organizations import add_member, login
from tests.test_projects import build_logframe, create_project


def photo() -> bytes:
    image = Image.new("RGB", (1600, 1200), "green")
    exif = image.getexif()
    exif.get_ifd(0x8769)[0x9003] = "2026:03:14 10:30:00"
    exif[0x8825] = {1: "S", 2: (1.0, 40.0, 30.0), 3: "E", 4: (29.0, 15.0, 0.0)}
    buffer = BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    return buffer.getvalue()


async def setup(client: AsyncClient) -> tuple[dict[str, Any], str, dict[str, Any], str]:
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
            "unit": "",
            "unit_cost": "800",
            "frequency": "6",
            "donor_line_code": "1.1",
        },
    )
    return ctx, base, nodes, r.json()["id"]


def execution_body(activity_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "activity_id": activity_id,
        "title": "Formation AVEC de Kiwanja",
        "start_date": "2026-03-14",
        "end_date": "2026-03-16",
        "location": "Kiwanja",
        "participants": {"women": 22, "men": 14, "girls": 0, "boys": 0, "with_disability": 3},
        "notes": "Deux groupes au lieu d'un, faute de salle assez grande.",
        **extra,
    }


async def test_execution_is_idempotent_and_validated(client: AsyncClient) -> None:
    ctx, base, nodes, _ = await setup(client)
    await add_member(client, ctx, "terrain@example.org", "field_agent")
    field = await login(client, "terrain@example.org")
    activity = nodes["activity"]["id"]

    body = execution_body(activity, client_uuid=str(uuid4()))
    r = await client.post(f"{base}/executions", headers=field, json=body)
    assert r.status_code == 201, r.text
    execution = r.json()
    assert execution["participants_total"] == 36
    assert execution["planned"] == "19200.00" and execution["spent"] == "0"

    # Renvoi de la même saisie après une coupure réseau : pas de doublon.
    again = await client.post(f"{base}/executions", headers=field, json=body)
    assert again.status_code == 200 and again.json()["id"] == execution["id"]

    bad = execution_body(nodes["output"]["id"])
    assert (await client.post(f"{base}/executions", headers=field, json=bad)).status_code == 422
    bad = execution_body(activity, participants={"women": 1, "with_disability": 2})
    assert (await client.post(f"{base}/executions", headers=field, json=bad)).status_code == 422
    bad = execution_body(activity, end_date="2026-03-01")
    assert (await client.post(f"{base}/executions", headers=field, json=bad)).status_code == 422

    r = await client.patch(
        f"{base}/executions/{execution['id']}", headers=field, json={"status": "completed"}
    )
    assert r.json()["status"] == "completed" and r.json()["title"] == "Formation AVEC de Kiwanja"

    listed = (await client.get(f"{base}/executions?activity_id={activity}", headers=field)).json()
    assert [e["id"] for e in listed] == [execution["id"]]


async def test_evidence_photo_and_document(client: AsyncClient) -> None:
    ctx, base, nodes, _ = await setup(client)
    h = ctx["headers"]
    execution = (
        await client.post(
            f"{base}/executions", headers=h, json=execution_body(nodes["activity"]["id"])
        )
    ).json()
    url = f"{base}/executions/{execution['id']}/evidence"

    token = str(uuid4())
    r = await client.post(
        url,
        headers=h,
        files={"file": ("seance.jpg", photo(), "image/jpeg")},
        data={"caption": "Séance de formation", "consent_given": "true", "client_uuid": token},
    )
    assert r.status_code == 201, r.text
    picture = r.json()
    assert picture["kind"] == "photo" and picture["has_thumbnail"]
    assert picture["taken_at"].startswith("2026-03-14T10:30")
    assert picture["latitude"] == "-1.675000" and picture["longitude"] == "29.250000"
    assert picture["consent_given"] is True
    again = await client.post(
        url,
        headers=h,
        files={"file": ("seance.jpg", photo(), "image/jpeg")},
        data={"client_uuid": token},
    )
    assert again.status_code == 200 and again.json()["id"] == picture["id"]

    thumb = await client.get(f"{base}/evidence/{picture['id']}/thumbnail", headers=h)
    assert thumb.headers["content-type"] == "image/webp"
    assert max(Image.open(BytesIO(thumb.content)).size) == 800
    assert not Image.open(BytesIO(thumb.content)).getexif()  # aucune métadonnée GPS
    original = await client.get(f"{base}/evidence/{picture['id']}/file", headers=h)
    assert original.content == photo()

    minutes = "Compte rendu : 36 participants, dont 22 femmes. Les AVEC ont élu leurs comités."
    r = await client.post(
        url,
        headers=h,
        files={"file": ("compte-rendu.txt", minutes.encode(), "text/plain")},
        data={"kind": "minutes"},
    )
    assert r.json()["kind"] == "minutes" and r.json()["page_count"] == 1
    assert (
        await client.get(f"{base}/evidence/{r.json()['id']}/thumbnail", headers=h)
    ).status_code == 404

    bad = await client.post(
        url, headers=h, files={"file": ("virus.exe", b"MZ", "application/x-msdownload")}
    )
    assert bad.status_code == 415
    r = await client.patch(
        f"{base}/evidence/{picture['id']}", headers=h, json={"consent_given": False}
    )
    assert r.json()["consent_given"] is False

    detail = (await client.get(f"{base}/executions/{execution['id']}", headers=h)).json()
    assert [e["kind"] for e in detail["evidence"]] == ["photo", "minutes"]
    assert detail["evidence_count"] == 2


async def test_expenses_roles_and_isolation(client: AsyncClient) -> None:
    ctx, base, nodes, line = await setup(client)
    h = ctx["headers"]
    execution = (
        await client.post(
            f"{base}/executions", headers=h, json=execution_body(nodes["activity"]["id"])
        )
    ).json()
    exe = f"{base}/executions/{execution['id']}"

    await add_member(client, ctx, "finance@example.org", "finance")
    finance = await login(client, "finance@example.org")
    r = await client.post(
        f"{exe}/expenses",
        headers=finance,
        json={
            "budget_line_id": line,
            "amount": "3200",
            "spent_on": "2026-03-16",
            "reference": "PC-12",
        },
    )
    assert r.status_code == 201, r.text
    detail = (await client.get(exe, headers=h)).json()
    assert detail["spent"] == "3200.00" and len(detail["expenses"]) == 1
    summary = (await client.get(f"{base}/budget/summary", headers=h)).json()
    assert summary["spent"] == "3200.00"

    other_project = await create_project(client, ctx, code="P2")
    other_line = (
        await client.post(
            f"/api/v1/orgs/{ctx['org_id']}/projects/{other_project}/budget/lines",
            headers=h,
            json={
                "label": "X",
                "activity_id": None,
                "quantity": "1",
                "unit": "",
                "unit_cost": "1",
                "frequency": "1",
                "donor_line_code": "",
            },
        )
    ).json()["id"]
    r = await client.post(
        f"{exe}/expenses",
        headers=h,
        json={"budget_line_id": other_line, "amount": "1", "spent_on": "2026-03-16"},
    )
    assert r.status_code == 404

    # Retrait d'une pièce : par son auteur ou un responsable, pas par un autre agent.
    await add_member(client, ctx, "agent1@example.org", "field_agent")
    await add_member(client, ctx, "agent2@example.org", "field_agent")
    agent1, agent2 = (
        await login(client, "agent1@example.org"),
        await login(client, "agent2@example.org"),
    )
    piece = (
        await client.post(
            f"{exe}/evidence", headers=agent1, files={"file": ("p.jpg", photo(), "image/jpeg")}
        )
    ).json()
    assert (
        await client.delete(f"{base}/evidence/{piece['id']}", headers=agent2)
    ).status_code == 403
    assert (
        await client.delete(f"{base}/evidence/{piece['id']}", headers=agent1)
    ).status_code == 204

    await add_member(client, ctx, "lecteur@example.org", "viewer")
    viewer = await login(client, "lecteur@example.org")
    assert (await client.get(exe, headers=viewer)).status_code == 200
    body = execution_body(nodes["activity"]["id"])
    assert (await client.post(f"{base}/executions", headers=viewer, json=body)).status_code == 403
    assert (await client.delete(exe, headers=agent1)).status_code == 403

    other = await register(client, "autre@example.org")
    assert (await client.get(exe, headers=other["headers"])).status_code == 404

    assert (await client.delete(exe, headers=h)).status_code == 204
    summary = (await client.get(f"{base}/budget/summary", headers=h)).json()
    assert summary["spent"] == "3200.00"  # la dépense reste, détachée de l'exécution
