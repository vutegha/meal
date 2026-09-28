"""Écrit le schéma OpenAPI de l'API, source du client TypeScript généré du frontend.

Usage : `uv run python -m app.scripts.openapi ../frontend/openapi.json`
"""

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    schema = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(schema, encoding="utf-8")
    else:
        sys.stdout.write(schema)


if __name__ == "__main__":
    main()
