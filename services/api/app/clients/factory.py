# services/api/app/clients/factory.py
"""
Factory functions for creating LLM and Embedding clients.
Provider is selected via LLM_PROVIDER / EMBED_PROVIDER env vars.

Supported providers:
  LLM:   "ray" (self-hosted vLLM) | "openai" (OpenAI API / compatible)
  Embed: "ray" (self-hosted BGE)  | "openai" (OpenAI API / compatible)
"""
import logging

logger = logging.getLogger(__name__)


def create_llm_client(provider: str):
    """
    Create an LLM client based on the provider name.

    Args:
        provider: "ray" or "openai"

    Returns:
        An LLM client instance with start/close/chat_completion methods.
    """
    provider = provider.lower().strip()

    if provider == "openai":
        from app.clients.openai_llm import OpenAILLMClient
        logger.info("Using OpenAI LLM provider")
        return OpenAILLMClient()

    elif provider == "ray":
        from app.clients.ray_llm import RayLLMClient
        logger.info("Using Ray/vLLM LLM provider")
        return RayLLMClient()

    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER: '{provider}'. "
            f"Supported: 'ray', 'openai'"
        )


def create_embed_client(provider: str):
    """
    Create an Embedding client based on the provider name.

    Args:
        provider: "ray" or "openai"

    Returns:
        An Embed client instance with start/close/embed_query/embed_documents methods.
    """
    provider = provider.lower().strip()

    if provider == "openai":
        from app.clients.openai_embed import OpenAIEmbedClient
        logger.info("Using OpenAI Embedding provider")
        return OpenAIEmbedClient()

    elif provider == "ray":
        from app.clients.ray_embed import RayEmbedClient
        logger.info("Using Ray/BGE-M3 Embedding provider")
        return RayEmbedClient()

    else:
        raise ValueError(
            f"Unknown EMBED_PROVIDER: '{provider}'. "
            f"Supported: 'ray', 'openai'"
        )
