"""Client IA. L'interface `LLMClient` permet de changer de fournisseur ou d'utiliser un faux
client dans les tests, sans toucher au code métier."""

import time
from dataclasses import dataclass
from typing import Any, Generic, Literal, Protocol, TypeVar

import anthropic
from pydantic import BaseModel

from app.core.config import get_settings

T = TypeVar("T", bound=BaseModel)
Effort = Literal["low", "medium", "high", "xhigh", "max"]


class LLMError(Exception):
    """Échec d'un appel au modèle, avec un message présentable à l'utilisateur."""


@dataclass
class LLMResult(Generic[T]):
    output: T
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    duration_ms: int = 0
    request_id: str = ""


class LLMClient(Protocol):
    async def structured(
        self,
        *,
        model: str,
        system: str,
        content: list[dict[str, Any]],
        output_type: type[T],
        effort: Effort = "high",
        max_tokens: int = 64000,
    ) -> LLMResult[T]: ...


class AnthropicClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def structured(
        self,
        *,
        model: str,
        system: str,
        content: list[dict[str, Any]],
        output_type: type[T],
        effort: Effort = "high",
        max_tokens: int = 64000,
    ) -> LLMResult[T]:
        started = time.monotonic()
        try:
            # Streaming : les générations longues ne heurtent pas les délais HTTP.
            async with self.client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content}],  # type: ignore[typeddict-item]
                output_format=output_type,
                output_config={"effort": effort},
            ) as stream:
                message = await stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise LLMError("Clé API Anthropic absente ou invalide.") from exc
        except anthropic.RateLimitError as exc:
            raise LLMError("Limite de requêtes atteinte. Réessayez dans quelques minutes.") from exc
        except anthropic.BadRequestError as exc:
            raise LLMError(f"Requête refusée par l'API : {exc.message}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(
                f"Erreur du service IA ({exc.status_code}). Réessayez plus tard."
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Service IA injoignable. Vérifiez la connexion réseau.") from exc

        if message.stop_reason == "refusal":
            raise LLMError("Le modèle a refusé de traiter ce document.")
        if message.stop_reason == "max_tokens":
            raise LLMError("La réponse du modèle a été tronquée : le document est trop volumineux.")
        output = message.parsed_output
        if output is None:
            raise LLMError("Le modèle n'a pas renvoyé de réponse structurée exploitable.")
        usage = message.usage
        return LLMResult(
            output=output,
            model=message.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
            cache_write_tokens=usage.cache_creation_input_tokens or 0,
            duration_ms=int((time.monotonic() - started) * 1000),
            request_id=message._request_id or "",
        )


_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = AnthropicClient()
    return _client


def set_llm(client: LLMClient | None) -> None:
    """Remplace le client (tests, autre fournisseur)."""
    global _client
    _client = client
