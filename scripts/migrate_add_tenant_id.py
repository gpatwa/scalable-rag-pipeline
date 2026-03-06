#!/usr/bin/env python3
"""
Database migration: Add tenant_id column to chat_history.

This is a standalone migration script for Milestone 1 (Multi-Tenant Support).
It can be run safely multiple times (idempotent).

Usage:
    # Local dev (requires .env or DATABASE_URL env var)
    python scripts/migrate_add_tenant_id.py

    # Against remote DB (e.g. port-forwarded Aurora)
    DATABASE_URL="postgresql://user:pass@host:5432/ragdb" python scripts/migrate_add_tenant_id.py

    # Dry-run mode (print SQL without executing)
    python scripts/migrate_add_tenant_id.py --dry-run
"""
import asyncio
import argparse
import os
import sys
import logging

# Allow importing from the services/api directory
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", "api"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# SQL statements for the migration
MIGRATION_SQL = [
    # 1. Add tenant_id column with default value (safe for existing rows)
    """
    ALTER TABLE chat_history
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(255) NOT NULL DEFAULT 'default';
    """,

    # 2. Create index on tenant_id for query performance
    """
    CREATE INDEX IF NOT EXISTS ix_chat_history_tenant_id
    ON chat_history (tenant_id);
    """,

    # 3. Create composite index for the most common query pattern:
    #    SELECT * FROM chat_history WHERE session_id = ? AND tenant_id = ?
    """
    CREATE INDEX IF NOT EXISTS ix_chat_history_session_tenant
    ON chat_history (session_id, tenant_id);
    """,
]


async def run_migration(dry_run: bool = False):
    """Execute the migration against the configured database."""
    # Import settings after sys.path is set up
    from app.config import settings

    # Use the sync version of the URL for psycopg2 / raw SQL
    db_url = settings.DATABASE_URL
    # Convert async URL to sync for raw connection
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    logger.info("=" * 55)
    logger.info("  Migration: Add tenant_id to chat_history")
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

        conn = await asyncpg.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))

        for i, sql in enumerate(MIGRATION_SQL, 1):
            logger.info(f"  Executing statement {i}/{len(MIGRATION_SQL)}...")
            await conn.execute(sql)

        # Verify the column exists
        result = await conn.fetchval(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_name = 'chat_history' AND column_name = 'tenant_id'"
        )
        if result == 1:
            logger.info("\n  ✅ Migration successful! tenant_id column is present.")
        else:
            logger.error("\n  ❌ Migration may have failed — column not found.")

        # Show current row count and default distribution
        total = await conn.fetchval("SELECT COUNT(*) FROM chat_history")
        default_count = await conn.fetchval(
            "SELECT COUNT(*) FROM chat_history WHERE tenant_id = 'default'"
        )
        logger.info(f"  Total rows: {total}, rows with tenant_id='default': {default_count}")

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
    parser = argparse.ArgumentParser(description="Add tenant_id column to chat_history")
    parser.add_argument("--dry-run", action="store_true", help="Print SQL without executing")
    args = parser.parse_args()

    asyncio.run(run_migration(dry_run=args.dry_run))
