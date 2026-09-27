"""Tarifs par million de jetons (USD) pour estimer le coût de chaque appel."""

from decimal import Decimal

# modèle : (entrée, sortie, lecture de cache, écriture de cache)
PRICES: dict[str, tuple[Decimal, Decimal, Decimal, Decimal]] = {
    "claude-opus-5-5": (Decimal("4"), Decimal("20"), Decimal("0.20"), Decimal("5")),
    "claude-opus-5": (Decimal("5"), Decimal("25"), Decimal("0.50"), Decimal("6.25")),
    "claude-sonnet-5": (Decimal("2"), Decimal("10"), Decimal("0.20"), Decimal("2.50")),
    "claude-haiku-4-5": (Decimal("1"), Decimal("5"), Decimal("0.10"), Decimal("1.25")),
}

MILLION = Decimal(1_000_000)


def estimate_cost(
    model: str, input_tokens: int, output_tokens: int, cache_read: int, cache_write: int
) -> Decimal:
    price_in, price_out, price_read, price_write = PRICES.get(model, PRICES["claude-opus-5"])
    total = (
        input_tokens * price_in
        + output_tokens * price_out
        + cache_read * price_read
        + cache_write * price_write
    ) / MILLION
    return total.quantize(Decimal("0.000001"))
