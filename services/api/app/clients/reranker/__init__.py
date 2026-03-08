# services/api/app/clients/reranker/__init__.py
"""
Re-ranking client module.

Provides a provider-based re-ranking layer that rescores retrieved
documents for better relevance ordering.

Providers:
  - "none"           → NullReranker (pass-through, no re-scoring)
  - "llm"            → LLMReranker (single LLM call scores N docs)
  - "cross_encoder"  → CrossEncoderReranker (Ray Serve endpoint)
"""
from app.clients.reranker.base import RerankerClient, ScoredDocument
from app.clients.reranker.factory import create_reranker_client

__all__ = ["RerankerClient", "ScoredDocument", "create_reranker_client"]
