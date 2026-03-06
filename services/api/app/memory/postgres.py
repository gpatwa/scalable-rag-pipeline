# services/api/app/memory/postgres.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, JSON, DateTime, Integer, Text, select, and_
from datetime import datetime
from app.config import settings

# 1. Database Setup
Base = declarative_base()

# Default tenant for backward compatibility
DEFAULT_TENANT_ID = "default"

# 2. Define the Chat History Table
class ChatHistory(Base):
    """
    Stores every conversation turn.
    """
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True)       # User's conversation ID
    user_id = Column(String, index=True)
    tenant_id = Column(String, index=True, default=DEFAULT_TENANT_ID, server_default=DEFAULT_TENANT_ID)
    role = Column(String)                          # "user" or "assistant"
    content = Column(Text)                         # The text message
    metadata_ = Column(JSON, default={})           # Extra info (latency, tokens used)
    created_at = Column(DateTime, default=datetime.utcnow)

# 3. Async Engine & Session
engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

class PostgresMemory:
    """
    Manager for persisting conversation state.
    All operations are scoped by tenant_id to enforce data isolation.
    """
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: str,
        tenant_id: str = DEFAULT_TENANT_ID,
    ):
        """Store a single conversation turn, tagged with tenant_id."""
        async with AsyncSessionLocal() as session:
            async with session.begin():
                msg = ChatHistory(
                    session_id=session_id,
                    role=role,
                    content=content,
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
                session.add(msg)
                # Commit happens automatically via 'async with session.begin()'

    async def get_history(
        self,
        session_id: str,
        limit: int = 10,
        user_id: str | None = None,
        tenant_id: str = DEFAULT_TENANT_ID,
    ):
        """
        Fetch last N messages for context window.

        Filters by session_id AND tenant_id.
        Optionally also by user_id for session ownership validation.
        """
        async with AsyncSessionLocal() as session:
            conditions = [
                ChatHistory.session_id == session_id,
                ChatHistory.tenant_id == tenant_id,
            ]
            if user_id is not None:
                conditions.append(ChatHistory.user_id == user_id)

            result = await session.execute(
                select(ChatHistory)
                .where(and_(*conditions))
                .order_by(ChatHistory.created_at.desc())
                .limit(limit)
            )
            # Reverse to get chronological order (Oldest -> Newest)
            return result.scalars().all()[::-1]

    async def session_belongs_to(
        self,
        session_id: str,
        user_id: str,
        tenant_id: str,
    ) -> bool | None:
        """
        Verify that a session belongs to the given user+tenant.

        Returns:
            True  – session exists and belongs to this user+tenant
            False – session exists but belongs to someone else (cross-tenant!)
            None  – session is brand new (no messages yet)
        """
        async with AsyncSessionLocal() as session:
            # Check if any messages exist for this session_id at all
            result = await session.execute(
                select(ChatHistory.user_id, ChatHistory.tenant_id)
                .where(ChatHistory.session_id == session_id)
                .limit(1)
            )
            row = result.first()

            if row is None:
                # Brand-new session — anyone can claim it
                return None

            # Session exists — verify ownership
            return row.user_id == user_id and row.tenant_id == tenant_id


postgres_memory = PostgresMemory()
