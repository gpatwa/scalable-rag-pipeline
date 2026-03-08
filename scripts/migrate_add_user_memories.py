#!/usr/bin/env python3
"""
Database migration: Create user_memories table for long-term memory.

Stores user preferences and facts across sessions.
Can be run safely multiple times (idempotent).

Usage:
    python scripts/migrate_add_user_memories.py
    python scripts/migrate_add_user_memories.py --dry-run
"""
import asyncio
import argparse
import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", "api"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

MIGRATION_SQL = [
    """
    CREATE TABLE IF NOT EXISTS user_memories (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        tenant_id VARCHAR(255) NOT NULL DEFAULT 'default',
        memory_type VARCHAR(50) NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_user_memories_user_tenant
    ON user_memories (user_id, tenant_id);
    """,
]


async def run_migration(dry_run: bool = False):
    from app.config import settings

    db_url = settings.DATABASE_URL
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    logger.info("=" * 55)
    logger.info("  Migration: Create user_memories table")
    logger.info("=" * 55)
    logger.info(f"  Database: {sync_url.split('@')[1] if '@' in sync_url else '***'}")
    logger.info(f"  Mode:     {'DRY RUN' if dry_run else 'EXECUTE'}")
    logger.info("=" * 55)

    if dry_run:
        logger.info("\nSQL to be executed:\n")
        for i, sql in enumerate(MIGRATION_SQL, 1):
            logger.info(f"-- Statement {i}")
            logger.info(sql.strip())
            logger.info("")
        logger.info("(Dry run — no changes made)")
        return

    try:
        import asyncpg

        conn = await asyncpg.connect(sync_url)

        for i, sql in enumerate(MIGRATION_SQL, 1):
            logger.info(f"  Executing statement {i}/{len(MIGRATION_SQL)}...")
            await conn.execute(sql)

        result = await conn.fetchval(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'user_memories'"
        )
        if result == 1:
            logger.info("\n  ✅ Migration successful! user_memories table exists.")
        else:
            logger.error("\n  ❌ Migration may have failed — table not found.")

        await conn.close()

    except ImportError:
        logger.error("  asyncpg not installed. Install with: pip install asyncpg")
        sys.exit(1)
    except Exception as e:
        logger.error(f"  ❌ Migration failed: {e}")
        sys.exit(1)

    logger.info("\n" + "=" * 55)
    logger.info("  Done!")
    logger.info("=" * 55)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create user_memories table")
    parser.add_argument("--dry-run", action="store_true", help="Print SQL without executing")
    args = parser.parse_args()

    asyncio.run(run_migration(dry_run=args.dry_run))
