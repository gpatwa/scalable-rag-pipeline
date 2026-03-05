#!/usr/bin/env python3
"""
Creates required Neo4j constraints and fulltext indexes for local dev.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neo4j import GraphDatabase
from services.api.app.config import settings

driver = GraphDatabase.driver(
    settings.NEO4J_URI,
    auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
)

with driver.session() as session:
    # 1. Create Entity node label constraint (optional, ensures uniqueness)
    try:
        session.run("CREATE CONSTRAINT entity_name IF NOT EXISTS FOR (e:Entity) REQUIRE e.name IS UNIQUE")
        print("✅ Created uniqueness constraint on Entity.name")
    except Exception as e:
        print(f"⏭️  Constraint: {e}")

    # 2. Create the fulltext index used by the retriever
    try:
        session.run(
            'CREATE FULLTEXT INDEX entity_index IF NOT EXISTS '
            'FOR (n:Entity) ON EACH [n.name]'
        )
        print("✅ Created fulltext index 'entity_index' on Entity.name")
    except Exception as e:
        print(f"⏭️  Fulltext index: {e}")

    # 3. Verify
    result = session.run("SHOW INDEXES YIELD name, type RETURN name, type")
    print("\nNeo4j Indexes:")
    for record in result:
        print(f"   {record['name']} ({record['type']})")

driver.close()
print("\n✅ Neo4j initialization complete.")
