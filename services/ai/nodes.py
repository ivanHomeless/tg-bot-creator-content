import logging
from typing import Any, Callable, Coroutine

from tavily import TavilyClient

from services.ai.prompts import GENERATE_ERROR_TEXT, SEARCH_FALLBACK_TEXT
from services.llm.router import AllProvidersExhausted, ProviderRouter

logger = logging.getLogger(__name__)


def make_search_node(
    tavily_api_key: str,
) -> Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]:
    """Create a search node that queries Tavily for product information."""
    client = TavilyClient(api_key=tavily_api_key)

    async def search_node(state: dict[str, Any]) -> dict[str, Any]:
        query = state["product_query"]
        try:
            results = client.search(query=query, max_results=5)
            contents = results.get("results", [])
            if not contents:
                logger.warning("Tavily returned empty results for: %s", query)
                return {"search_results": SEARCH_FALLBACK_TEXT, "error": "empty_search"}

            text_parts = []
            for item in contents:
                title = item.get("title", "")
                content = item.get("content", "")
                url = item.get("url", "")
                text_parts.append(f"## {title}\n{content}\nSource: {url}")

            return {"search_results": "\n\n".join(text_parts)}
        except Exception as e:
            logger.error("Tavily search failed: %s", e)
            return {"search_results": SEARCH_FALLBACK_TEXT, "error": "search_failed"}

    return search_node


def make_generate_node(
    router: ProviderRouter,
) -> Callable[[dict[str, Any]], Coroutine[Any, Any, dict[str, Any]]]:
    """Create a generate node that calls the LLM via ProviderRouter."""

    async def generate_node(state: dict[str, Any]) -> dict[str, Any]:
        if state.get("error"):
            return {"generated_text": SEARCH_FALLBACK_TEXT}

        system_prompt = state.get("system_prompt", "")
        search_results = state.get("search_results", "")

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Информация о товаре из веб-поиска:\n\n"
                    f"{search_results}\n\n"
                    f"Напиши пост для Telegram-канала на основе этой информации."
                ),
            },
        ]

        try:
            response = await router.generate(messages)
            return {"generated_text": response.text}
        except AllProvidersExhausted:
            logger.error("All LLM providers exhausted")
            return {"generated_text": GENERATE_ERROR_TEXT, "error": "llm_failed"}

    return generate_node
