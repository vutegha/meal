"""Type réel des fichiers déposés, lu dans leur contenu.

Le type annoncé par le navigateur (et l'extension) se falsifient : un fichier `note.txt` envoyé
comme `text/html` serait gardé puis renvoyé comme une page web. Le serveur reconnaît donc le
format d'après les premiers octets et ne garde que des formats connus ; le reste est refusé.
"""

import warnings
import zipfile
from io import BytesIO
from typing import Any

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Octets lus pour reconnaître un format (en-têtes de conteneurs audio et vidéo compris).
HEAD_BYTES = 64 * 1024
# Au-delà, une image est refusée : la décoder occuperait des centaines de Mo de mémoire
# (« bombe de décompression »). 120 millions de pixels couvrent les capteurs de téléphone de
# 108 Mpx.
MAX_PIXELS = 120_000_000

TEXT_EXTENSIONS = (".txt", ".md", ".csv")
TEXT_TYPES = ("text/plain", "text/markdown", "text/csv")
EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
    DOCX: "docx",
    XLSX: "xlsx",
    "text/plain": "txt",
    "audio/mpeg": "mp3",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
    "audio/ogg": "ogg",
    "audio/webm": "webm",
    "audio/wav": "wav",
    "audio/amr": "amr",
    "audio/3gpp": "3gp",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
    "video/3gpp": "3gp",
}


class ImageTooLarge(Exception):
    pass


def media_type(head: bytes, declared: str | None = None) -> str | None:
    """Type d'un enregistrement audio ou vidéo d'après ses premiers octets, ou None."""
    audio = (declared or "").lower().startswith("audio/")
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand == b"qt  ":
            return "video/quicktime"
        if brand.startswith(b"3g"):
            return "audio/3gpp" if audio else "video/3gpp"
        if brand in (b"M4A ", b"M4B ") or audio:
            return "audio/mp4"
        return "video/mp4"
    if head[4:8] in (b"moov", b"mdat", b"wide", b"free"):
        # Ancien format QuickTime, sans en-tête ftyp.
        return "video/quicktime"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio/webm" if audio else "video/webm"
    if head.startswith(b"OggS"):
        return "audio/ogg"
    if head.startswith(b"#!AMR"):
        return "audio/amr"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head.startswith(b"ID3"):
        return "audio/mpeg"
    if len(head) > 1 and head[0] == 0xFF:
        if head[1] & 0xF6 == 0xF0:
            return "audio/aac"
        if head[1] & 0xE0 == 0xE0:
            return "audio/mpeg"
    return None


def sniff(data: bytes, filename: str, declared: str | None = None) -> str | None:
    """Type MIME du fichier d'après son contenu, ou None si le format n'est pas pris en charge.

    `data` : le fichier entier (les documents Office se reconnaissent à leur contenu zippé), ou
    seulement son début pour un enregistrement.
    """
    head = data[:HEAD_BYTES]
    if head.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"PK\x03\x04"):
        return _office(data)
    if media := media_type(head, declared):
        return media
    name = filename.lower()
    base = (declared or "").split(";")[0].strip().lower()
    if b"\x00" not in head and (name.endswith(TEXT_EXTENSIONS) or base in TEXT_TYPES):
        # Gardé et renvoyé comme texte brut, jamais interprété par le navigateur.
        return "text/plain"
    return None


def _office(data: bytes) -> str | None:
    try:
        names = set(zipfile.ZipFile(BytesIO(data)).namelist())
    except (zipfile.BadZipFile, OSError, ValueError):
        return None
    if "word/document.xml" in names:
        return DOCX
    if "xl/workbook.xml" in names:
        return XLSX
    return None


def open_image(data: bytes) -> Any:
    """Image Pillow dont la taille a été contrôlée avant tout décodage des pixels.

    Lève ImageTooLarge au-delà de MAX_PIXELS, UnidentifiedImageError ou OSError si l'image est
    illisible.
    """
    from PIL import Image

    # Pillow avertit au-delà de cette limite et refuse au-delà du double : l'avertissement
    # devient ici un refus.
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(BytesIO(data))
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageTooLarge(str(exc)) from exc
    if image.width * image.height > MAX_PIXELS:
        raise ImageTooLarge(f"{image.width} × {image.height} pixels")
    return image


def too_large_message() -> str:
    return f"Image trop grande (plus de {MAX_PIXELS // 1_000_000} millions de pixels)"


def inline_allowed(content_type: str) -> bool:
    """Affichable dans la page (photo, enregistrement) ; les autres fichiers sont téléchargés."""
    return content_type.startswith(("image/", "audio/", "video/"))


def served_type(content_type: str) -> str:
    """Type renvoyé au navigateur : seulement un format connu (les pièces déposées avant ce
    contrôle peuvent porter un type annoncé par le client)."""
    base = content_type.split(";")[0].strip().lower()
    if base in EXTENSIONS:
        return base
    if base in TEXT_TYPES:
        return "text/plain"
    return "application/octet-stream"
