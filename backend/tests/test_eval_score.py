import json

from app.llm.evals.run import HERE, score
from tests.fake_llm import EXTRACTION


def test_score_compares_extraction_with_expected() -> None:
    text = (HERE / "proposition_avec.txt").read_text(encoding="utf-8")
    expected = json.loads((HERE / "expected_proposition_avec.json").read_text(encoding="utf-8"))
    result = score(EXTRACTION, expected, "proposition_avec.txt", text)
    checks = dict(result.checks)
    assert checks["nœud conditions de vie (goal)"]
    assert checks["nœud A1.2.1 (activity)"]
    assert checks["indicateur de OS1"]
    assert not checks["indicateur de R1.2"]  # absent de la sortie simulée
    assert checks["budget A1.1.1 = 19200"]
    assert not checks["budget A1.2.1 = 13500"]
    assert 0 < result.rate < 1
    # Une citation inventée sur les douze éléments de la sortie simulée.
    assert 0.8 < result.quotes_verified < 1
