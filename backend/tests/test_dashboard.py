from httpx import AsyncClient

from tests.test_executions import execution_body, setup


async def test_org_dashboard_filters(client: AsyncClient) -> None:
    ctx, base, nodes, line = await setup(client)
    h = ctx["headers"]
    activity = nodes["activity"]["id"]
    for body in (
        execution_body(activity, status="completed"),
        execution_body(
            activity,
            start_date="2026-05-02",
            end_date=None,
            location="Rutshuru",
            participants={"women": 0, "men": 5, "girls": 10, "boys": 0, "with_disability": 0},
        ),
    ):
        r = await client.post(f"{base}/executions", headers=h, json=body)
        assert r.status_code == 201, r.text
    r = await client.post(
        f"{base}/budget/lines/{line}/expenses",
        headers=h,
        json={"amount": "1500", "spent_on": "2026-03-16", "reference": "PC-1"},
    )
    assert r.status_code == 201, r.text

    url = f"/api/v1/orgs/{ctx['org_id']}/dashboard"
    data = (await client.get(url, headers=h)).json()
    assert data["options"]["years"] == [2026]
    assert data["options"]["zones"] == ["Goma", "Rutshuru"]
    assert data["options"]["locations"] == ["Kiwanja", "Rutshuru"]
    assert data["projects"] == 1 and data["executions"] == 2
    assert data["completed_executions"] == 1
    assert data["people"]["total"] == 51 and data["people"]["women"] == 22
    assert data["spending"] == [{"currency": "EUR", "amount": "1500.00"}]
    assert [m["key"] for m in data["by_month"]] == ["2026-03", "2026-05"]

    may = (await client.get(url, headers=h, params={"year": 2026, "month": 5})).json()
    assert may["executions"] == 1 and may["people"]["total"] == 15 and may["spending"] == []

    girls = (await client.get(url, headers=h, params={"beneficiary": "girls"})).json()
    assert girls["executions"] == 1 and girls["people"]["total"] == 10

    kiwanja = (await client.get(url, headers=h, params={"location": "Kiwanja"})).json()
    assert kiwanja["executions"] == 1 and kiwanja["by_location"][0]["people"] == 36

    # Vue restreinte : un effectif de 1 à 4 est caché, pas un effectif plus grand.
    disabled = (await client.get(url, headers=h, params={"beneficiary": "with_disability"})).json()
    assert disabled["people"]["total"] == 0 and "total" in disabled["people"]["masked"]
    assert disabled["by_location"] == [
        {"key": "Kiwanja", "label": "Kiwanja", "executions": 1, "people": 0, "masked": True}
    ]
    assert data["people"]["with_disability"] == 3 and data["people"]["masked"] == []
    rutshuru = (await client.get(url, headers=h, params={"location": "Rutshuru"})).json()
    assert rutshuru["people"]["total"] == 15 and rutshuru["people"]["masked"] == []

    elsewhere = (await client.get(url, headers=h, params={"zone": "Bunia"})).json()
    assert elsewhere["projects"] == 0 and elsewhere["executions"] == 0
