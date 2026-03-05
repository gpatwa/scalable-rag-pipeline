#!/usr/bin/env python3
"""
Local Development Database Initializer.
Creates all SQLAlchemy tables if they don't exist.
For production, use Alembic migrations instead.
"""
import asyncio
import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.api.app.config import settings
from services.api.app.memory.postgres import Base, engine


async def init_db():
    print(f"Connecting to: {settings.DATABASE_URL.split('@')[1]}")  # Hide credentials
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database tables created successfully.")

    # Verify tables exist
    from sqlalchemy import inspect
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        print(f"   Tables: {tables}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())
