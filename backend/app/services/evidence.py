"""Traitement des preuves déposées : type, métadonnées EXIF des photos, vignette, texte."""

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from io import BytesIO
from typing import Any

from app.documents.extract import ExtractionError, detect_kind, extract_pages

IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
IMAGE_EXTENSIONS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
THUMBNAIL_SIZE = 800
# Balises EXIF utiles (numéros standard).
_DATETIME_ORIGINAL = 0x9003
_EXIF_IFD = 0x8769
_GPS_IFD = 0x8825


@dataclass
class ProcessedFile:
    content_type: str
    sha256: str
    is_image: bool
    thumbnail: bytes | None = None
    taken_at: datetime | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    text: str = ""
    page_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class UnsupportedFile(Exception):
    pass


def image_type(filename: str, content_type: str | None) -> str | None:
    if content_type in IMAGE_TYPES:
        return content_type
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return IMAGE_EXTENSIONS.get(suffix)


def _degrees(value: Any, ref: str) -> Decimal | None:
    try:
        d, m, s = (float(x) for x in value)
    except (TypeError, ValueError):
        return None
    result = d + m / 60 + s / 3600
    if ref in ("S", "W"):
        result = -result
    return Decimal(str(round(result, 6)))


def _process_image(
    data: bytes,
) -> tuple[bytes, datetime | None, Decimal | None, Decimal | None, dict[str, Any]]:
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        image = Image.open(BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise UnsupportedFile("Image illisible") from exc

    exif = image.getexif()
    taken_at = None
    raw = exif.get_ifd(_EXIF_IFD).get(_DATETIME_ORIGINAL)
    if isinstance(raw, str):
        try:
            taken_at = datetime.strptime(raw.strip(), "%Y:%m:%d %H:%M:%S").replace(tzinfo=UTC)
        except ValueError:
            taken_at = None
    gps = exif.get_ifd(_GPS_IFD)
    latitude = _degrees(gps.get(2), gps.get(1, "N")) if gps else None
    longitude = _degrees(gps.get(4), gps.get(3, "E")) if gps else None

    # La vignette est redressée et ne garde aucune métadonnée (ni GPS ni appareil).
    thumbnail = ImageOps.exif_transpose(image)
    thumbnail.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE))
    if thumbnail.mode not in ("RGB", "RGBA"):
        thumbnail = thumbnail.convert("RGB")
    buffer = BytesIO()
    thumbnail.save(buffer, format="WEBP", quality=80)
    extra = {"width": image.width, "height": image.height}
    return buffer.getvalue(), taken_at, latitude, longitude, extra


async def process(data: bytes, filename: str, content_type: str | None) -> ProcessedFile:
    sha256 = hashlib.sha256(data).hexdigest()
    if mime := image_type(filename, content_type):
        thumbnail, taken_at, latitude, longitude, extra = await asyncio.to_thread(
            _process_image, data
        )
        return ProcessedFile(
            content_type=mime,
            sha256=sha256,
            is_image=True,
            thumbnail=thumbnail,
            taken_at=taken_at,
            latitude=latitude,
            longitude=longitude,
            extra=extra,
        )
    kind = detect_kind(filename, content_type)
    if kind is None:
        raise UnsupportedFile(
            "Format non pris en charge : photos (JPEG, PNG, WebP) ou documents "
            "(PDF, Word, Excel, texte)"
        )
    processed = ProcessedFile(
        content_type=content_type or "application/octet-stream", sha256=sha256, is_image=False
    )
    try:
        pages = await asyncio.to_thread(extract_pages, data, kind)
    except ExtractionError as exc:
        # Un document scanné reste une preuve valable, même sans texte exploitable.
        processed.extra = {"extraction_error": str(exc)}
        return processed
    processed.text = "\n\n".join(p.text.replace("\x00", "") for p in pages)
    processed.page_count = len(pages)
    return processed
