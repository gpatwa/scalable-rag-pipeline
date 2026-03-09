# services/control-plane/tests/conftest.py
"""
Shared fixtures for control plane tests.

Ensures all models are imported before create_tables() so that
Base.metadata has all tables (resolves ForeignKey references).
"""
import os
import sys

# Ensure control plane app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set env vars before any app imports
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-cp-secret")
os.environ.setdefault("INTERNAL_API_KEY", "test-internal-key")
os.environ.setdefault("ENV", "dev")
os.environ.setdefault("RATE_LIMIT_DEFAULT_RPM", "10")

import pytest  # noqa: E402


@pytest.fixture
async def db_session():
    """
    Create a fresh in-memory database with all tables for each test.

    Imports all models to ensure Base.metadata is complete before
    calling create_tables(). Each test gets a fresh DB.
    """
    import app.db as db_module
    from app.db import init_engine, create_tables

    # Import ALL models so Base.metadata has all tables
    import app.models.tenant  # noqa: F401
    import app.models.data_plane  # noqa: F401
    import app.models.usage  # noqa: F401

    init_engine("sqlite+aiosqlite:///:memory:")
    await create_tables()
    # Access the module-level attribute (not a stale local copy)
    yield db_module.AsyncSessionLocal
