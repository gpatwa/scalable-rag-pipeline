#!/usr/bin/env python3
"""
One-command local environment initializer.
Usage: python scripts/init_local.py
  OR:  make init

Runs all setup steps:
  1. Postgres — creates tables (chat_history)
  2. Qdrant   — creates collections (rag_collection, semantic_cache)
  3. Neo4j    — creates fulltext index + constraints
  4. MinIO    — creates the S3 bucket
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── 1. Postgres ──────────────────────────────────────────────────────────────
async def init_postgres():
    print("\n[1/4] Postgres — creating tables...")
    from services.api.app.memory.postgres import Base, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from sqlalchemy import inspect
    async with engine.connect() as conn:
        tables = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
    await engine.dispose()
    print(f"  ✅ Tables: {tables}")


# ── 2. Qdrant ────────────────────────────────────────────────────────────────
def init_qdrant():
    print("\n[2/4] Qdrant — creating collections...")
    from qdrant_client import QdrantClient
    from qdrant_client.http import models
    from services.api.app.config import settings

    VECTOR_DIM = 4096  # llama3 via Ollama

    client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    existing = [c.name for c in client.get_collections().collections]

    for name in [settings.QDRANT_COLLECTION, "semantic_cache"]:
        if name in existing:
            print(f"  ⏭️  '{name}' already exists")
        else:
            client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=VECTOR_DIM,
                    distance=models.Distance.COSINE,
                ),
            )
            print(f"  ✅ Created '{name}' (dim={VECTOR_DIM}, cosine)")


# ── 3. Neo4j ─────────────────────────────────────────────────────────────────
def init_neo4j():
    print("\n[3/4] Neo4j — creating indexes...")
    from neo4j import GraphDatabase
    from services.api.app.config import settings

    driver = GraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )

    with driver.session() as session:
        try:
            session.run(
                "CREATE CONSTRAINT entity_name IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE e.name IS UNIQUE"
            )
            print("  ✅ Uniqueness constraint on Entity.name")
        except Exception as e:
            print(f"  ⏭️  Constraint: {e}")

        try:
            session.run(
                "CREATE FULLTEXT INDEX entity_index IF NOT EXISTS "
                "FOR (n:Entity) ON EACH [n.name]"
            )
            print("  ✅ Fulltext index 'entity_index'")
        except Exception as e:
            print(f"  ⏭️  Fulltext index: {e}")

    driver.close()


# ── 4. MinIO (S3 bucket) ─────────────────────────────────────────────────────
def init_minio():
    print("\n[4/4] MinIO — creating S3 bucket...")
    import boto3
    from botocore.exceptions import ClientError
    from services.api.app.config import settings

    if not settings.S3_ENDPOINT_URL:
        print("  ⏭️  S3_ENDPOINT_URL not set — skipping (using real AWS)")
        return

    s3 = boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )

    try:
        s3.head_bucket(Bucket=settings.S3_BUCKET_NAME)
        print(f"  ⏭️  Bucket '{settings.S3_BUCKET_NAME}' already exists")
    except ClientError:
        s3.create_bucket(Bucket=settings.S3_BUCKET_NAME)
        print(f"  ✅ Created bucket '{settings.S3_BUCKET_NAME}'")


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    print("=" * 55)
    print("  RAG Platform — Local Environment Setup")
    print("=" * 55)

    await init_postgres()
    init_qdrant()
    init_neo4j()
    init_minio()

    print("\n" + "=" * 55)
    print("  ✅  All done!  Run `make dev` to start the API.")
    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
