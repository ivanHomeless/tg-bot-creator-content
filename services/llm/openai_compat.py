import logging

import openai
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from services.llm.base import LLMProvider, LLMProviderExhausted, LLMResponse

logger = logging.getLogger(__name__)


def _to_langchain_messages(messages: list[dict]) -> list:
    """Convert dict messages to LangChain message objects."""
    result = []
    for m in messages:
        role = m["role"]
        content = m["content"]
        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "user":
            result.append(HumanMessage(content=content))
        elif role == "assistant":
            result.append(AIMessage(content=content))
    return result


class OpenAICompatibleProvider(LLMProvider):
    """
    Provider for OpenAI-compatible APIs (OpenAI, OpenRouter, DeepSeek).

    Rotation order: keys first, then models.
    key[0]+model[0] → key[1]+model[0] → key[0]+model[1] → key[1]+model[1] → exhausted
    """

    def __init__(self, config: dict):
        self._config = config
        self._name: str = config["name"]
        self._base_url: str = config.get("base_url", "https://api.openai.com/v1")
        self._models: list[str] = config["models"]
        self._api_keys: list[str] = config["api_keys"]
        self._default_temperature: float = config.get("temperature", 0.7)
        self._current_model_idx = 0
        self._current_key_idx = 0
        self._exhausted = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_exhausted(self) -> bool:
        return self._exhausted

    def reset(self) -> None:
        self._current_model_idx = 0
        self._current_key_idx = 0
        self._exhausted = False

    def _advance(self) -> bool:
        """Advance to next key, then model. Returns False if exhausted."""
        self._current_key_idx += 1
        if self._current_key_idx < len(self._api_keys):
            return True
        # Keys exhausted for current model, advance model
        self._current_key_idx = 0
        self._current_model_idx += 1
        if self._current_model_idx < len(self._models):
            return True
        # All exhausted
        self._exhausted = True
        return False

    async def generate(
        self, messages: list[dict], temperature: float = 0.7
    ) -> LLMResponse:
        if self._exhausted:
            raise LLMProviderExhausted(f"Provider {self._name} exhausted")

        while True:
            model = self._models[self._current_model_idx]
            api_key = self._api_keys[self._current_key_idx]

            try:
                llm = ChatOpenAI(
                    model=model,
                    api_key=api_key,
                    base_url=self._base_url,
                    temperature=temperature,
                )
                lc_messages = _to_langchain_messages(messages)
                response = await llm.ainvoke(lc_messages)

                tokens = None
                if response.response_metadata:
                    usage = response.response_metadata.get("token_usage")
                    if usage:
                        tokens = usage.get("total_tokens")

                text = response.content
                # Some models return content as list of blocks
                if isinstance(text, list):
                    text = "".join(
                        block.get("text", "") if isinstance(block, dict) else str(block)
                        for block in text
                    )

                return LLMResponse(
                    text=text,
                    provider_name=self._name,
                    model=model,
                    tokens_used=tokens,
                )

            except (
                openai.RateLimitError,
                openai.APIError,
                openai.APITimeoutError,
            ) as e:
                logger.warning(
                    f"[{self._name}] {model} key[{self._current_key_idx}] failed: {e}"
                )
                if not self._advance():
                    raise LLMProviderExhausted(
                        f"Provider {self._name} exhausted after error: {e}"
                    )
