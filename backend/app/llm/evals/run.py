"""Jeu d'évaluation du prompt d'extraction du cadre logique.

Appelle réellement l'API Claude (clé ANTHROPIC_API_KEY requise, coût de quelques centimes) :

    uv run python -m app.llm.evals.run [--model claude-opus-5-5]

Le score compare la sortie du modèle à `expected_proposition_avec.json` : éléments du cadre
logique retrouvés, valeurs des indicateurs, totaux budgétaires par activité, et part des
citations vérifiées dans le document. À relancer à chaque modification du prompt.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.core.config import get_settings
from app.documents.extract import extract_pages
from app.llm.client import LLMError, get_llm
from app.llm.pricing import estimate_cost
from app.llm.prompts import logframe_extraction as prompt
from app.schemas.ai import LogframeExtraction
from app.services.extraction import normalize, verify

HERE = Path(__file__).parent
CASES = [("proposition_avec.txt", "expected_proposition_avec.json")]


@dataclass
class Score:
    checks: list[tuple[str, bool]] = field(default_factory=list)
    quotes_verified: float = 0.0

    def add(self, label: str, ok: bool) -> None:
        self.checks.append((label, ok))

    @property
    def rate(self) -> float:
        return sum(ok for _, ok in self.checks) / len(self.checks) if self.checks else 0.0


def _close(value: float | None, expected: float) -> bool:
    return value is not None and abs(value - expected) <= 0.01 * max(abs(expected), 1)


def score(
    extraction: LogframeExtraction, expected: dict[str, Any], filename: str, text: str
) -> Score:
    result = Score()
    by_code = {normalize(n.code): n for n in extraction.nodes}
    by_ref = {n.ref: n for n in extraction.nodes}

    def find(code: str, level: str) -> Any:
        node = by_code.get(normalize(code)) or by_ref.get(code)
        if node is None:
            # Nœuds sans code (objectif général) : recherche dans le titre.
            node = next(
                (
                    n
                    for n in extraction.nodes
                    if n.level == level and normalize(code) in normalize(n.title)
                ),
                None,
            )
        return node

    for level, codes in expected["nodes"].items():
        for code in codes:
            node = find(code, level)
            result.add(f"nœud {code} ({level})", node is not None and node.level == level)

    for item in expected["indicators"]:
        node = find(item["node"], "")
        candidates = [i for i in extraction.indicators if node and i.node_ref == node.ref]
        ok = any(
            all(_close(getattr(i, k), item[k]) for k in ("baseline", "target") if k in item)
            for i in candidates
        )
        result.add(f"indicateur de {item['node']}", ok)

    totals: dict[str, float] = {}
    for line in extraction.budget_lines:
        activity = by_ref.get(line.activity_ref or "")
        key = activity.code if activity else "support"
        totals[key] = totals.get(key, 0) + line.quantity * line.unit_cost * line.frequency
    for key, amount in expected["budget_totals"].items():
        result.add(f"budget {key} = {amount}", _close(totals.get(key), amount))

    pages = [
        SimpleNamespace(number=p.number, text=p.text) for p in extract_pages(text.encode(), "txt")
    ]
    proposal = verify(extraction, [SimpleNamespace(filename=filename, pages=pages)])  # type: ignore[list-item]
    items = [*proposal.nodes, *proposal.indicators, *proposal.budget_lines]
    result.quotes_verified = sum(i.verified for i in items) / len(items) if items else 0.0
    return result


async def main(model: str) -> int:
    if not get_settings().anthropic_api_key:
        print("ANTHROPIC_API_KEY manquante : l'évaluation appelle réellement l'API.")
        return 2
    failed = False
    for source, expected_file in CASES:
        text = (HERE / source).read_text(encoding="utf-8")
        expected = json.loads((HERE / expected_file).read_text(encoding="utf-8"))
        pages = extract_pages(text.encode(), "txt")
        content = prompt.build_content([(source, [(p.number, p.text) for p in pages])])
        try:
            response = await get_llm().structured(
                model=model, system=prompt.SYSTEM, content=content, output_type=LogframeExtraction
            )
        except LLMError as exc:
            print(f"{source} : échec de l'appel ({exc})")
            return 1
        result = score(response.output, expected, source, text)
        cost = estimate_cost(
            response.model or model,
            response.input_tokens,
            response.output_tokens,
            response.cache_read_tokens,
            response.cache_write_tokens,
        )
        print(f"\n{source} ({prompt.VERSION}, {response.model or model}, {cost:.4f} USD)")
        for label, ok in result.checks:
            print(f"  {'OK ' if ok else 'KO '} {label}")
        print(f"  Contrôles réussis : {result.rate:.0%}")
        print(f"  Citations vérifiées : {result.quotes_verified:.0%}")
        failed |= result.rate < 0.9 or result.quotes_verified < 0.8
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=get_settings().llm_model_extraction)
    sys.exit(asyncio.run(main(parser.parse_args().model)))
