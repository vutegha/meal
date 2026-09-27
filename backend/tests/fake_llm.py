from typing import Any, TypeVar

from pydantic import BaseModel

from app.llm.client import LLMError, LLMResult
from app.models import FeedbackCategory
from app.schemas.accountability import FeedbackSuggestion, PeriodicDraft
from app.schemas.ai import LogframeExtraction
from app.schemas.report import ReportDraft
from app.schemas.tor import TorDraft

T = TypeVar("T", bound=BaseModel)


def node(ref: str, parent: str | None, level: str, title: str, quote: str) -> dict[str, Any]:
    return {
        "ref": ref,
        "parent_ref": parent,
        "level": level,
        "code": ref,
        "title": title,
        "assumptions": "",
        "source_document": 1,
        "source_page": 1,
        "source_quote": quote,
    }


def budget(
    activity: str | None, code: str, label: str, qty: float, cost: float, freq: float, quote: str
) -> dict[str, Any]:
    return {
        "activity_ref": activity,
        "donor_line_code": code,
        "label": label,
        "category": "",
        "quantity": qty,
        "unit": "",
        "unit_cost": cost,
        "frequency": freq,
        "is_estimate": False,
        "source_document": 1,
        "source_page": 1,
        "source_quote": quote,
    }


# Ce que le modèle pourrait renvoyer pour app/llm/evals/proposition_avec.txt ; la dernière
# citation est volontairement inventée pour vérifier le contrôle des citations.
EXTRACTION = LogframeExtraction.model_validate(
    {
        "summary": "Projet de résilience économique à Rutshuru.",
        "currency": "USD",
        "nodes": [
            node(
                "OG",
                None,
                "goal",
                "Améliorer les conditions de vie",
                "Contribuer à l'amélioration durable des conditions de vie",
            ),
            node(
                "OS1",
                "OG",
                "outcome",
                "Les ménages diversifient leurs revenus",
                "Les ménages ciblés augmentent et diversifient leurs sources de revenus",
            ),
            node(
                "R1.1",
                "OS1",
                "output",
                "30 AVEC fonctionnelles",
                "30 associations villageoises d’épargne et de crédit (AVEC) sont créées",
            ),
            node(
                "A1.1.1",
                "R1.1",
                "activity",
                "Former les membres des AVEC",
                "Former les membres des AVEC à la gestion de l'épargne",
            ),
            node(
                "A1.1.2",
                "R1.1",
                "activity",
                "Doter les AVEC en kits",
                "Doter chaque AVEC d'un kit de démarrage",
            ),
            node(
                "R1.2",
                "OS1",
                "output",
                "Les jeunes lancent une AGR",
                "Les jeunes formés lancent une activité génératrice de revenus",
            ),
            node(
                "A1.2.1",
                "R1.2",
                "activity",
                "Former 150 jeunes",
                "Cette phrase n'existe pas dans le document source",
            ),
        ],
        "indicators": [
            {
                "node_ref": "OS1",
                "code": "OS1.a",
                "name": "Revenu mensuel moyen des ménages ciblés",
                "unit": "USD",
                "baseline": 38,
                "target": 55,
                "aggregation": "latest",
                "disaggregations": [],
                "source_of_verification": "Enquêtes de suivi semestrielles",
                "source_document": 1,
                "source_page": 1,
                "source_quote": (
                    "Revenu mensuel moyen des ménages ciblés. Valeur de référence : 38 USD"
                ),
            },
            {
                "node_ref": "R1.1",
                "code": "R1.1.a",
                "name": "Nombre de membres d'AVEC formés",
                "unit": "personnes",
                "baseline": None,
                "target": 600,
                "aggregation": "sum",
                "disaggregations": ["sexe"],
                "source_of_verification": "Listes de présence",
                "source_document": 1,
                "source_page": 1,
                "source_quote": "Nombre de membres d'AVEC formés, désagrégé par sexe",
            },
        ],
        "budget_lines": [
            budget(
                "A1.1.1",
                "1.1",
                "Formateurs AVEC",
                4,
                800,
                6,
                "4 formateurs x 800 USD par mois x 6 mois",
            ),
            budget("A1.1.2", "2.1", "Kits de démarrage", 30, 120, 1, "30 kits x 120 USD"),
            budget(None, "9.1", "Loyer du bureau", 1, 900, 24, "900 USD par mois x 24 mois"),
        ],
        "missing_information": ["Aucune valeur de référence pour R1.2.a"],
    }
)


