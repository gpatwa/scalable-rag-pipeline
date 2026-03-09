# services/control-plane/app/routes/data_planes.py
"""
Data plane registry routes.

Admin routes for managing data planes, plus internal routes
for data plane self-registration and heartbeat.
"""
import hashlib
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select
from ..auth.jwt import require_admin, validate_internal_key
from .. import db as db_module
from ..models.data_plane import DataPlane
from ..proxy.router import invalidate_cache

router = APIRouter()


class DataPlaneResponse(BaseModel):
    id: str
    tenant_id: str
    endpoint_url: str
    status: str
    version: str
    last_heartbeat_at: Optional[str] = None

    class Config:
        from_attributes = True


# ── Admin routes ─────────────────────────────────────────────────────────

@router.get("/")
async def list_data_planes(_admin: dict = Depends(require_admin)):
    """List all registered data planes."""
    async with db_module.AsyncSessionLocal() as session:
        result = await session.execute(select(DataPlane))
        planes = result.scalars().all()
    return [
        DataPlaneResponse(
            id=dp.id, tenant_id=dp.tenant_id, endpoint_url=dp.endpoint_url,
            status=dp.status, version=dp.version,
            last_heartbeat_at=dp.last_heartbeat_at.isoformat() if dp.last_heartbeat_at else None,
        )
        for dp in planes
    ]


@router.get("/{dp_id}", response_model=DataPlaneResponse)
async def get_data_plane(dp_id: str, _admin: dict = Depends(require_admin)):
    """Get a specific data plane."""
    async with db_module.AsyncSessionLocal() as session:
        result = await session.execute(select(DataPlane).where(DataPlane.id == dp_id))
        dp = result.scalars().first()
    if not dp:
        raise HTTPException(status_code=404, detail="Data plane not found")
    return DataPlaneResponse(
        id=dp.id, tenant_id=dp.tenant_id, endpoint_url=dp.endpoint_url,
        status=dp.status, version=dp.version,
        last_heartbeat_at=dp.last_heartbeat_at.isoformat() if dp.last_heartbeat_at else None,
    )


@router.delete("/{dp_id}")
async def decommission_data_plane(dp_id: str, _admin: dict = Depends(require_admin)):
    """Mark a data plane as decommissioned (stops routing traffic)."""
    async with db_module.AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(select(DataPlane).where(DataPlane.id == dp_id))
            dp = result.scalars().first()
            if not dp:
                raise HTTPException(status_code=404, detail="Data plane not found")
            dp.status = "decommissioned"
            invalidate_cache(dp.tenant_id)
    return {"status": "decommissioned", "data_plane_id": dp_id}


# ── Internal routes (data plane → control plane) ────────────────────────

class RegisterRequest(BaseModel):
    data_plane_id: str
    endpoint_url: str
    api_key: str
    version: str = "0.0.0"
    tenant_id: str = "default"


class HeartbeatRequest(BaseModel):
    data_plane_id: str
    status: str = "healthy"
    uptime_seconds: int = 0
    metrics: dict = {}


@router.post("/internal/register")
async def register_data_plane(
    req: RegisterRequest,
    _auth: bool = Depends(validate_internal_key),
):
    """
    Register or update a data plane instance.

    Called by the data plane on startup.
    """
    api_key_hash = hashlib.sha256(req.api_key.encode()).hexdigest()

    async with db_module.AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(DataPlane).where(DataPlane.id == req.data_plane_id)
            )
            dp = result.scalars().first()

            if dp:
                # Update existing
                if dp.status == "decommissioned":
                    return {"status": "decommissioned"}, 410
                dp.endpoint_url = req.endpoint_url
                dp.api_key_hash = api_key_hash
                dp.version = req.version
                dp.status = "healthy"
                dp.last_heartbeat_at = datetime.utcnow()
            else:
                # Create new
                dp = DataPlane(
                    id=req.data_plane_id,
                    tenant_id=req.tenant_id,
                    endpoint_url=req.endpoint_url,
                    api_key_hash=api_key_hash,
                    status="healthy",
                    version=req.version,
                    last_heartbeat_at=datetime.utcnow(),
                )
                session.add(dp)

            invalidate_cache(req.tenant_id)

    return {"status": "registered", "heartbeat_interval": 30}


@router.post("/internal/heartbeat")
async def heartbeat(
    req: HeartbeatRequest,
    _auth: bool = Depends(validate_internal_key),
):
    """
    Receive heartbeat from a data plane.

    Updates last_heartbeat_at and status.
    """
    async with db_module.AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(DataPlane).where(DataPlane.id == req.data_plane_id)
            )
            dp = result.scalars().first()

            if not dp:
                raise HTTPException(status_code=404, detail="Data plane not registered")

            if dp.status == "decommissioned":
                raise HTTPException(status_code=410, detail="Data plane decommissioned")

            dp.status = req.status
            dp.last_heartbeat_at = datetime.utcnow()

    return {"status": "ok"}
