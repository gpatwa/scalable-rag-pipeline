# services/api/app/clients/graphdb/null_client.py
"""
Null (no-op) implementation of GraphDBClient.

Used when GRAPHDB_PROVIDER=none — disables graph search entirely,
so the retriever falls back to vector-only retrieval.
"""
import logging

logger = logging.getLogger(__name__)


class NullGraphClient:
    """
    A do-nothing GraphDBClient.
    All queries return empty results; all writes are silently ignored.
    """

    async def connect(self) -> None:
        logger.info("GraphDB disabled (GRAPHDB_PROVIDER=none).")

    async def close(self) -> None:
        pass

    @property
    def is_connected(self) -> bool:
        return True  # Always "healthy" since there's nothing to fail

    async def query_related(
        self,
        query: str,
        tenant_id: str,
        limit: int = 5,
    ) -> list[str]:
        return []

    async def upsert_triples(
        self,
        triples: list[dict],
        tenant_id: str,
    ) -> None:
        pass
