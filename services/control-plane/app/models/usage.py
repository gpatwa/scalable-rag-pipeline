# services/control-plane/app/models/usage.py
"""
Usage tracking model for billing and analytics.
"""
from sqlalchemy import Column, String, Integer, DateTime
from datetime import datetime
from ..db import Base


class UsageEvent(Base):
    """A single usage event (chat query, upload, feedback)."""
    __tablename__ = "usage_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)  # "chat" | "upload" | "feedback"
    token_count = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
