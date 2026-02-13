import logging

from services.llm.base import LLMProvider, LLMProviderExhausted, LLMResponse

logger = logging.getLogger(__name__)


class AllProvidersExhausted(Exception):
    """Raised when every provider in the priority list is exhausted."""


class ProviderRouter:
    """
    Manages a priority-ordered list of LLMProvider instances.
    Tries providers in order; when one is exhausted, moves to the next.
    """

    def __init__(self, providers: list[LLMProvider]):
        self.providers = providers
        self._current_idx = 0

    async def generate(
        self, messages: list[dict], temperature: float = 0.7
    ) -> LLMResponse:
        """Try providers in priority order until one succeeds."""
        errors: list[str] = []

        for i in range(len(self.providers)):
            idx = (self._current_idx + i) % len(self.providers)
            provider = self.providers[idx]

            if provider.is_exhausted:
                continue

            try:
                response = await provider.generate(messages, temperature)
                self._current_idx = idx
                logger.info(f"Generated via {provider.name}/{response.model}")
                return response
            except LLMProviderExhausted:
                logger.warning(f"Provider {provider.name} exhausted, trying next")
                errors.append(f"{provider.name}: exhausted")
                continue
            except Exception as e:
                logger.error(f"Provider {provider.name} error: {e}")
                errors.append(f"{provider.name}: {e}")
                continue

        raise AllProvidersExhausted(f"All providers failed: {'; '.join(errors)}")

    def reset_all(self) -> None:
        """Reset rotation state for all providers."""
        for p in self.providers:
            p.reset()
        self._current_idx = 0

    @classmethod
    def from_config(cls, config: list[dict]) -> "ProviderRouter":
        """Build router from DB config (list of provider dicts)."""
        from services.llm.gemini import GeminiProvider
        from services.llm.openai_compat import OpenAICompatibleProvider

        providers: list[LLMProvider] = []
        for cfg in config:
            provider_type = cfg.get("type", "")
            if provider_type == "openai_compatible":
                providers.append(OpenAICompatibleProvider(cfg))
            elif provider_type == "gemini":
                providers.append(GeminiProvider(cfg))
            else:
                logger.warning(f"Unknown provider type: {provider_type}")
        return cls(providers)
