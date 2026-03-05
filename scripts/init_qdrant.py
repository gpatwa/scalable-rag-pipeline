#!/usr/bin/env python3
"""
Creates required Qdrant collections for local development.
Collections: rag_collection (main retrieval), semantic_cache (query cache).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qdrant_client import QdrantClient
from qdrant_client.http import models
from services.api.app.config import settings

# Embedding dimension — 4096 for llama3 via Ollama
VECTOR_DIM = 4096

client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

collections_to_create = [
    settings.QDRANT_COLLECTION,  # "rag_collection"
    "semantic_cache",
]

for name in collections_to_create:
    existing = [c.name for c in client.get_collections().collections]
    if name in existing:
        print(f"⏭️  Collection '{name}' already exists (skipping)")
    else:
        client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(
                size=VECTOR_DIM,
                distance=models.Distance.COSINE,
            ),
        )
        print(f"✅ Created collection '{name}' (dim={VECTOR_DIM}, cosine)")

# Verify
print(f"\nCollections: {[c.name for c in client.get_collections().collections]}")
