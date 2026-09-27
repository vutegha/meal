"""Détection et floutage des visages sur les photos de terrain.

Détecteurs de Haar fournis avec OpenCV : aucun modèle à télécharger, aucun appel externe.
Ils ratent des visages (trop petits, de dos, dans l'ombre) et prennent parfois un motif pour
un visage : le floutage protège par défaut, il ne dispense pas de vérifier la photo.
"""

from functools import cache
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

# Plus petit visage recherché, en pixels, sur l'image analysée.
MIN_FACE = 16
# Marge ajoutée autour du visage détecté (cheveux, oreilles, menton).
MARGIN = 0.25

Box = tuple[int, int, int, int]


@cache
def _detectors() -> list[Any]:
    import cv2

    root: str = cv2.data.haarcascades  # type: ignore[attr-defined]
    return [
        cv2.CascadeClassifier(root + name)
        for name in (
            "haarcascade_frontalface_default.xml",
            "haarcascade_frontalface_alt2.xml",
            "haarcascade_profileface.xml",
        )
    ]


def _overlap(a: Box, b: Box) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def detect_faces(image: Image.Image) -> list[Box]:
    """Rectangles (x, y, largeur, hauteur) des visages trouvés, sans doublon."""
    import cv2
    import numpy as np

    gray = cv2.equalizeHist(np.asarray(image.convert("L")))
    width = gray.shape[1]
    found: list[Box] = []
    for index, detector in enumerate(_detectors()):
        # Le détecteur de profil ne voit qu'un côté : on analyse aussi l'image retournée.
        views = [(gray, False)] + ([(cv2.flip(gray, 1), True)] if index == 2 else [])
        for view, flipped in views:
            boxes = detector.detectMultiScale(
                view, scaleFactor=1.1, minNeighbors=5, minSize=(MIN_FACE, MIN_FACE)
            )
            for x, y, w, h in (tuple(int(v) for v in box) for box in boxes):
                box = (width - x - w if flipped else x, y, w, h)
                if not any(_overlap(box, other) for other in found):
                    found.append(box)
    return found


def blur_faces(image: Image.Image) -> tuple[Image.Image, int]:
    """Copie de l'image où chaque visage est pixelisé puis flouté (irréversible)."""
    boxes = detect_faces(image)
    if not boxes:
        return image, 0
    result = image.copy()
    for x, y, w, h in boxes:
        dx, dy = int(w * MARGIN), int(h * MARGIN)
        left, top = max(0, x - dx), max(0, y - dy)
        right, bottom = min(image.width, x + w + dx), min(image.height, y + h + dy)
        region = result.crop((left, top, right, bottom))
        size = region.size
        # Pixelisation (8 blocs de large) puis flou : les traits ne se reconstituent pas.
        small = (8, max(1, round(8 * size[1] / size[0])))
        region = region.resize(small, Image.Resampling.BILINEAR)
        region = region.resize(size, Image.Resampling.NEAREST).filter(
            ImageFilter.GaussianBlur(max(2, size[0] // 10))
        )
        mask = Image.new("L", size, 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size[0] - 1, size[1] - 1), fill=255)
        result.paste(region, (left, top), mask)
    return result, len(boxes)
