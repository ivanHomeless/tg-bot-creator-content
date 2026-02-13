import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.ai.graph import PostState, build_graph
from services.ai.prompts import (
    DEFAULT_SYSTEM_PROMPT,
    GENERATE_ERROR_TEXT,
    SEARCH_FALLBACK_TEXT,
)
from services.llm.base import LLMResponse
from services.llm.router import AllProvidersExhausted, ProviderRouter


def _tavily_results(items: list[dict] | None = None):
    """Build a Tavily-like response dict."""
    if items is None:
        items = [
            {
                "title": "Product Review",
                "content": "Great product with many features.",
                "url": "https://example.com/review",
            }
        ]
    return {"results": items}


class TestAIPipeline:
    async def test_full_pipeline_success(self):
        """Search succeeds, generate succeeds → generated_text filled."""
        mock_tavily = MagicMock()
        mock_tavily.search.return_value = _tavily_results()

        mock_router = AsyncMock(spec=ProviderRouter)
        mock_router.generate.return_value = LLMResponse(
            text="Generated post content",
            provider_name="test",
            model="test-model",
        )

        with patch("services.ai.nodes.TavilyClient", return_value=mock_tavily):
            graph = build_graph("fake-key", mock_router)
            result = await graph.ainvoke(
                {
                    "product_query": "iPhone 15",
                    "system_prompt": DEFAULT_SYSTEM_PROMPT,
                }
            )

        assert result["generated_text"] == "Generated post content"
        assert result.get("error") is None
        mock_router.generate.assert_called_once()

    async def test_search_failure_returns_fallback(self):
        """Tavily exception → fallback text, generate gets fallback."""
        mock_tavily = MagicMock()
        mock_tavily.search.side_effect = Exception("API error")

        mock_router = AsyncMock(spec=ProviderRouter)

        with patch("services.ai.nodes.TavilyClient", return_value=mock_tavily):
            graph = build_graph("fake-key", mock_router)
            result = await graph.ainvoke(
                {
                    "product_query": "iPhone 15",
                    "system_prompt": DEFAULT_SYSTEM_PROMPT,
                }
            )

        # When search fails, error is set → generate returns fallback
        assert result["generated_text"] == SEARCH_FALLBACK_TEXT
        assert result["error"] == "search_failed"
        # generate_node should NOT call the router when error is set
        mock_router.generate.assert_not_called()

    async def test_search_empty_returns_fallback(self):
        """Empty Tavily results → fallback text."""
        mock_tavily = MagicMock()
        mock_tavily.search.return_value = {"results": []}

        mock_router = AsyncMock(spec=ProviderRouter)

        with patch("services.ai.nodes.TavilyClient", return_value=mock_tavily):
            graph = build_graph("fake-key", mock_router)
            result = await graph.ainvoke(
                {
                    "product_query": "nonexistent product",
                    "system_prompt": DEFAULT_SYSTEM_PROMPT,
                }
            )

        assert result["search_results"] == SEARCH_FALLBACK_TEXT
        assert result["error"] == "empty_search"
        mock_router.generate.assert_not_called()

    async def test_generate_failure_returns_error(self):
        """AllProvidersExhausted → error text in generated_text."""
        mock_tavily = MagicMock()
        mock_tavily.search.return_value = _tavily_results()

        mock_router = AsyncMock(spec=ProviderRouter)
        mock_router.generate.side_effect = AllProvidersExhausted("all failed")

        with patch("services.ai.nodes.TavilyClient", return_value=mock_tavily):
            graph = build_graph("fake-key", mock_router)
            result = await graph.ainvoke(
                {
                    "product_query": "iPhone 15",
                    "system_prompt": DEFAULT_SYSTEM_PROMPT,
                }
            )

        assert result["generated_text"] == GENERATE_ERROR_TEXT
        assert result["error"] == "llm_failed"

    async def test_search_results_passed_to_generate(self):
        """Tavily text appears in LLM messages."""
        mock_tavily = MagicMock()
        mock_tavily.search.return_value = _tavily_results(
            [
                {
                    "title": "Spec Sheet",
                    "content": "Battery 4000mAh, Screen 6.1 inch",
                    "url": "https://example.com/specs",
                }
            ]
        )

        mock_router = AsyncMock(spec=ProviderRouter)
        mock_router.generate.return_value = LLMResponse(
            text="Post text", provider_name="test", model="m"
        )

        with patch("services.ai.nodes.TavilyClient", return_value=mock_tavily):
            graph = build_graph("fake-key", mock_router)
            await graph.ainvoke(
                {
                    "product_query": "Samsung Galaxy",
                    "system_prompt": DEFAULT_SYSTEM_PROMPT,
                }
            )

        # Check that search results were included in the messages to LLM
        call_args = mock_router.generate.call_args
        messages = call_args[0][0]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "Battery 4000mAh" in user_msg["content"]
        assert "Screen 6.1 inch" in user_msg["content"]

    async def test_system_prompt_used_in_generate(self):
        """Custom system prompt is passed to LLM."""
        mock_tavily = MagicMock()
        mock_tavily.search.return_value = _tavily_results()

        mock_router = AsyncMock(spec=ProviderRouter)
        mock_router.generate.return_value = LLMResponse(
            text="Post", provider_name="test", model="m"
        )

        custom_prompt = "Write in formal English only."

        with patch("services.ai.nodes.TavilyClient", return_value=mock_tavily):
            graph = build_graph("fake-key", mock_router)
            await graph.ainvoke(
                {
                    "product_query": "MacBook Pro",
                    "system_prompt": custom_prompt,
                }
            )

        call_args = mock_router.generate.call_args
        messages = call_args[0][0]
        system_msg = next(m for m in messages if m["role"] == "system")
        assert system_msg["content"] == custom_prompt
