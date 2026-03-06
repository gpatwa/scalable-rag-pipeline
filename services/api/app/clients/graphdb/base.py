# services/api/app/clients/graphdb/base.py
"""
Protocol definition for Graph DB clients.
All graph database providers must implement this interface.

The interface uses `query_related()` instead of raw Cypher so that
implementations can translate to Gremlin (Cosmos DB), SPARQL, or
other graph query languages.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class GraphDBClient(Protocol):
    """
    Interface for graph database operations.

    Implementations: Neo4j, Cosmos DB (Gremlin API), etc.
    Setting GRAPHDB_PROVIDER=none returns a NullGraphClient that
    gracefully returns empty results (vector-only retrieval).
    """

    async def connect(self) -> None:
        """Initialize connections / driver pools."""
        ...

    async def close(self) -> None:
        """Clean up connections."""
        ...

    async def query_related(
        self,
        query: str,
        tenant_id: str,
        limit: int = 5,
    ) -> list[str]:
        """
        Find graph-connected context for the given query.

        Args:
            query: Natural-language search query (used for full-text
                   index matching or embedding lookup).
            tenant_id: Only return results belonging to this tenant.
            limit: Maximum number of relationship strings to return.

        Returns:
            List of human-readable relationship strings, e.g.
            ["AWS RELATED_TO Cloud", "S3 STORES Objects"]
        """
        ...

    async def upsert_triples(
        self,
        triples: list[dict],
        tenant_id: str,
    ) -> None:
        """
        Insert or merge entity triples into the graph.

        Args:
            triples: List of {"source": str, "target": str, "type": str}
            tenant_id: Tag all created nodes/edges with this tenant.
        """
        ...
