"""API des tests de bout en bout : vraie base, faux modèle IA (aucune clé ni appel réseau).

Lancé par frontend/playwright.config.ts : `uv run python -m tests.e2e_server`.
"""

import os

import uvicorn

from app.llm.client import set_llm
from tests.fake_llm import FakeLLM

set_llm(FakeLLM())

from app.main import app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, port=int(os.environ.get("E2E_API_PORT", "8000")), log_level="warning")
