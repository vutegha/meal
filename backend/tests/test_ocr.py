import base64
from io import BytesIO

import pymupdf
from httpx import AsyncClient
from PIL import Image

from tests.conftest import register
from tests.fake_llm import FakeLLM
from tests.test_ai import upload
from tests.test_projects import create_project
from tests.test_tor import fake_llm  # noqa: F401

__all__ = ["fake_llm"]


def scanned_pdf() -> bytes:
    """Une page de texte, puis une page « scannée » (image seule, sans texte)."""
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "Proposition de projet : résilience économique " * 3)
    scan = pdf.new_page()
    image = Image.new("RGB", (400, 300), "white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    scan.insert_image(pymupdf.Rect(50, 50, 450, 350), stream=buffer.getvalue())
    return bytes(pdf.tobytes())


async def setup(client: AsyncClient) -> tuple[dict[str, str], str]:
    ctx = await register(client, "ocr@example.org")
    base = f"/api/v1/orgs/{ctx['org_id']}/projects/{await create_project(client, ctx)}"
    return ctx, base


async def test_scanned_pages_are_read(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx, base = await setup(client)
    r = await upload(client, ctx, base, "rapport.pdf", scanned_pdf(), "application/pdf")
    assert r.status_code == 201, r.text
    document = r.json()
    # Avec JOBS_INLINE, la reconnaissance est déjà faite au retour de l'import.
    assert document["status"] == "extracted", document
    assert document["page_count"] == 2
    [call] = fake_llm.calls
    image = call["content"][0]
    assert image["type"] == "image" and image["source"]["media_type"] == "image/png"
    assert Image.open(BytesIO(base64.b64decode(image["source"]["data"]))).format == "PNG"
    assert "Page 2" in call["content"][1]["text"]

    # Le texte reconnu rejoint la recherche plein texte.
    r = await client.get(
        f"{base}/documents/search", params={"q": "participants"}, headers=ctx["headers"]
    )
    hits = r.json()
    assert hits and hits[0]["page"] == 2


async def test_photographed_page(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx, base = await setup(client)
    buffer = BytesIO()
    Image.new("RGB", (3000, 2000), "white").save(buffer, format="JPEG")
    r = await upload(client, ctx, base, "liste.jpg", buffer.getvalue(), "image/jpeg")
    assert r.json()["status"] == "extracted"
    sent = base64.b64decode(fake_llm.calls[0]["content"][0]["source"]["data"])
    assert max(Image.open(BytesIO(sent)).size) == 1600  # réduite avant envoi


async def test_ocr_failure_is_reported(client: AsyncClient, fake_llm: FakeLLM) -> None:
    ctx, base = await setup(client)
    fake_llm.error = "Service IA injoignable. Vérifiez la connexion réseau."
    r = await upload(client, ctx, base, "rapport.pdf", scanned_pdf(), "application/pdf")
    document = r.json()
    assert document["status"] == "failed"
    assert "injoignable" in document["error"]
