# services/api/app/agents/nodes/retriever.py
import asyncio
from typing import Dict, List
from app.agents.state import AgentState
from app.clients.qdrant import qdrant_client
from app.clients.neo4j import neo4j_client
from app.clients.ray_embed import embed_client # To be implemented
import logging

logger = logging.getLogger(__name__)

async def retrieve_node(state: AgentState) -> Dict:
    """
    Executes Hybrid Retrieval:
    1. Embeds the user query.
    2. Runs Vector Search (Qdrant) AND Graph Search (Neo4j) concurrently.
    3. Merges and deduplicates results.
    """
    query = state["current_query"]
    logger.info(f"Retrieving context for: {query}")

    # Step 1: Get Embedding for the query (Call Ray Serve)
    # We await this because we need the vector for Qdrant
    query_vector = await embed_client.embed_query(query)

    # Step 2: Define the tasks for Parallel Execution
    
    # Task A: Vector Search (Semantic Similarity)
    async def run_vector_search():
        results = await qdrant_client.search(vector=query_vector, limit=5)
        # Format: "Content [Source: Page 1]"
        return [f"{r.payload['text']} [Source: {r.payload['metadata']['filename']}]" for r in results]

    # Task B: Graph Search (Structural Relationships)
    # We use a keyword match or a pre-defined Cypher template here.
    async def run_graph_search():
        cypher = """
        CALL db.index.fulltext.queryNodes("entity_index", $query) YIELD node, score
        MATCH (node)-[r]->(neighbor)
        RETURN node.name + ' ' + type(r) + ' ' + neighbor.name as text
        LIMIT 5
        """
        # Note: Lucene syntax for fulltext search might need fuzzy matching (~).
        try:
            results = await neo4j_client.query(cypher, {"query": query})
            return [r['text'] for r in results]
        except Exception as e:
            logger.error(f"Graph search failed: {e}")
            return []

    # Step 3: Run both in parallel!
    vector_docs, graph_docs = await asyncio.gather(run_vector_search(), run_graph_search())

    # Step 4: Merge and Deduplicate
    # We prioritize Graph results for specific facts, Vector for general context.
    combined_docs = list(set(vector_docs + graph_docs))
    
    logger.info(f"Retrieved {len(combined_docs)} documents.")

    # Update State
    return {"documents": combined_docs}