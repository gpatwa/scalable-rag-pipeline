# services/api/app/clients/vectordb/factory.py
"""
Factory for creating VectorDB client instances.
Provider is selected via VECTORDB_PROVIDER env var.

Supported providers:
  "qdrant"           — Self-hosted or Qdrant Cloud
  "azure_ai_search"  — Azure AI Search (future)
  "pinecone"         — Pinecone (future)
"""
import logging

logger = logging.getLogger(__name__)


def create_vectordb_client(provider: str):
    """
    Create a VectorDB client based on the provider name.

    Args:
        provider: "qdrant", "azure_ai_search", or "pinecone"

    Returns:
        A VectorDBClient instance.
    """
    provider = provider.lower().strip()

    if provider == "qdrant":
        from app.clients.vectordb.qdrant_impl import QdrantVectorClient
        from app.config import settings

        use_grpc = settings.ENV != "dev"
        logger.info("Using Qdrant VectorDB provider")
        return QdrantVectorClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            prefer_grpc=use_grpc,
        )

    elif provider == "azure_ai_search":
        raise NotImplementedError(
            "Azure AI Search provider is not yet implemented. "
            "Add 'azure-search-documents' to requirements and implement "
            "app.clients.vectordb.azure_ai_search.AzureAISearchClient."
        )

    elif provider == "pinecone":
        raise NotImplementedError(
            "Pinecone provider is not yet implemented. "
            "Add 'pinecone-client' to requirements and implement "
            "app.clients.vectordb.pinecone_impl.PineconeVectorClient."
        )

    else:
        raise ValueError(
            f"Unknown VECTORDB_PROVIDER: '{provider}'. "
            f"Supported: 'qdrant', 'azure_ai_search', 'pinecone'"
        )
