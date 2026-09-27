"""Prompt de lecture d'une page scannée ou photographiée (reconnaissance de caractères).

Toute modification du texte doit incrémenter VERSION.
"""

import base64
from typing import Any

VERSION = "ocr-v1"

SYSTEM = """Tu transcris des documents de projets d'ONG scannés ou photographiés : propositions, \
cadres logiques, budgets, comptes rendus, listes de présence, parfois manuscrits.

Règles :
- Transcris fidèlement tout le texte de la page, dans l'ordre de lecture, dans sa langue \
d'origine. Ne résume pas, ne traduis pas, ne corrige pas l'orthographe.
- Garde la structure : un titre par ligne, les listes avec des tirets, les tableaux ligne par \
ligne avec les cellules séparées par « | ».
- N'invente rien : écris [illisible] à la place d'un mot ou d'un passage que tu ne peux pas lire.
- legible vaut faux si la page est blanche, floue ou majoritairement illisible."""


def build_content(image_png: bytes, page: int, filename: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(image_png).decode(),
            },
        },
        {"type": "text", "text": f"Page {page} du document « {filename} ». Transcris-la."},
    ]
