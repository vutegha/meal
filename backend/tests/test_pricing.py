from decimal import Decimal

from app.llm.pricing import estimate_cost


def test_dated_model_uses_its_own_price() -> None:
    assert estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 0, 0, 0) == Decimal("1")
    assert estimate_cost("claude-opus-5-5", 1_000_000, 0, 0, 0) == Decimal("4")
    assert estimate_cost("modele-inconnu", 1_000_000, 0, 0, 0) == Decimal("5")


def test_haiku_long_prompt_rate() -> None:
    assert estimate_cost("claude-haiku-5-5", 10_000, 1_000, 0, 0) == Decimal("0.0015")
    assert estimate_cost("claude-haiku-5-5", 200_000, 1_000, 0, 0) == Decimal("0.1025")
