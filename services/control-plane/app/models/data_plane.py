# services/control-plane/app/models/data_plane.py
"""
Data Plane registry model.

Tracks all registered data plane instances, their health status,
and maps them to tenants for request routing.
"""
from sqlalchemy import Column, String, Integer, DateTime
from datetime import datetime
from ..db import Base


class DataPlane(Base):
    """A registered data plane instance."""
    __tablename__ = "data_plane_registry"

    id = Column(String(255), primary_key=True)  # DATA_PLANE_ID
    tenant_id = Column(String(255), nullable=False, index=True)  # Logical FK to tenants
    endpoint_url = Column(String(1024), nullable=False)
    api_key_hash = Column(String(255), nullable=False)  # Hashed API key
    status = Column(
        String(50), default="provisioning"
    )  # provisioning | healthy | unhealthy | decommissioned
    version = Column(String(50), default="0.0.0")
    last_heartbeat_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
