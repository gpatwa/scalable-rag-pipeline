# services/api/app/clients/base.py
"""
Protocol definitions for LLM and Embedding clients.
All providers must implement these interfaces.
"""
from typing import Dict, List, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Interface for LLM chat completion providers."""

    async def start(self) -> None:
        """Initialize connections / SDK clients."""
        ...

    async def close(self) -> None:
        """Clean up connections."""
        ...

    async def chat_completion(
        self,
        messages: List[Dict],
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> str:
        """
        Send a chat completion request.

        Args:
            messages: List of {"role": "system|user|assistant", "content": "..."}
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative)
            json_mode: If True, request structured JSON output

        Returns:
            The assistant's response text.
        """
        ...


@runtime_checkable
class EmbedClient(Protocol):
    """Interface for text embedding providers."""

    async def start(self) -> None:
        """Initialize connections / SDK clients."""
        ...

    async def close(self) -> None:
        """Clean up connections."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query text. Returns a vector."""
        ...

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple documents. Returns a list of vectors."""
        ...
