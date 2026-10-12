import pytest
from pydantic import BaseModel

from app.core.config import get_settings
from app.llm.client import AnthropicClient, LLMError


class Out(BaseModel):
    text: str


async def test_cle_absente_message_explicite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    client = AnthropicClient()
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        await client.structured(model="m", system="s", content=[], output_type=Out)
