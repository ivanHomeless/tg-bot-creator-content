import pytest

from services.llm.base import LLMProvider, LLMResponse


class TestLLMResponse:
    def test_llm_response_dataclass(self):
        r = LLMResponse(
            text="Hello", provider_name="openai", model="gpt-4o", tokens_used=42
        )
        assert r.text == "Hello"
        assert r.provider_name == "openai"
        assert r.model == "gpt-4o"
        assert r.tokens_used == 42

    def test_llm_response_tokens_optional(self):
        r = LLMResponse(text="Hi", provider_name="gemini", model="flash")
        assert r.tokens_used is None


class TestLLMProviderABC:
    def test_provider_interface_cannot_instantiate(self):
        with pytest.raises(TypeError):
            LLMProvider()
