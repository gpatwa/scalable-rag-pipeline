# services/api/app/clients/graphdb/factory.py
"""
Factory for creating GraphDB client instances.
Provider is selected via GRAPHDB_PROVIDER env var.

Supported providers:
  "neo4j"    — Neo4j (default)
  "cosmosdb" — Azure Cosmos DB Gremlin API (future)
  "none"     — Disabled (vector-only retrieval)
"""
import logging

logger = logging.getLogger(__name__)


def create_graphdb_client(provider: str):
    """
    Create a GraphDB client based on the provider name.

    Args:
        provider: "neo4j", "cosmosdb", or "none"

    Returns:
        A GraphDBClient instance.
    """
    provider = provider.lower().strip()

    if provider == "neo4j":
        from app.clients.graphdb.neo4j_impl import Neo4jGraphClient
        from app.config import settings

        logger.info("Using Neo4j GraphDB provider")
        return Neo4jGraphClient(
            uri=settings.NEO4J_URI,
            user=settings.NEO4J_USER,
            password=settings.NEO4J_PASSWORD,
        )

    elif provider == "cosmosdb":
        raise NotImplementedError(
            "Cosmos DB Gremlin provider is not yet implemented. "
            "Add 'gremlinpython' to requirements and implement "
            "app.clients.graphdb.cosmosdb.CosmosDBGraphClient."
        )

    elif provider == "none":
        from app.clients.graphdb.null_client import NullGraphClient

        logger.info("GraphDB disabled (provider=none), using NullGraphClient")
        return NullGraphClient()

    else:
        raise ValueError(
            f"Unknown GRAPHDB_PROVIDER: '{provider}'. "
            f"Supported: 'neo4j', 'cosmosdb', 'none'"
        )
