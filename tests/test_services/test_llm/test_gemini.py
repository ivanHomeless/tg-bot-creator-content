import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from services.llm.base import LLMProviderExhausted
from services.llm.gemini import GeminiProvider


def _make_config(models=None, api_keys=None):
    return {
        "name": "test-gemini",
        "type": "gemini",
        "models": models or ["gemini-2.0-flash"],
        "api_keys": api_keys or ["AIza-key1"],
        "temperature": 0.7,
    }


def _mock_response(content="Generated text"):
    resp = MagicMock()
    resp.content = content
    resp.response_metadata = {"usage_metadata": {"total_token_count": 50}}
    return resp


class TestGeminiProvider:
    @patch("services.llm.gemini.ChatGoogleGenerativeAI")
    async def test_generate_success(self, mock_chat_cls):
        mock_instance = AsyncMock()
        mock_instance.ainvoke.return_value = _mock_response("Hello from Gemini")
        mock_chat_cls.return_value = mock_instance

        provider = GeminiProvider(_make_config())
        result = await provider.generate([{"role": "user", "content": "Hi"}])

        assert result.text == "Hello from Gemini"
        assert result.provider_name == "test-gemini"
        assert result.model == "gemini-2.0-flash"
        assert result.tokens_used == 50

    @patch("services.llm.gemini.ChatGoogleGenerativeAI")
    async def test_model_rotation_first(self, mock_chat_cls):
        """With 2 models and 1 key, on error rotates model before key."""
        mock_fail = AsyncMock()
        mock_fail.ainvoke.side_effect = Exception("ResourceExhausted")
        mock_success = AsyncMock()
        mock_success.ainvoke.return_value = _mock_response("OK")

        mock_chat_cls.side_effect = [mock_fail, mock_success]

        provider = GeminiProvider(
            _make_config(
                models=["gemini-2.0-flash", "gemini-1.5-pro"],
                api_keys=["AIza-key1"],
            )
        )
        result = await provider.generate([{"role": "user", "content": "Hi"}])

        assert result.text == "OK"
        assert result.model == "gemini-1.5-pro"
        assert provider._current_model_idx == 1
        assert provider._current_key_idx == 0  # key did NOT change

    @patch("services.llm.gemini.ChatGoogleGenerativeAI")
    async def test_key_rotation_after_all_models(self, mock_chat_cls):
        """After models exhausted for key[0], moves to key[1]+model[0]."""
        mock_fail = AsyncMock()
        mock_fail.ainvoke.side_effect = Exception("ResourceExhausted")
        mock_success = AsyncMock()
        mock_success.ainvoke.return_value = _mock_response("OK")

        # model[0]+key[0] fail, model[1]+key[0] fail, model[0]+key[1] success
        mock_chat_cls.side_effect = [mock_fail, mock_fail, mock_success]

        provider = GeminiProvider(
            _make_config(
                models=["gemini-2.0-flash", "gemini-1.5-pro"],
                api_keys=["AIza-key1", "AIza-key2"],
            )
        )
        result = await provider.generate([{"role": "user", "content": "Hi"}])

        assert result.text == "OK"
        assert provider._current_model_idx == 0  # reset to model[0]
        assert provider._current_key_idx == 1  # advanced to key[1]

    @patch("services.llm.gemini.ChatGoogleGenerativeAI")
    async def test_provider_exhausted(self, mock_chat_cls):
        mock_fail = AsyncMock()
        mock_fail.ainvoke.side_effect = Exception("ResourceExhausted")
        mock_chat_cls.return_value = mock_fail

        provider = GeminiProvider(
            _make_config(models=["m1"], api_keys=["k1"])
        )

        with pytest.raises(LLMProviderExhausted):
            await provider.generate([{"role": "user", "content": "Hi"}])

        assert provider.is_exhausted is True

    @patch("services.llm.gemini.ChatGoogleGenerativeAI")
    async def test_reset(self, mock_chat_cls):
        mock_fail = AsyncMock()
        mock_fail.ainvoke.side_effect = Exception("error")
        mock_chat_cls.return_value = mock_fail

        provider = GeminiProvider(
            _make_config(models=["m1"], api_keys=["k1"])
        )

        with pytest.raises(LLMProviderExhausted):
            await provider.generate([{"role": "user", "content": "Hi"}])

        provider.reset()
        assert provider.is_exhausted is False
        assert provider._current_model_idx == 0
        assert provider._current_key_idx == 0
