# services/api/app/memory/postgres.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, String, JSON, DateTime, Integer, Text
from datetime import datetime
from app.config import settings

# 1. Database Setup
Base = declarative_base()

# 2. Define the Chat History Table
class ChatHistory(Base):
    """
    Stores every conversation turn.
    """
    __tablename__ = "chat_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True) # User's conversation ID
    user_id = Column(String, index=True)
    role = Column(String) # "user" or "assistant"
    content = Column(Text) # The text message
    metadata_ = Column(JSON, default={}) # Extra info (latency, tokens used)
    created_at = Column(DateTime, default=datetime.utcnow)

# 3. Async Engine & Session
engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

class PostgresMemory:
    """
    Manager for persisting conversation state.
    """
    async def add_message(self, session_id: str, role: str, content: str, user_id: str):
        async with AsyncSessionLocal() as session:
            async with session.begin():
                msg = ChatHistory(
                    session_id=session_id,
                    role=role,
                    content=content,
                    user_id=user_id
                )
                session.add(msg)
                # Commit happens automatically via 'async with session.begin()'

    async def get_history(self, session_id: str, limit: int = 10):
        """
        Fetch last N messages for context window.
        """
        from sqlalchemy import select
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ChatHistory)
                .where(ChatHistory.session_id == session_id)
                .order_by(ChatHistory.created_at.desc())
                .limit(limit)
            )
            # Reverse to get chronological order (Oldest -> Newest)
            return result.scalars().all()[::-1]

postgres_memory = PostgresMemory()