TOR_DRAFT = TorDraft.model_validate(
    {
        "title": "TdR : formation des membres des AVEC",
        "sections": [
            {"key": "contexte", "content": "Les ménages ciblés ont un revenu moyen de 38 USD."},
            {
                "key": "objectifs",
                "content": "- Renforcer la gestion de l'épargne\n- Former 600 membres",
            },
            {"key": "budget", "content": "Ce texte doit être ignoré : le budget vient du projet."},
            {"key": "lieu_calendrier", "content": "[À compléter : dates de la formation]"},
        ],
        "missing_information": ["Dates de la formation", "Lieu exact"],
    }
)

# Le renvoi [S9] n'existe pas et doit être signalé ; la suggestion pour « X9 » doit être écartée.
REPORT_DRAFT = ReportDraft.model_validate(
    {
        "title": "Rapport : formation AVEC de Kiwanja",
        "sections": [
            {"key": "resume", "content": "36 membres ont été formés à Kiwanja [S1][P1]."},
            {"key": "deroulement", "content": "Deux groupes ont été constitués [S1] [S9]."},
            {"key": "participants", "content": "Ce texte doit être ignoré."},
            {"key": "lecons", "content": "[À compléter : retours des participants]"},
        ],
        "missing_information": ["Retours des participants"],
        "indicator_suggestions": [
            {
                "indicator_code": "I1",
                "value": 36,
                "justification": "36 participants selon le compte rendu",
                "source_ref": "S2",
            },
            {"indicator_code": "X9", "value": 3, "justification": "inconnu", "source_ref": "S1"},
        ],
    }
)

PERIODIC_DRAFT = PeriodicDraft.model_validate(
    {
        "title": "Rapport trimestriel T1 2026",
        "sections": [
            {"key": "resume", "content": "Trois AVEC formées ce trimestre [S1]."},
            {"key": "redevabilite", "content": "Un retour reçu et traité [S2] [S7]."},
            {"key": "budget", "content": "Ce texte doit être ignoré."},
        ],
        "missing_information": ["Évolution du contexte sécuritaire"],
    }
)

# Le modèle sous-estime volontairement la sensibilité : l'API doit la corriger.
FEEDBACK_SUGGESTION = FeedbackSuggestion(
    category=FeedbackCategory.FRAUD,
    sensitive=False,
    urgency="normal",
    summary="Un relais communautaire exigerait de l'argent pour l'inscription sur la liste.",
    justification="Paiement exigé en échange de l'aide : fraude.",
)

FIXTURES: dict[type[BaseModel], BaseModel] = {
    FeedbackSuggestion: FEEDBACK_SUGGESTION,
    PeriodicDraft: PERIODIC_DRAFT,
    LogframeExtraction: EXTRACTION,
    TorDraft: TOR_DRAFT,
    ReportDraft: REPORT_DRAFT,
}


class FakeLLM:
    def __init__(self, error: str | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def structured(
        self,
        *,
        model: str,
        system: str,
        content: list[dict[str, Any]],
        output_type: type[T],
        effort: str | None = "high",
        max_tokens: int = 64000,
    ) -> LLMResult[T]:
        self.calls.append({"model": model, "system": system, "content": content})
        if self.error:
            raise LLMError(self.error)
        return LLMResult(
            output=output_type.model_validate(FIXTURES[output_type].model_dump()),
            model=model,
            input_tokens=12_000,
            output_tokens=3_000,
            cache_write_tokens=10_000,
            duration_ms=1500,
            request_id="req_test",
        )
