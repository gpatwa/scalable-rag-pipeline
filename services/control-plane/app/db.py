# services/control-plane/app/db.py
"""
Control Plane database engine.

Uses async SQLAlchemy with the control plane's own database
(separate from the data plane's Postgres for chat history).
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import cp_settings

Base = declarative_base()

engine = None
AsyncSessionLocal = None


def init_engine(database_url: str | None = None):
    """Initialize the async engine and session factory."""
    global engine, AsyncSessionLocal
    url = database_url or cp_settings.DATABASE_URL
    engine = create_async_engine(url, echo=False)
    AsyncSessionLocal = sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )


async def create_tables():
    """Create all tables (for dev/testing — use Alembic in production)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """FastAPI dependency for database sessions."""
    async with AsyncSessionLocal() as session:
        yield session
