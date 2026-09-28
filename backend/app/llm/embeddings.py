"""Embeddings pour la recherche sémantique (Voyage AI, recommandé avec Claude).

Anthropic ne fournit pas de modèle d'embeddings : sans clé Voyage, `get_embedder()` renvoie
None et la recherche reste en plein texte.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

import httpx

from app.core.config import get_settings

DIMENSIONS = 1024
# USD par million de jetons.
PRICES = {"voyage-3.5": Decimal("0.06"), "voyage-3.5-lite": Decimal("0.02")}
MAX_CHARS = 8000

Kind = Literal["document", "query"]


class EmbeddingError(Exception):
    pass


@dataclass
class Embeddings:
    vectors: list[list[float]]
    tokens: int
    model: str

    @property
    def cost_usd(self) -> Decimal:
        price = PRICES.get(self.model, Decimal("0.06"))
        return (price * self.tokens / Decimal(1_000_000)).quantize(Decimal("0.000001"))


class Embedder(Protocol):
    async def embed(self, texts: list[str], kind: Kind) -> Embeddings: ...


class VoyageEmbedder:
    url = "https://api.voyageai.com/v1/embeddings"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def embed(self, texts: list[str], kind: Kind) -> Embeddings:
        body = {
            "input": [t[:MAX_CHARS] or " " for t in texts],
            "model": self.model,
            "input_type": kind,
            "output_dimension": DIMENSIONS,
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    self.url, json=body, headers={"Authorization": f"Bearer {self.api_key}"}
                )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise EmbeddingError(f"Service d'embeddings indisponible : {exc}") from exc
        rows = sorted(data["data"], key=lambda row: row["index"])
        return Embeddings(
            vectors=[row["embedding"] for row in rows],
            tokens=int(data.get("usage", {}).get("total_tokens", 0)),
            model=self.model,
        )


_override: Embedder | None = None
_overridden = False


def get_embedder() -> Embedder | None:
    if _overridden:
        return _override
    settings = get_settings()
    if not settings.voyage_api_key:
        return None
    return VoyageEmbedder(settings.voyage_api_key, settings.embeddings_model)


def set_embedder(embedder: Embedder | None, active: bool = True) -> None:
    """Remplace le service (tests). `active=False` rétablit la configuration."""
    global _override, _overridden
    _override, _overridden = embedder, active
