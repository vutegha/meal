from decimal import Decimal
from typing import Any

import pymupdf
from httpx import AsyncClient

from tests.conftest import register
from tests.test_organizations import add_member, login
from tests.test_projects import build_logframe, create_project


async def setup(client: AsyncClient) -> tuple[dict[str, Any], str, dict[str, Any]]:
    ctx = await register(client, "pm@example.org")
    base = f"/api/v1/orgs/{ctx['org_id']}/projects/{await create_project(client, ctx)}"
    return ctx, base, await build_logframe(client, ctx, base)


async def test_period_targets(client: AsyncClient) -> None:
    ctx, base, nodes = await setup(client)
    h = ctx["headers"]
    r = await client.post(
        f"{base}/indicators",
        headers=h,
        json={
            "node_id": nodes["output"]["id"],
            "code": "I1",
            "name": "Membres formés",
            "target": 600,
            "period_targets": [
                {"period_start": "2026-07-01", "period_end": "2026-12-31", "target": 400},
                {"period_start": "2026-01-01", "period_end": "2026-06-30", "target": 200},
            ],
        },
    )
    assert r.status_code == 201, r.text
    indicator = r.json()
    # Triées par période.
    assert [t["target"] for t in indicator["period_targets"]] == ["200", "400"]
    url = f"{base}/indicators/{indicator['id']}"
    for start, end, value in (
        ("2026-01-01", "2026-03-31", 90),
        ("2026-04-01", "2026-06-30", 60),
        ("2026-07-01", "2026-09-30", 100),
    ):
        r = await client.post(
            f"{url}/values",
            headers=h,
            json={"period_start": start, "period_end": end, "value": value},
        )
        assert r.status_code == 201, r.text

    listed = (await client.get(f"{base}/indicators", headers=h)).json()[0]
    first, second = listed["period_targets"]
    assert Decimal(first["achieved"]) == 150 and first["achievement_rate"] == 0.75
    assert Decimal(second["achieved"]) == 100 and second["achievement_rate"] == 0.25
    assert Decimal(listed["achieved"]) == 250

    r = await client.patch(
        url,
        headers=h,
        json={
            "period_targets": [
                {"period_start": "2026-01-01", "period_end": "2026-06-30", "target": 200},
                {"period_start": "2026-06-01", "period_end": "2026-12-31", "target": 400},
            ]
        },
    )
    assert r.status_code == 422  # chevauchement
    r = await client.patch(url, headers=h, json={"period_targets": []})
    assert r.json()["period_targets"] == []


async def test_expenses_in_other_currency(client: AsyncClient) -> None:
    ctx, base, nodes = await setup(client)
    h = ctx["headers"]
    line = (
        await client.post(
            f"{base}/budget/lines",
            headers=h,
            json={
                "activity_id": nodes["activity"]["id"],
                "label": "Location de salle",
                "quantity": 1,
                "unit_cost": 1000,
            },
        )
    ).json()
    expenses = f"{base}/budget/lines/{line['id']}/expenses"

    r = await client.post(
        expenses, headers=h, json={"amount": 100000, "currency": "CDF", "spent_on": "2026-03-10"}
    )
    assert r.status_code == 422 and "Taux de change CDF" in r.json()["detail"]

    await add_member(client, ctx, "finance@example.org", "finance")
    finance = await login(client, "finance@example.org")
    rates = [
        {"currency": "CDF", "rate": "0.00035", "valid_from": "2026-01-01"},
        {"currency": "CDF", "rate": "0.0004", "valid_from": "2026-03-01"},
        {"currency": "USD", "rate": "0.92", "valid_from": "2026-01-01"},
    ]
    r = await client.put(f"{base}/exchange-rates", headers=finance, json=rates)
    assert r.status_code == 200, r.text
    assert len(r.json()["exchange_rates"]) == 3
    bad = [{"currency": "EUR", "rate": "1", "valid_from": "2026-01-01"}]
    assert (await client.put(f"{base}/exchange-rates", headers=h, json=bad)).status_code == 422

    # Taux en vigueur à la date de la dépense.
    r = await client.post(
        expenses, headers=h, json={"amount": 100000, "currency": "CDF", "spent_on": "2026-03-10"}
    )
    assert r.status_code == 201, r.text
    expense = r.json()
    assert expense["amount"] == "40.00" and expense["original_amount"] == "100000"
    assert expense["currency"] == "CDF" and Decimal(expense["exchange_rate"]) == Decimal("0.0004")
    r = await client.post(
        expenses, headers=h, json={"amount": 100000, "currency": "CDF", "spent_on": "2026-02-10"}
    )
    assert r.json()["amount"] == "35.00"
    # Taux saisi pour la dépense, et devise du projet sans conversion.
    r = await client.post(
        expenses,
        headers=h,
        json={"amount": 10, "currency": "USD", "exchange_rate": "0.9", "spent_on": "2026-03-10"},
    )
    assert r.json()["amount"] == "9.00"
    r = await client.post(
        expenses, headers=h, json={"amount": 16, "currency": "EUR", "spent_on": "2026-03-10"}
    )
    assert r.json()["amount"] == "16.00" and r.json()["currency"] == ""

    summary = (await client.get(f"{base}/budget/summary", headers=h)).json()
    assert summary["spent"] == "100.00"


async def test_export_pdf_and_docx(client: AsyncClient) -> None:
    ctx, base, nodes = await setup(client)
    h = ctx["headers"]
    await client.post(
        f"{base}/indicators",
        headers=h,
        json={
            "node_id": nodes["output"]["id"],
            "code": "I1",
            "name": "Membres formés",
            "target": 600,
            "period_targets": [
                {"period_start": "2026-01-01", "period_end": "2026-06-30", "target": 200}
            ],
        },
    )
    await client.put(
        f"{base}/exchange-rates",
        headers=h,
        json=[{"currency": "CDF", "rate": "0.0004", "valid_from": "2026-01-01"}],
    )
    r = await client.get(f"{base}/export.pdf", headers=h)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    with pymupdf.open(stream=r.content, filetype="pdf") as pdf:
        text = "".join(pdf[i].get_text() for i in range(pdf.page_count))
    for expected in ("Cadre logique", "Membres formés", "Cibles par période", "CDF", "Page 1"):
        assert expected in text, expected
    r = await client.get(f"{base}/export.docx", headers=h)
    assert r.status_code == 200 and r.content[:2] == b"PK"
    assert (await client.get(f"{base}/export.odt", headers=h)).status_code == 404
