"""Prompt de classement d'un retour communautaire (plainte, suggestion, signalement…).

Modèle léger : la personne qui saisit valide ou corrige toujours la proposition.
Toute modification du texte doit incrémenter VERSION.
"""

from typing import Any

VERSION = "feedback-v1"

SYSTEM = """Tu aides une équipe MEAL d'ONG à trier les retours reçus des communautés \
(mécanisme de plaintes et retours). Pour le retour fourni, propose :
- category : information (demande d'information), suggestion, appreciation (remerciement, \
satisfaction), complaint (plainte sur l'aide, le ciblage, le comportement, la qualité…), fraud \
(détournement, corruption, paiement exigé, fausse liste), sexual_exploitation (exploitation ou \
abus sexuels, harcèlement sexuel, demande de faveurs sexuelles, même évoqués indirectement), \
safety (menace, violence, danger pour une personne, risque sécuritaire), other ;
- sensitive : vrai pour fraud, sexual_exploitation et safety, et pour tout retour qui met une \
personne en danger ou qui vise un membre du personnel ou d'un partenaire ;
- urgency : high si une personne est en danger ou si le retour relève des catégories sensibles, \
normal pour une plainte ordinaire, low pour le reste ;
- summary : une phrase neutre, sans nom de personne, ni numéro de téléphone, ni lieu précis \
permettant d'identifier quelqu'un ;
- justification : une phrase qui explique le choix de la catégorie.

En cas de doute entre une catégorie sensible et une autre, choisis la catégorie sensible : un \
signalement mal classé comme ordinaire ne serait pas traité dans les délais. Réponds en français, \
quelle que soit la langue du retour."""


def build_content(description: str, channel: str | None) -> list[dict[str, Any]]:
    head = f"Canal de réception : {channel}\n\n" if channel else ""
    return [{"type": "text", "text": f"{head}Retour reçu :\n<retour>\n{description}\n</retour>"}]
