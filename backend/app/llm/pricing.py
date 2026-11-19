"""Tarifs par million de jetons (USD) pour estimer le coût de chaque appel."""

from decimal import Decimal

Prices = tuple[Decimal, Decimal, Decimal, Decimal]

# modèle : (entrée, sortie, lecture de cache, écriture de cache)
PRICES: dict[str, Prices] = {
    "claude-opus-5-5": (Decimal("4"), Decimal("20"), Decimal("0.20"), Decimal("5")),
    "claude-opus-5": (Decimal("5"), Decimal("25"), Decimal("0.50"), Decimal("6.25")),
    "claude-sonnet-5-5": (Decimal("2"), Decimal("10"), Decimal("0.20"), Decimal("2.50")),
    "claude-sonnet-5": (Decimal("2"), Decimal("10"), Decimal("0.20"), Decimal("2.50")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50"), Decimal("0.01"), Decimal("0.125")),
    "claude-haiku-4-5": (Decimal("1"), Decimal("5"), Decimal("0.10"), Decimal("1.25")),
}
# Au-delà de LONG_PROMPT jetons d'entrée (cache compris), certains modèles changent de tarif.
LONG_PROMPT = 100_000
LONG_PROMPT_PRICES: dict[str, Prices] = {
    "claude-haiku-5-5": (Decimal("0.50"), Decimal("2.50"), Decimal("0.05"), Decimal("0.625")),
}

MILLION = Decimal(1_000_000)


def _base_model(model: str) -> str:
    """Nom du tarif : l'API peut renvoyer un identifiant daté (claude-haiku-4-5-20251001)."""
    matches = [name for name in PRICES if model == name or model.startswith(f"{name}-")]
    return max(matches, key=len, default="claude-opus-5")


def estimate_cost(
    model: str, input_tokens: int, output_tokens: int, cache_read: int, cache_write: int
) -> Decimal:
    name = _base_model(model)
    prices = PRICES[name]
    if input_tokens + cache_read + cache_write > LONG_PROMPT:
        prices = LONG_PROMPT_PRICES.get(name, prices)
    price_in, price_out, price_read, price_write = prices
    total = (
        input_tokens * price_in
        + output_tokens * price_out
        + cache_read * price_read
        + cache_write * price_write
    ) / MILLION
    return total.quantize(Decimal("0.000001"))
