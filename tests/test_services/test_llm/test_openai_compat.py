import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import openai

from services.llm.base import LLMProviderExhausted
from services.llm.openai_compat import OpenAICompatibleProvider


def _make_config(models=None, api_keys=None):
    return {
        "name": "test-openai",
        "type": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "models": models or ["gpt-4o-mini"],
        "api_keys": api_keys or ["sk-key1"],
        "temperature": 0.7,
    }


def _mock_response(content="Generated text"):
    resp = MagicMock()
    resp.content = content
    resp.response_metadata = {"token_usage": {"total_tokens": 100}}
    return resp


class TestOpenAICompatibleProvider:
    @patch("services.llm.openai_compat.ChatOpenAI")
    async def test_generate_success(self, mock_chat_cls):
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = _mock_response("Hello")
        mock_chat_cls.return_value = mock_instance

        provider = OpenAICompatibleProvider(_make_config())
        result = await provider.generate([{"role": "user", "content": "Hi"}])

        assert result.text == "Hello"
        assert result.provider_name == "test-openai"
        assert result.model == "gpt-4o-mini"
        assert result.tokens_used == 100

    @patch("services.llm.openai_compat.ChatOpenAI")
    async def test_key_rotation_on_rate_limit(self, mock_chat_cls):
        mock_fail = AsyncMock()
        mock_fail.ainvoke.side_effect = openai.RateLimitError(
            message="rate limit",
            response=MagicMock(status_code=429),
            body=None,
        )
        mock_success = AsyncMock()
        mock_success.ainvoke.return_value = _mock_response("OK")

        mock_chat_cls.side_effect = [mock_fail, mock_success]

        provider = OpenAICompatibleProvider(
            _make_config(api_keys=["sk-key1", "sk-key2"])
        )
        result = await provider.generate([{"role": "user", "content": "Hi"}])

        assert result.text == "OK"
        # Should have advanced to key[1]
        assert provider._current_key_idx == 1

    @patch("services.llm.openai_compat.ChatOpenAI")
    async def test_model_rotation_after_keys_exhausted(self, mock_chat_cls):
        mock_fail = AsyncMock()
        mock_fail.ainvoke.side_effect = openai.RateLimitError(
            message="rate limit",
            response=MagicMock(status_code=429),
            body=None,
        )
        mock_success = AsyncMock()
        mock_success.ainvoke.return_value = _mock_response("OK")

        # key[0]+model[0] fail, key[0]+model[1] success (1 key, 2 models)
        mock_chat_cls.side_effect = [mock_fail, mock_success]

        provider = OpenAICompatibleProvider(
            _make_config(models=["gpt-4o-mini", "gpt-4o"], api_keys=["sk-key1"])
        )
        result = await provider.generate([{"role": "user", "content": "Hi"}])

        assert result.text == "OK"
        assert provider._current_model_idx == 1

    @patch("services.llm.openai_compat.ChatOpenAI")
    async def test_provider_exhausted(self, mock_chat_cls):
        mock_fail = AsyncMock()
        mock_fail.ainvoke.side_effect = openai.RateLimitError(
            message="rate limit",
            response=MagicMock(status_code=429),
            body=None,
        )
        mock_chat_cls.return_value = mock_fail

        provider = OpenAICompatibleProvider(
            _make_config(models=["m1"], api_keys=["k1"])
        )

        with pytest.raises(LLMProviderExhausted):
            await provider.generate([{"role": "user", "content": "Hi"}])

    @patch("services.llm.openai_compat.ChatOpenAI")
    async def test_reset_clears_indices(self, mock_chat_cls):
        mock_fail = AsyncMock()
        mock_fail.ainvoke.side_effect = openai.RateLimitError(
            message="rate limit",
            response=MagicMock(status_code=429),
            body=None,
        )
        mock_chat_cls.return_value = mock_fail

        provider = OpenAICompatibleProvider(
            _make_config(models=["m1"], api_keys=["k1"])
        )

        with pytest.raises(LLMProviderExhausted):
            await provider.generate([{"role": "user", "content": "Hi"}])

        assert provider.is_exhausted is True

        provider.reset()
        assert provider.is_exhausted is False
        assert provider._current_model_idx == 0
        assert provider._current_key_idx == 0

    def test_is_exhausted_property(self):
        provider = OpenAICompatibleProvider(_make_config())
        assert provider.is_exhausted is False
