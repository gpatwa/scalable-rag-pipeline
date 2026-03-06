# services/api/app/clients/graphdb/__init__.py
"""
GraphDB client abstraction layer.
Supports: Neo4j (default), Cosmos DB Gremlin (future), none (disabled).
"""
from app.clients.graphdb.base import GraphDBClient
from app.clients.graphdb.factory import create_graphdb_client

__all__ = ["GraphDBClient", "create_graphdb_client"]
