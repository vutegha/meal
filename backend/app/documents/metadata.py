"""Retrait des métadonnées d'une photo (EXIF, GPS, XMP, IPTC, commentaires) sans la recompresser.

La date et la position sont lues avant et gardées en base, où l'accès est contrôlé : le fichier
original n'a plus à porter le numéro de série de l'appareil, la position exacte ni le logiciel.
Seule l'orientation est conservée, pour que la photo reste à l'endroit.
"""

import struct
from io import BytesIO

_ORIENTATION = 0x0112
# Segments JPEG retirés : APP1 (EXIF, XMP), APP13 (IPTC, Photoshop), commentaire.
_JPEG_DROPPED = {0xE1, 0xED, 0xFE}
# Morceaux PNG retirés : EXIF, textes libres (auteur, logiciel, commentaires), date.
_PNG_DROPPED = {b"eXIf", b"tEXt", b"iTXt", b"zTXt", b"tIME"}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_WEBP_DROPPED = {b"EXIF", b"XMP "}
_VP8X_EXIF = 0x08
_VP8X_XMP = 0x04


class MetadataError(Exception):
    pass


def _orientation(data: bytes) -> int:
    from PIL import Image

    try:
        value = Image.open(BytesIO(data)).getexif().get(_ORIENTATION, 1)
    except Exception:  # noqa: BLE001 - une orientation illisible vaut « à l'endroit »
        return 1
    return value if isinstance(value, int) and 1 <= value <= 8 else 1


def _strip_jpeg(data: bytes, orientation: int) -> bytes:
    out = bytearray(data[:2])
    pos = 2
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            raise MetadataError("Segment JPEG inattendu")
        marker = data[pos + 1]
        if marker == 0xFF:  # octet de remplissage
            pos += 1
            continue
        if marker == 0xDA:  # début des données de l'image : tout le reste est gardé
            if orientation != 1:
                from PIL import Image

                exif = Image.Exif()
                exif[_ORIENTATION] = orientation
                payload = exif.tobytes()
                segment = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
                # Après APP0 (JFIF) s'il existe, sinon juste après le début du fichier.
                insert = 2
                if out[2:4] == b"\xff\xe0":
                    insert = 4 + struct.unpack(">H", out[4:6])[0]
                out[insert:insert] = segment
            out += data[pos:]
            return bytes(out)
        (length,) = struct.unpack(">H", data[pos + 2 : pos + 4])
        end = pos + 2 + length
        if length < 2 or end > len(data):
            raise MetadataError("Segment JPEG tronqué")
        if marker not in _JPEG_DROPPED:
            out += data[pos:end]
        pos = end
    raise MetadataError("JPEG sans données d'image")


def _strip_png(data: bytes) -> bytes:
    out = bytearray(_PNG_SIGNATURE)
    pos = len(_PNG_SIGNATURE)
    while pos + 12 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        end = pos + 12 + length
        if end > len(data):
            raise MetadataError("Morceau PNG tronqué")
        if kind not in _PNG_DROPPED:
            out += data[pos:end]
        pos = end
        if kind == b"IEND":
            return bytes(out)
    raise MetadataError("PNG sans fin")


def _strip_webp(data: bytes) -> bytes:
    chunks = bytearray()
    pos = 12
    while pos + 8 <= len(data):
        kind = data[pos : pos + 4]
        (length,) = struct.unpack("<I", data[pos + 4 : pos + 8])
        end = pos + 8 + length + (length & 1)
        if pos + 8 + length > len(data):
            raise MetadataError("Morceau WebP tronqué")
        chunk = bytearray(data[pos:end])
        if kind == b"VP8X":
            chunk[8] &= ~(_VP8X_EXIF | _VP8X_XMP) & 0xFF
        if kind not in _WEBP_DROPPED:
            chunks += chunk
        pos = end
    return b"RIFF" + struct.pack("<I", len(chunks) + 4) + b"WEBP" + bytes(chunks)


def _transposed(data: bytes, mime: str) -> bytes:
    """Pixels redressés selon l'EXIF, réencodés sans aucune métadonnée."""
    from PIL import Image, ImageOps

    image = ImageOps.exif_transpose(Image.open(BytesIO(data)))
    buffer = BytesIO()
    if mime == "image/png":
        image.save(buffer, format="PNG", optimize=True)
    elif mime == "image/jpeg":
        image.convert("RGB").save(buffer, format="JPEG", quality=92)
    else:
        image.save(buffer, format="WEBP", quality=90)
    return buffer.getvalue()


def strip_metadata(data: bytes, mime: str) -> bytes:
    """Photo sans métadonnées. Un fichier mal formé est réencodé plutôt que gardé tel quel."""
    try:
        return _strip(data, mime)
    except (MetadataError, struct.error):
        return _transposed(data, mime)


def _strip(data: bytes, mime: str) -> bytes:
    orientation = _orientation(data)
    if mime == "image/jpeg":
        if data[:2] != b"\xff\xd8":
            raise MetadataError("Ce n'est pas un JPEG")
        return _strip_jpeg(data, orientation)
    if mime == "image/png":
        if not data.startswith(_PNG_SIGNATURE):
            raise MetadataError("Ce n'est pas un PNG")
        return _strip_png(_transposed(data, mime) if orientation != 1 else data)
    if mime == "image/webp":
        if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
            raise MetadataError("Ce n'est pas un WebP")
        return _strip_webp(_transposed(data, mime) if orientation != 1 else data)
    return data
