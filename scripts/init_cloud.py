#!/usr/bin/env python3
"""
scripts/init_cloud.py
Initialize cloud databases after EKS deployment.

Creates Qdrant collections, Neo4j indexes, and Postgres tables
against the cloud endpoints.

Usage:
  # If running outside the VPC, port-forward first:
  kubectl port-forward svc/qdrant 6333:6333 &
  kubectl port-forward svc/neo4j-cluster 7687:7687 &
  kubectl port-forward svc/<aurora-proxy> 5432:5432 &

  # Then run:
  python3 scripts/init_cloud.py

  # Or pass endpoints directly:
  python3 scripts/init_cloud.py \\
      --qdrant-host localhost --qdrant-port 6333 \\
      --neo4j-uri bolt://localhost:7687 \\
      --db-url "postgresql+asyncpg://ragadmin:PASS@localhost:5432/ragdb"
"""

import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def init_qdrant(host: str, port: int):
    """Create Qdrant collections for vector search and semantic cache."""
    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    print(f"\n--- Qdrant ({host}:{port}) ---")
    client = QdrantClient(host=host, port=port, timeout=30)

    collections = {
        "rag_collection": {
            "size": 4096,
            "distance": models.Distance.COSINE,
        },
        "semantic_cache": {
            "size": 4096,
            "distance": models.Distance.COSINE,
        },
    }

    existing = {c.name for c in client.get_collections().collections}

    for name, config in collections.items():
        if name in existing:
            info = client.get_collection(name)
            print(f"  {name}: already exists ({info.points_count} points)")
        else:
            client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=config["size"],
                    distance=config["distance"],
                ),
            )
            print(f"  {name}: CREATED (dim={config['size']})")


def init_neo4j(uri: str, user: str, password: str):
    """Create Neo4j fulltext index and uniqueness constraint."""
    from neo4j import GraphDatabase

    print(f"\n--- Neo4j ({uri}) ---")
    driver = GraphDatabase.driver(uri, auth=(user, password))

    with driver.session() as session:
        # Uniqueness constraint
        try:
            session.run(
                "CREATE CONSTRAINT entity_name IF NOT EXISTS "
                "FOR (e:Entity) REQUIRE e.name IS UNIQUE"
            )
            print("  Constraint entity_name: OK")
        except Exception as e:
            print(f"  Constraint entity_name: {e}")

        # Fulltext index
        try:
            session.run(
                "CREATE FULLTEXT INDEX entity_index IF NOT EXISTS "
                "FOR (e:Entity) ON EACH [e.name, e.description]"
            )
            print("  Fulltext index entity_index: OK")
        except Exception as e:
            print(f"  Fulltext index entity_index: {e}")

        # Verify
        result = session.run("MATCH (n:Entity) RETURN count(n) as cnt")
        cnt = result.single()["cnt"]
        print(f"  Entity nodes: {cnt}")

    driver.close()


def init_postgres(db_url: str):
    """Create Postgres tables using SQLAlchemy models."""
    print(f"\n--- Postgres ---")

    try:
        from sqlalchemy import create_engine
        from services.api.app.models.db import Base

        sync_url = db_url.replace("+asyncpg", "").replace("+aiopg", "")
        engine = create_engine(sync_url)
        Base.metadata.create_all(engine)
        engine.dispose()
        print("  Tables: created/verified")
    except ImportError:
        print("  SKIP: SQLAlchemy models not available (install greenlet)")
    except Exception as e:
        print(f"  ERROR: {e}")


def main():
    parser = argparse.ArgumentParser(description="Initialize cloud databases")
    parser.add_argument("--qdrant-host", default="localhost", help="Qdrant host")
    parser.add_argument("--qdrant-port", type=int, default=6333, help="Qdrant port")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687", help="Neo4j URI")
    parser.add_argument("--neo4j-user", default="neo4j", help="Neo4j username")
    parser.add_argument("--neo4j-password", default="password", help="Neo4j password")
    parser.add_argument("--db-url", default=None, help="Postgres connection URL")
    args = parser.parse_args()

    print("=" * 50)
    print("  Cloud Database Initialization")
    print("=" * 50)

    # Qdrant
    try:
        init_qdrant(args.qdrant_host, args.qdrant_port)
    except Exception as e:
        print(f"  Qdrant ERROR: {e}")
        print("  Hint: kubectl port-forward svc/qdrant 6333:6333 &")

    # Neo4j
    try:
        init_neo4j(args.neo4j_uri, args.neo4j_user, args.neo4j_password)
    except Exception as e:
        print(f"  Neo4j ERROR: {e}")
        print("  Hint: kubectl port-forward svc/neo4j-cluster 7687:7687 &")

    # Postgres (only if URL provided)
    if args.db_url:
        try:
            init_postgres(args.db_url)
        except Exception as e:
            print(f"  Postgres ERROR: {e}")
    else:
        print("\n--- Postgres ---")
        print("  SKIP: No --db-url provided (tables auto-created by API on startup)")

    print("\n" + "=" * 50)
    print("  Initialization Complete!")
    print("=" * 50)


if __name__ == "__main__":
    main()
