# services/api/app/cache/semantic.py
import uuid
import logging
from typing import Optional
from app.clients.ray_embed import embed_client

logger = logging.getLogger(__name__)

DEFAULT_TENANT_ID = "default"
CACHE_COLLECTION = "semantic_cache"

# Late-initialised — set by main.py lifespan via set_vectordb_client()
_vectordb_client = None


def set_vectordb_client(client):
    """Called once during app startup to inject the abstracted VectorDB client."""
    global _vectordb_client
    _vectordb_client = client


class SemanticCache:
    """
    Implements Semantic Caching using Vector Search.
    Instead of exact string matching, we match by meaning.
    All cache entries are scoped by tenant_id for isolation.

    Uses the provider-agnostic VectorDBClient so caching works with
    Qdrant, Azure AI Search, or any other VectorDB backend.
    """

    async def get_cached_response(
        self,
        query: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        threshold: float = 0.95,
    ) -> Optional[str]:
        """
        Check if a similar query exists in the cache for this tenant.
        """
        try:
            # 1. Embed the incoming query (Fast CPU/GPU call)
            vector = await embed_client.embed_query(query)

            # 2. Search in the cache collection, filtered by tenant
            results = await _vectordb_client.search(
                collection=CACHE_COLLECTION,
                vector=vector,
                limit=1,
                filters={"tenant_id": tenant_id},
                score_threshold=threshold,
            )

            if results:
                hit = results[0]
                logger.info(
                    f"Semantic Cache Hit! Score: {hit['score']} (tenant={tenant_id})"
                )
                return hit["payload"]["answer"]

        except Exception as e:
            logger.warning(f"Semantic cache lookup failed: {e}")

        return None

    async def set_cached_response(
        self,
        query: str,
        answer: str,
        tenant_id: str = DEFAULT_TENANT_ID,
    ):
        """
        Save a Q&A pair to the cache, tagged with tenant_id.
        """
        try:
            # 1. Embed query
            vector = await embed_client.embed_query(query)

            # 2. Save to Vector DB with tenant_id in payload
            await _vectordb_client.upsert(
                collection=CACHE_COLLECTION,
                points=[
                    {
                        "id": str(uuid.uuid4()),
                        "vector": vector,
                        "payload": {
                            "query": query,
                            "answer": answer,
                            "tenant_id": tenant_id,
                        },
                    }
                ],
            )
        except Exception as e:
            logger.warning(f"Failed to write to semantic cache: {e}")


semantic_cache = SemanticCache()
