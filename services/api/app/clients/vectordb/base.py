# services/api/app/clients/vectordb/base.py
"""
Protocol definition for Vector DB clients.
All vector database providers must implement this interface.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class VectorDBClient(Protocol):
    """
    Interface for vector database operations.

    Implementations: Qdrant, Azure AI Search, Pinecone, etc.

    Search results are returned as plain dicts:
        [{"id": "...", "score": 0.95, "payload": {"text": "...", ...}}, ...]
    """

    async def connect(self) -> None:
        """Initialize connections / SDK clients."""
        ...

    async def close(self) -> None:
        """Clean up connections."""
        ...

    async def search(
        self,
        collection: str,
        vector: list[float],
        limit: int = 5,
        filters: dict | None = None,
        score_threshold: float | None = None,
    ) -> list[dict]:
        """
        Perform vector similarity search.

        Args:
            collection: Name of the collection/index to search.
            vector: Query embedding vector.
            limit: Maximum number of results.
            filters: Key-value pairs for metadata filtering
                     (e.g. {"tenant_id": "acme"}).
            score_threshold: Minimum similarity score to include.

        Returns:
            List of dicts: [{"id": ..., "score": ..., "payload": {...}}, ...]
        """
        ...

    async def upsert(
        self,
        collection: str,
        points: list[dict],
    ) -> None:
        """
        Insert or update vectors with payloads.

        Args:
            collection: Target collection/index.
            points: List of dicts, each with keys:
                    {"id": str, "vector": list[float], "payload": dict}
        """
        ...

    async def create_collection(
        self,
        collection: str,
        vector_size: int,
    ) -> None:
        """
        Create a collection/index if it doesn't exist.

        Args:
            collection: Name of the collection.
            vector_size: Dimensionality of vectors.
        """
        ...

    async def delete_by_filter(
        self,
        collection: str,
        filters: dict,
    ) -> None:
        """
        Delete vectors matching the given filters.

        Args:
            collection: Target collection/index.
            filters: Key-value pairs to match for deletion
                     (e.g. {"tenant_id": "acme"}).
        """
        ...
