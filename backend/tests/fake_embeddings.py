"""Faux service d'embeddings : des synonymes partagent une dimension, sans appel réseau."""

import hashlib
import math
import re

from app.llm.embeddings import DIMENSIONS, EmbeddingError, Embeddings, Kind

CONCEPTS = {
    "épargne": 0,
    "économies": 0,
    "economies": 0,
    "forage": 1,
    "puits": 1,
    "formation": 2,
    "atelier": 2,
}


def _vector(text: str) -> list[float]:
    vector = [0.0] * DIMENSIONS
    for word in re.findall(r"\w+", text.lower()):
        if word in CONCEPTS:
            vector[CONCEPTS[word]] += 3.0
        else:
            digest = int(hashlib.sha1(word.encode()).hexdigest(), 16)
            vector[10 + digest % (DIMENSIONS - 10)] += 0.2
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class FakeEmbedder:
    def __init__(self) -> None:
        self.calls: list[tuple[Kind, int]] = []
        self.fail = False

    async def embed(self, texts: list[str], kind: Kind) -> Embeddings:
        if self.fail:
            raise EmbeddingError("service coupé")
        self.calls.append((kind, len(texts)))
        return Embeddings(
            vectors=[_vector(t) for t in texts],
            tokens=sum(len(t.split()) for t in texts),
            model="voyage-3.5",
        )
