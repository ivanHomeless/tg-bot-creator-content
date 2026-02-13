from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Response from an LLM provider."""

    text: str
    provider_name: str
    model: str
    tokens_used: int | None = None


class LLMProviderExhausted(Exception):
    """Raised when all models and keys for a provider are exhausted."""


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name."""
        ...

    @abstractmethod
    async def generate(
        self, messages: list[dict], temperature: float = 0.7
    ) -> LLMResponse:
        """Generate a response. Raises LLMProviderExhausted when exhausted."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset rotation state."""
        ...

    @property
    @abstractmethod
    def is_exhausted(self) -> bool:
        """True if all models+keys have been tried without success."""
        ...
