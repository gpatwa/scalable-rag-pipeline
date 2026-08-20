from typing import Protocol

from openai import AsyncOpenAI

from app.config import Settings


class ChatCompletionClient(Protocol):
    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.0,
    ) -> str: ...


class OpenAICompatibleClient:
    """Small product-owned adapter for OpenAI-compatible chat endpoints."""

    def __init__(self, config: Settings):
        self._config = config
        self._client: AsyncOpenAI | None = None

    @property
    def configured(self) -> bool:
        return bool(self._config.llm_api_key or self._config.ANALYTICS_LLM_BASE_URL)

    async def start(self) -> None:
        if not self.configured:
            return
        kwargs = {"api_key": self._config.llm_api_key or "local-development"}
        if self._config.ANALYTICS_LLM_BASE_URL:
            kwargs["base_url"] = self._config.ANALYTICS_LLM_BASE_URL
        self._client = AsyncOpenAI(**kwargs)

    async def close(self) -> None:
        if self._client:
            await self._client.close()

    async def chat_completion(
        self,
        messages: list[dict],
        temperature: float = 0.0,
    ) -> str:
        if not self._client:
            raise RuntimeError(
                "Analytics LLM is not configured. Set ANALYTICS_LLM_API_KEY "
                "or ANALYTICS_LLM_BASE_URL."
            )
        response = await self._client.chat.completions.create(
            model=self._config.ANALYTICS_LLM_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=1_024,
        )
        return response.choices[0].message.content or ""
