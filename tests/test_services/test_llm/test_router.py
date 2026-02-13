import logging
import pytest
from unittest.mock import AsyncMock, MagicMock

from services.llm.base import LLMProvider, LLMProviderExhausted, LLMResponse
from services.llm.router import AllProvidersExhausted, ProviderRouter


class MockProvider(LLMProvider):
    """Test helper: a mock LLM provider with controllable behavior."""

    def __init__(self, provider_name: str, responses=None, fail=False):
        self._name = provider_name
        self._responses = responses or []
        self._fail = fail
        self._exhausted = False
        self._call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_exhausted(self) -> bool:
        return self._exhausted

    def reset(self) -> None:
        self._exhausted = False
        self._call_count = 0

    async def generate(
        self, messages: list[dict], temperature: float = 0.7
    ) -> LLMResponse:
        if self._exhausted:
            raise LLMProviderExhausted(f"{self._name} exhausted")
        if self._fail:
            self._exhausted = True
            raise LLMProviderExhausted(f"{self._name} failed")
        if self._call_count < len(self._responses):
            resp = self._responses[self._call_count]
            self._call_count += 1
            return resp
        return LLMResponse(
            text=f"response from {self._name}",
            provider_name=self._name,
            model="test-model",
        )


class TestProviderRouter:
    async def test_router_uses_first_provider(self):
        p1 = MockProvider("first")
        p2 = MockProvider("second")
        router = ProviderRouter([p1, p2])

        result = await router.generate([{"role": "user", "content": "Hi"}])

        assert result.provider_name == "first"
        assert p2._call_count == 0

    async def test_router_falls_through_to_second(self):
        p1 = MockProvider("first", fail=True)
        p2 = MockProvider("second")
        router = ProviderRouter([p1, p2])

        result = await router.generate([{"role": "user", "content": "Hi"}])

        assert result.provider_name == "second"

    async def test_router_all_exhausted(self):
        p1 = MockProvider("first", fail=True)
        p2 = MockProvider("second", fail=True)
        router = ProviderRouter([p1, p2])

        with pytest.raises(AllProvidersExhausted):
            await router.generate([{"role": "user", "content": "Hi"}])

    def test_router_from_config(self):
        config = [
            {
                "name": "gemini",
                "type": "gemini",
                "models": ["gemini-2.0-flash"],
                "api_keys": ["key1"],
            },
            {
                "name": "openai",
                "type": "openai_compatible",
                "base_url": "https://api.openai.com/v1",
                "models": ["gpt-4o"],
                "api_keys": ["sk-key1"],
            },
        ]
        router = ProviderRouter.from_config(config)

        assert len(router.providers) == 2
        from services.llm.gemini import GeminiProvider
        from services.llm.openai_compat import OpenAICompatibleProvider

        assert isinstance(router.providers[0], GeminiProvider)
        assert isinstance(router.providers[1], OpenAICompatibleProvider)

    async def test_router_reset_all(self):
        p1 = MockProvider("first", fail=True)
        p2 = MockProvider("second", fail=True)
        router = ProviderRouter([p1, p2])

        with pytest.raises(AllProvidersExhausted):
            await router.generate([{"role": "user", "content": "Hi"}])

        assert p1.is_exhausted is True
        assert p2.is_exhausted is True

        router.reset_all()

        assert p1.is_exhausted is False
        assert p2.is_exhausted is False
        assert router._current_idx == 0

    async def test_router_sticks_with_working_provider(self):
        p1 = MockProvider("first", fail=True)
        p2 = MockProvider("second")
        router = ProviderRouter([p1, p2])

        # First call falls through to p2
        r1 = await router.generate([{"role": "user", "content": "Hi"}])
        assert r1.provider_name == "second"

        # Second call should start from p2 (sticks)
        r2 = await router.generate([{"role": "user", "content": "Hello"}])
        assert r2.provider_name == "second"
        assert router._current_idx == 1

    async def test_router_logs_rotation(self, caplog):
        p1 = MockProvider("first", fail=True)
        p2 = MockProvider("second")
        router = ProviderRouter([p1, p2])

        with caplog.at_level(logging.WARNING):
            await router.generate([{"role": "user", "content": "Hi"}])

        assert any("first" in r.message and "exhausted" in r.message for r in caplog.records)
