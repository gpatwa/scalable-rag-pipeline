# services/api/app/clients/vectordb/__init__.py
"""
VectorDB client abstraction layer.
Supports: Qdrant (default), Azure AI Search, Pinecone (future).
"""
from app.clients.vectordb.base import VectorDBClient
from app.clients.vectordb.factory import create_vectordb_client

__all__ = ["VectorDBClient", "create_vectordb_client"]
