"""Contrôle des réponses aux formulaires de collecte et synthèse par question."""

from datetime import date
from typing import Any

from app.models import FormSubmission
from app.schemas.form import FieldSummary, FormField, FormSummary

MAX_TEXT = 4000


class InvalidAnswers(ValueError):
    pass


def _clean(field: FormField, value: Any) -> Any:
    """Valeur normalisée, ou exception avec un message lisible par la personne qui saisit."""
    label = field.label
    if field.type == "text":
        text = str(value).strip()
        if len(text) > MAX_TEXT:
            raise InvalidAnswers(f"« {label} » : réponse trop longue")
        return text or None
    if field.type in ("number", "integer"):
        try:
            number = float(str(value).replace(",", "."))
        except ValueError:
            raise InvalidAnswers(f"« {label} » : un nombre est attendu") from None
        if field.type == "integer":
            if not number.is_integer():
                raise InvalidAnswers(f"« {label} » : un nombre entier est attendu")
            return int(number)
        return number
    if field.type == "yesno":
        if isinstance(value, bool):
            return value
        raise InvalidAnswers(f"« {label} » : oui ou non attendu")
    if field.type == "date":
        try:
            return date.fromisoformat(str(value)).isoformat()
        except ValueError:
            raise InvalidAnswers(f"« {label} » : date attendue (AAAA-MM-JJ)") from None
    if field.type == "select":
        if value not in field.options:
            raise InvalidAnswers(f"« {label} » : choix inconnu")
        return value
    values = value if isinstance(value, list) else [value]
    if any(v not in field.options for v in values):
        raise InvalidAnswers(f"« {label} » : choix inconnu")
    return [o for o in field.options if o in values] or None


def validate_answers(fields: list[FormField], answers: dict[str, Any]) -> dict[str, Any]:
    known = {f.key for f in fields}
    unknown = set(answers) - known
    if unknown:
        raise InvalidAnswers(f"Questions inconnues : {', '.join(sorted(unknown))}")
    clean: dict[str, Any] = {}
    for field in fields:
        raw = answers.get(field.key)
        value = None if raw is None or raw == "" or raw == [] else _clean(field, raw)
        if value is None:
            if field.required:
                raise InvalidAnswers(f"« {field.label} » : réponse obligatoire")
            continue
        clean[field.key] = value
    return clean


def summarize(fields: list[FormField], submissions: list[FormSubmission]) -> FormSummary:
    summaries = []
    for field in fields:
        values = [s.answers[field.key] for s in submissions if field.key in s.answers]
        summary = FieldSummary(
            key=field.key, label=field.label, type=field.type, answered=len(values)
        )
        if field.type in ("select", "multiselect"):
            summary.counts = {o: 0 for o in field.options}
            for value in values:
                for option in value if isinstance(value, list) else [value]:
                    if option in summary.counts:
                        summary.counts[option] += 1
        elif field.type == "yesno":
            summary.counts = {
                "yes": sum(1 for v in values if v),
                "no": sum(1 for v in values if not v),
            }
        elif field.type in ("number", "integer") and values:
            numbers = [float(v) for v in values]
            summary.total = sum(numbers)
            summary.mean = round(summary.total / len(numbers), 2)
            summary.min, summary.max = min(numbers), max(numbers)
        elif field.type == "text":
            summary.samples = [str(v) for v in values[-5:]][::-1]
        summaries.append(summary)
    return FormSummary(submissions=len(submissions), fields=summaries)
