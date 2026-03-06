# services/api/app/agents/nodes/retriever.py
import asyncio
from typing import Dict, List
from langchain_core.runnables import RunnableConfig
from app.agents.state import AgentState
from app.clients.ray_embed import embed_client
from app.config import settings
import logging

logger = logging.getLogger(__name__)

DEFAULT_TENANT_ID = "default"

# ------------------------------------------------------------------
# Late-initialised references — set by main.py lifespan via set_clients()
# ------------------------------------------------------------------
_vectordb_client = None
_graphdb_client = None


def set_clients(vectordb, graphdb):
    """Called once during app startup to inject abstracted clients."""
    global _vectordb_client, _graphdb_client
    _vectordb_client = vectordb
    _graphdb_client = graphdb


async def retrieve_node(state: AgentState, config: RunnableConfig) -> Dict:
    """
    Executes Hybrid Retrieval:
    1. Embeds the user query.
    2. Runs Vector Search AND Graph Search concurrently.
    3. Merges and deduplicates results.

    Both searches are filtered by tenant_id from the LangGraph config
    to enforce cross-tenant data isolation.

    Uses the provider-agnostic VectorDBClient and GraphDBClient
    (set via set_clients() at startup), so the retriever works with
    Qdrant, Azure AI Search, Neo4j, Cosmos DB, or none.
    """
    query = state["current_query"]

    # Extract tenant_id from LangGraph configurable (set in chat.py)
    configurable = config.get("configurable", {})
    tenant_id = configurable.get("tenant_id", DEFAULT_TENANT_ID)

    logger.info(f"Retrieving context for: {query} (tenant={tenant_id})")

    # Step 1: Get Embedding for the query (Call Ray Serve / OpenAI)
    query_vector = await embed_client.embed_query(query)

    # Step 2: Define the tasks for Parallel Execution

    # Task A: Vector Search (Semantic Similarity) — filtered by tenant_id
    async def run_vector_search():
        results = await _vectordb_client.search(
            collection=settings.QDRANT_COLLECTION,
            vector=query_vector,
            limit=5,
            filters={"tenant_id": tenant_id},
        )
        # results are plain dicts: {"id", "score", "payload"}
        return [
            f"{r['payload']['text']} [Source: {r['payload'].get('filename', r['payload'].get('metadata', {}).get('filename', 'unknown'))}]"
            for r in results
        ]

    # Task B: Graph Search (Structural Relationships) — filtered by tenant_id
    async def run_graph_search():
        try:
            return await _graphdb_client.query_related(
                query=query, tenant_id=tenant_id, limit=5
            )
        except Exception as e:
            logger.error(f"Graph search failed: {e}")
            return []

    # Step 3: Run both in parallel!
    vector_docs, graph_docs = await asyncio.gather(
        run_vector_search(), run_graph_search()
    )

    # Step 4: Merge and Deduplicate
    combined_docs = list(set(vector_docs + graph_docs))

    logger.info(f"Retrieved {len(combined_docs)} documents (tenant={tenant_id}).")

    # Update State
    return {"documents": combined_docs}
