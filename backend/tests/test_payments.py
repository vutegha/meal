from typing import Any

from httpx import AsyncClient

from tests.conftest import register
from tests.test_admin import platform_admin
from tests.test_billing import billing_of, signup


async def announce(client: AsyncClient, ctx: dict[str, Any], **body: Any) -> dict[str, Any]:
    r = await client.post(
        f"/api/v1/orgs/{ctx['org_id']}/billing/checkout", headers=ctx["headers"], json=body
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


async def test_online_payment_gets_a_receipt(client: AsyncClient) -> None:
    ctx = await register(client, "online@x.org")
    out = await announce(client, ctx, plan="team", cycle="annual")
    payment = out["payment"]
    assert (payment["status"], payment["method"]) == ("paid", "online")
    assert payment["receipt_number"].startswith("WM-")
    assert payment["paid_at"] is not None

    url = f"/api/v1/orgs/{ctx['org_id']}/billing/payments/{payment['id']}/receipt.pdf"
    r = await client.get(url, headers=ctx["headers"])
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert payment["receipt_number"] in r.headers["content-disposition"]

    # Les numéros de reçu se suivent.
    second = (await announce(client, ctx, plan="team", cycle="annual"))["payment"]
    assert int(second["receipt_number"][-6:]) == int(payment["receipt_number"][-6:]) + 1


async def test_bank_transfer_waits_for_confirmation(client: AsyncClient) -> None:
    admin = await platform_admin(client)
    ctx = await register(client, "transfer@x.org")
    catalog = (await client.get("/api/v1/billing/plans")).json()
    assert catalog["payment_instructions"]

    out = await announce(client, ctx, plan="institution", cycle="annual", method="bank_transfer")
    payment = out["payment"]
    assert (payment["status"], payment["receipt_number"]) == ("pending", None)
    assert payment["reference"].startswith("WM-")
    # Rien ne change tant que le virement n'est pas reçu.
    assert out["subscription"]["plan"] == "team"
    assert out["subscription"]["status"] == "trialing"
    org_url = f"/api/v1/orgs/{ctx['org_id']}/billing/payments/{payment['id']}"
    assert (await client.get(f"{org_url}/receipt.pdf", headers=ctx["headers"])).status_code == 404

    listing = await client.get(
        "/api/v1/admin/payments", headers=admin["headers"], params={"status": "pending"}
    )
    assert listing.status_code == 200, listing.text
    data = listing.json()
    assert data["summary"]["pending"] == 1
    assert data["summary"]["pending_amount"] == "2490.00"
    [row] = data["items"]
    assert (row["organization_name"], row["paid_by_email"]) == ("Org", "transfer@x.org")

    r = await client.post(
        f"/api/v1/admin/payments/{payment['id']}/confirm",
        headers=admin["headers"],
        json={"note": "Reçu sur le compte Rawbank"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "paid"
    assert r.json()["receipt_number"]
    sub = await billing_of(client, ctx)
    assert (sub["plan"], sub["cycle"], sub["status"]) == ("institution", "annual", "active")

    r = await client.post(
        f"/api/v1/admin/payments/{payment['id']}/confirm", headers=admin["headers"], json={}
    )
    assert r.status_code == 409
    r = await client.get(
        f"/api/v1/admin/payments/{payment['id']}/receipt.pdf", headers=admin["headers"]
    )
    assert r.content.startswith(b"%PDF")


async def test_customer_cancels_an_announced_payment(client: AsyncClient) -> None:
    ctx = await signup(client, "mm@x.org", account_type="individual", cycle="usage")
    payment = (
        await announce(client, ctx, plan="solo", cycle="usage", pack=50, method="mobile_money")
    )["payment"]
    url = f"/api/v1/orgs/{ctx['org_id']}/billing/payments/{payment['id']}/cancel"
    r = await client.post(url, headers=ctx["headers"])
    assert r.json()["status"] == "canceled"
    assert (await client.post(url, headers=ctx["headers"])).status_code == 409
    assert (await billing_of(client, ctx))["credits"] == 5


async def test_admin_records_and_refunds_payments(client: AsyncClient) -> None:
    admin = await platform_admin(client)
    ctx = await signup(client, "cash@x.org", account_type="individual", cycle="usage")
    r = await client.post(
        f"/api/v1/admin/subscriptions/{ctx['org_id']}/payments",
        headers=admin["headers"],
        json={
            "plan": "solo",
            "cycle": "usage",
            "pack": 50,
            "amount": "90",
            "method": "mobile_money",
            "reference": "MP241013.1542.A12345",
            "note": "Remise ONG partenaire",
        },
    )
    assert r.status_code == 201, r.text
    payment = r.json()
    assert (payment["status"], payment["amount"], payment["reference"]) == (
        "paid",
        "90.00",
        "MP241013.1542.A12345",
    )
    assert (await billing_of(client, ctx))["credits"] == 55

    r = await client.post(
        f"/api/v1/admin/payments/{payment['id']}/refund", headers=admin["headers"], json={}
    )
    assert r.status_code == 422
    r = await client.post(
        f"/api/v1/admin/payments/{payment['id']}/refund",
        headers=admin["headers"],
        json={"note": "Doublon"},
    )
    assert r.json()["status"] == "refunded"
    assert (await billing_of(client, ctx))["credits"] == 5
    summary = (await client.get("/api/v1/admin/payments", headers=admin["headers"])).json()
    assert summary["summary"]["refunded_last_30_days"] == "90.00"

    # Visible et tracé côté espace
    payments = (
        await client.get(f"/api/v1/orgs/{ctx['org_id']}/billing/payments", headers=ctx["headers"])
    ).json()
    assert [p["status"] for p in payments] == ["refunded"]

    # Réservé à l'administration de la plateforme
    r = await client.post(
        f"/api/v1/admin/payments/{payment['id']}/refund",
        headers=ctx["headers"],
        json={"note": "Moi-même"},
    )
    assert r.status_code == 404
