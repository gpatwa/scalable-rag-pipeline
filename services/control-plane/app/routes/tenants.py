# services/control-plane/app/routes/tenants.py
"""
Tenant management CRUD routes.

Admin-only endpoints for managing customer organizations.
"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select
from ..auth.jwt import require_admin
from .. import db as db_module
from ..models.tenant import Tenant

router = APIRouter()


class TenantCreate(BaseModel):
    name: str
    plan: str = "free"
    rate_limit_rpm: int = 60
    storage_quota_mb: int = 0
    metadata_: dict = {}


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    plan: Optional[str] = None
    enabled: Optional[bool] = None
    rate_limit_rpm: Optional[int] = None
    storage_quota_mb: Optional[int] = None
    metadata_: Optional[dict] = None


class TenantResponse(BaseModel):
    id: str
    name: str
    plan: str
    enabled: bool
    rate_limit_rpm: int
    storage_quota_mb: int

    class Config:
        from_attributes = True


@router.post("/", response_model=TenantResponse)
async def create_tenant(
    req: TenantCreate,
    _admin: dict = Depends(require_admin),
):
    """Create a new tenant."""
    tenant_id = str(uuid.uuid4())[:8]
    tenant = Tenant(
        id=tenant_id,
        name=req.name,
        plan=req.plan,
        rate_limit_rpm=req.rate_limit_rpm,
        storage_quota_mb=req.storage_quota_mb,
        metadata_=req.metadata_,
    )
    async with db_module.AsyncSessionLocal() as session:
        async with session.begin():
            session.add(tenant)
    return TenantResponse(
        id=tenant_id,
        name=req.name,
        plan=req.plan,
        enabled=True,
        rate_limit_rpm=req.rate_limit_rpm,
        storage_quota_mb=req.storage_quota_mb,
    )


@router.get("/")
async def list_tenants(_admin: dict = Depends(require_admin)):
    """List all tenants."""
    async with db_module.AsyncSessionLocal() as session:
        result = await session.execute(select(Tenant).order_by(Tenant.created_at.desc()))
        tenants = result.scalars().all()
    return [
        TenantResponse(
            id=t.id, name=t.name, plan=t.plan, enabled=t.enabled,
            rate_limit_rpm=t.rate_limit_rpm, storage_quota_mb=t.storage_quota_mb,
        )
        for t in tenants
    ]


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: str, _admin: dict = Depends(require_admin)):
    """Get a specific tenant."""
    async with db_module.AsyncSessionLocal() as session:
        result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantResponse(
        id=tenant.id, name=tenant.name, plan=tenant.plan, enabled=tenant.enabled,
        rate_limit_rpm=tenant.rate_limit_rpm, storage_quota_mb=tenant.storage_quota_mb,
    )


@router.patch("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    req: TenantUpdate,
    _admin: dict = Depends(require_admin),
):
    """Update a tenant."""
    async with db_module.AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
            tenant = result.scalars().first()
            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")
            for field, value in req.model_dump(exclude_none=True).items():
                setattr(tenant, field, value)
    return TenantResponse(
        id=tenant.id, name=tenant.name, plan=tenant.plan, enabled=tenant.enabled,
        rate_limit_rpm=tenant.rate_limit_rpm, storage_quota_mb=tenant.storage_quota_mb,
    )


@router.delete("/{tenant_id}")
async def disable_tenant(tenant_id: str, _admin: dict = Depends(require_admin)):
    """Soft-disable a tenant (does not delete data)."""
    async with db_module.AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
            tenant = result.scalars().first()
            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")
            tenant.enabled = False
    return {"status": "disabled", "tenant_id": tenant_id}
