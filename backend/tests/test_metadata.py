from io import BytesIO

from PIL import Image, PngImagePlugin

from app.documents.metadata import strip_metadata

GPS = {1: "S", 2: (1.0, 40.0, 30.0), 3: "E", 4: (29.0, 15.0, 0.0)}


def _exif(orientation: int = 1) -> Image.Exif:
    exif = Image.new("RGB", (1, 1)).getexif()
    exif[0x8825] = GPS
    exif[0x0110] = "Téléphone de terrain"
    exif.get_ifd(0x8769)[0x9003] = "2026:03:14 10:30:00"
    if orientation != 1:
        exif[0x0112] = orientation
    return exif


def _image() -> Image.Image:
    image = Image.new("RGB", (64, 32), "white")
    image.paste((200, 30, 30), (0, 0, 16, 32))
    return image


def test_jpeg_perd_ses_metadonnees_mais_pas_ses_pixels() -> None:
    buffer = BytesIO()
    _image().save(buffer, "JPEG", exif=_exif(), comment=b"auteur : agent 12")
    data = buffer.getvalue()
    cleaned = strip_metadata(data, "image/jpeg")
    image = Image.open(BytesIO(cleaned))
    assert not image.getexif() and "comment" not in image.info
    assert b"agent 12" not in cleaned
    assert image.tobytes() == Image.open(BytesIO(data)).tobytes()


def test_jpeg_garde_son_orientation() -> None:
    buffer = BytesIO()
    _image().save(buffer, "JPEG", exif=_exif(orientation=6))
    cleaned = strip_metadata(buffer.getvalue(), "image/jpeg")
    assert strip_metadata(cleaned, "image/jpeg") == cleaned  # relancer ne change rien
    image = Image.open(BytesIO(cleaned))
    exif = image.getexif()
    assert dict(exif) == {0x0112: 6}
    assert not exif.get_ifd(0x8825)


def test_png_perd_ses_textes() -> None:
    info = PngImagePlugin.PngInfo()
    info.add_text("Author", "Agent 12")
    buffer = BytesIO()
    _image().save(buffer, "PNG", pnginfo=info, exif=_exif())
    cleaned = strip_metadata(buffer.getvalue(), "image/png")
    image = Image.open(BytesIO(cleaned))
    assert not image.getexif() and "Author" not in image.info
    assert image.convert("RGB").tobytes() == _image().tobytes()


def test_png_tourne_est_redresse() -> None:
    buffer = BytesIO()
    _image().save(buffer, "PNG", exif=_exif(orientation=6))
    image = Image.open(BytesIO(strip_metadata(buffer.getvalue(), "image/png")))
    assert not image.getexif() and image.size == (32, 64)


def test_webp_perd_son_exif() -> None:
    buffer = BytesIO()
    _image().save(buffer, "WEBP", lossless=True, exif=_exif())
    cleaned = strip_metadata(buffer.getvalue(), "image/webp")
    image = Image.open(BytesIO(cleaned))
    assert not image.getexif()
    assert image.convert("RGB").tobytes() == _image().tobytes()
