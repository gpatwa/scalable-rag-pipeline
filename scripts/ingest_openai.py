#!/usr/bin/env python3
"""
Quick document ingestion using OpenAI embeddings + Qdrant.
Designed to work from local machine with port-forwarded Qdrant.

Usage:
    OPENAI_API_KEY=sk-... python scripts/ingest_openai.py data/test-docs/aws_well_architected.pdf
"""
import asyncio
import os
import sys
import uuid
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "rag_collection")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


# ── PDF Parsing ─────────────────────────────────────────────────────────────
def parse_pdf(filepath: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(filepath)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            pages.append(text.strip())
    full_text = "\n\n".join(pages)
    logger.info(f"  Parsed PDF: {len(reader.pages)} pages, {len(full_text):,} chars")
    return full_text


# ── Chunking ────────────────────────────────────────────────────────────────
def chunk_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk.strip())
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# ── Embedding via OpenAI ────────────────────────────────────────────────────
async def embed_texts(texts: list[str]) -> list[list[float]]:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    all_embeddings = []

    # OpenAI supports batching up to ~2048 inputs, but let's batch by 100
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        response = await client.embeddings.create(model=EMBED_MODEL, input=batch)
        batch_embs = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embs)
        logger.info(f"  Embedded {len(all_embeddings)}/{len(texts)} chunks...")

    return all_embeddings


# ── Qdrant Upsert ──────────────────────────────────────────────────────────
def upsert_qdrant(chunks: list[str], embeddings: list[list[float]], filename: str):
    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    points = [
        models.PointStruct(
            id=str(uuid.uuid4()),
            vector=emb,
            payload={
                "text": chunk,
                "metadata": {"filename": filename, "chunk_index": i},
            },
        )
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]

    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        client.upsert(collection_name=QDRANT_COLLECTION, points=batch)

    logger.info(f"  Qdrant: upserted {len(points)} vectors into '{QDRANT_COLLECTION}'")


# ── Main ────────────────────────────────────────────────────────────────────
async def main():
    if len(sys.argv) < 2:
        print("Usage: OPENAI_API_KEY=sk-... python scripts/ingest_openai.py <pdf_file>")
        sys.exit(1)

    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        sys.exit(1)

    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY environment variable is required")
        sys.exit(1)

    filename = os.path.basename(filepath)
    logger.info("=" * 60)
    logger.info(f"  Ingesting: {filename}")
    logger.info("=" * 60)

    # 1. Parse
    text = parse_pdf(filepath)

    # 2. Chunk
    chunks = chunk_text(text)
    logger.info(f"  Chunked into {len(chunks)} pieces ({CHUNK_SIZE} chars, {CHUNK_OVERLAP} overlap)")

    # 3. Embed via OpenAI
    logger.info(f"  Embedding via OpenAI ({EMBED_MODEL})...")
    embeddings = await embed_texts(chunks)

    # 4. Upsert to Qdrant
    upsert_qdrant(chunks, embeddings, filename)

    logger.info("\n" + "=" * 60)
    logger.info(f"  Done! {len(chunks)} chunks indexed.")
    logger.info(f"  Try asking questions about '{filename}' in the chat UI.")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
