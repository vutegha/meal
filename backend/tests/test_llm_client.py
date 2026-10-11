from app.llm.client import parse_json_output
from app.schemas.ai import ExtractedProject

PROJECT = (
    '{"donor": "UE", "start_date": null, "end_date": null, "duration_months": 24, '
    '"zones": ["Nord-Kivu"], "target_groups": []}'
)


def test_parse_json_output_accepts_plain_and_fenced_json() -> None:
    assert parse_json_output(PROJECT, ExtractedProject) == ExtractedProject.model_validate_json(
        PROJECT
    )
    fenced = parse_json_output(f"Voici :\n```json\n{PROJECT}\n```", ExtractedProject)
    assert fenced is not None and fenced.duration_months == 24


def test_parse_json_output_rejects_invalid_output() -> None:
    assert parse_json_output("pas de JSON", ExtractedProject) is None
    assert parse_json_output('{"donor": "UE"}', ExtractedProject) is None
