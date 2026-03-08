# services/api/app/clients/reranker/factory.py
"""
Factory for creating Re-ranker client instances.
Provider is selected via RERANKER_PROVIDER env var.

Supported providers:
  "none"           — Pass-through (no re-scoring)
  "llm"            — Single LLM call scores all docs
  "cross_encoder"  — Dedicated Ray Serve endpoint
"""
import logging

logger = logging.getLogger(__name__)


def create_reranker_client(provider: str, score_threshold: float = 0.3):
    """
    Create a Reranker client based on the provider name.

    Args:
        provider: "none", "llm", or "cross_encoder"
        score_threshold: Minimum relevance score (0.0-1.0) to keep a document.

    Returns:
        A RerankerClient instance with start/close/rerank methods.
    """
    provider = provider.lower().strip()

    if provider == "none":
        from app.clients.reranker.null_client import NullReranker

        logger.info("Using NullReranker (pass-through)")
        return NullReranker()

    elif provider == "llm":
        from app.clients.reranker.llm_reranker import LLMReranker

        logger.info(f"Using LLMReranker (threshold={score_threshold})")
        return LLMReranker(score_threshold=score_threshold)

    elif provider == "cross_encoder":
        from app.clients.reranker.cross_encoder_reranker import CrossEncoderReranker
        from app.config import settings

        logger.info(
            f"Using CrossEncoderReranker "
            f"(endpoint={settings.RERANKER_ENDPOINT}, threshold={score_threshold})"
        )
        return CrossEncoderReranker(
            endpoint=settings.RERANKER_ENDPOINT,
            score_threshold=score_threshold,
        )

    else:
        raise ValueError(
            f"Unknown RERANKER_PROVIDER: '{provider}'. "
            f"Supported: 'none', 'llm', 'cross_encoder'"
        )
