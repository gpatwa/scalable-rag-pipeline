# services/api/app/clients/reranker/base.py
"""
Protocol definition for Re-ranker clients.
All re-ranker providers must implement this interface.
"""
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class ScoredDocument:
    """A document with a normalized relevance score (0.0–1.0)."""
    text: str
    score: float  # 0.0 (irrelevant) to 1.0 (highly relevant)
    original_rank: int  # Position in the original retrieval results


@runtime_checkable
class RerankerClient(Protocol):
    """
    Interface for re-ranking operations.

    Implementations: NullReranker, LLMReranker, CrossEncoderReranker.

    The rerank() method takes a query and a list of document texts,
    and returns them re-ordered by relevance with normalized scores.
    Documents below the score threshold are filtered out (but at least
    one document is always kept).
    """

    async def start(self) -> None:
        """Initialize connections / SDK clients."""
        ...

    async def close(self) -> None:
        """Clean up connections."""
        ...

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int = 8,
    ) -> list[ScoredDocument]:
        """
        Re-rank documents by relevance to the query.

        Args:
            query: The user's search query.
            documents: List of document texts to re-rank.
            top_k: Maximum number of results to return.

        Returns:
            List of ScoredDocument, sorted by score descending.
            Documents below the provider's threshold are removed
            (always keeps at least 1).
        """
        ...
