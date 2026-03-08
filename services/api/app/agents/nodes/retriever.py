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
_reranker_client = None


def set_clients(vectordb, graphdb, reranker=None):
    """Called once during app startup to inject abstracted clients."""
    global _vectordb_client, _graphdb_client, _reranker_client
    _vectordb_client = vectordb
    _graphdb_client = graphdb
    _reranker_client = reranker


async def retrieve_node(state: AgentState, config: RunnableConfig) -> Dict:
    """
    Executes Hybrid Retrieval with optional Re-ranking:
    1. Embeds the user query.
    2. Runs Vector Search AND Graph Search concurrently.
    3. Merges and deduplicates results.
    4. Re-ranks merged results (if reranker is configured).

    Both searches are filtered by tenant_id from the LangGraph config
    to enforce cross-tenant data isolation.

    Uses the provider-agnostic VectorDBClient, GraphDBClient, and
    RerankerClient (set via set_clients() at startup).
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
    # Fetch more candidates (15) to account for duplicates, then deduplicate
    async def run_vector_search():
        results = await _vectordb_client.search(
            collection=settings.QDRANT_COLLECTION,
            vector=query_vector,
            limit=15,
            filters={"tenant_id": tenant_id},
        )
        # Deduplicate by text content (duplicate ingestions create identical chunks)
        seen_texts = set()
        unique_docs = []
        for r in results:
            text = r['payload']['text']
            if text not in seen_texts:
                seen_texts.add(text)
                filename = r['payload'].get('filename',
                    r['payload'].get('metadata', {}).get('filename', 'unknown'))
                unique_docs.append(f"{text} [Source: {filename}]")
            if len(unique_docs) >= 8:
                break
        return unique_docs

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

    # Step 4: Merge (graph docs first for priority, then vector)
    combined_docs = graph_docs + [d for d in vector_docs if d not in graph_docs]

    logger.info(
        f"Retrieved {len(combined_docs)} docs "
        f"(vector={len(vector_docs)}, graph={len(graph_docs)}, tenant={tenant_id})"
    )

    # Step 5: Re-rank merged results (if reranker is configured)
    if _reranker_client and combined_docs:
        try:
            scored_docs = await _reranker_client.rerank(
                query=query, documents=combined_docs, top_k=8
            )
            reranked_docs = [sd.text for sd in scored_docs]

            # Log re-ranking effect
            logger.info(
                f"Re-ranked {len(combined_docs)} → {len(reranked_docs)} docs "
                f"(top score: {scored_docs[0].score:.2f})"
            )
            combined_docs = reranked_docs
        except Exception as e:
            logger.warning(f"Re-ranking failed ({e}), using original order")

    if combined_docs:
        logger.info(f"First doc preview: {combined_docs[0][:120]}...")
    else:
        logger.warning(f"No documents found for query: '{query}'")

    # Update State
    return {"documents": combined_docs}
