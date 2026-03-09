# services/control-plane/app/models/tenant.py
"""
Tenant model for the control plane database.

Each tenant represents a customer organization that has one or more
data planes deployed in their environment.
"""
from sqlalchemy import Column, String, Integer, Boolean, JSON, DateTime
from datetime import datetime
from ..db import Base


class Tenant(Base):
    """A customer organization."""
    __tablename__ = "tenants"

    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    plan = Column(String(50), default="free")  # "free" | "starter" | "enterprise"
    enabled = Column(Boolean, default=True)
    rate_limit_rpm = Column(Integer, default=60)
    storage_quota_mb = Column(Integer, default=0)  # 0 = unlimited
    metadata_ = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
