import json
import logging

from httpx import AsyncClient

from app.core.observability import JsonFormatter, _strip_event, scrub


def test_scrub_masks_phones_and_emails() -> None:
    text = "Appel de awa@example.org au +243 970 000 000 puis au 0812345678, dossier RET-0012"
    assert scrub(text) == "Appel de [e-mail] au [téléphone] puis au [téléphone], dossier RET-0012"


def test_json_log_line_has_no_personal_data() -> None:
    record = logging.makeLogRecord(
        {"msg": "SMS reçu de %s", "args": ("+243970000000",), "levelname": "INFO"}
    )
    record.request_id = "abc"
    line = json.loads(JsonFormatter().format(record))
    assert line["message"] == "SMS reçu de [téléphone]" and line["request_id"] == "abc"


def test_error_report_keeps_neither_body_nor_user() -> None:
    event = {
        "user": {"email": "awa@example.org"},
        "request": {
            "method": "GET",
            "url": "https://meal.example.org/api/v1/orgs/x/personal-data?q=Kahindo",
            "headers": {"Authorization": "Bearer secret"},
            "data": {"contact": "+243970000000"},
        },
        "exception": {
            "values": [
                {
                    "value": "contact +243970000000 refusé",
                    "stacktrace": {"frames": [{"vars": {"contact": "+243970000000"}}]},
                }
            ]
        },
    }
    cleaned = _strip_event(event, {})
    assert cleaned is not None
    assert "user" not in cleaned
    assert cleaned["request"] == {
        "method": "GET",
        "url": "https://meal.example.org/api/v1/orgs/x/personal-data",
    }
    value = cleaned["exception"]["values"][0]
    assert (
        value["value"] == "contact [téléphone] refusé"
        and "vars" not in value["stacktrace"]["frames"][0]
    )


async def test_request_id_and_metrics(client: AsyncClient) -> None:
    r = await client.get("/health", headers={"X-Request-ID": "terrain-42"})
    assert r.headers["x-request-id"] == "terrain-42"
    assert len((await client.get("/health")).headers["x-request-id"]) == 32
    metrics = (await client.get("/metrics")).text
    assert 'wemeal_http_requests_total{method="GET",route="/health",status="200"}' in metrics
