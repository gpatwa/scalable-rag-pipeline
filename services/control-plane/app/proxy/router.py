# services/control-plane/app/proxy/router.py
"""
Tenant-to-DataPlane routing.

Resolves a tenant_id to the appropriate data plane endpoint URL.
Maintains an in-memory cache with TTL for fast lookups.
"""
import time
import logging
from typing import Optional
from dataclasses import dataclass
from sqlalchemy import select
from .. import db as db_module
from ..models.data_plane import DataPlane

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60  # Refresh cache every 60s


@dataclass
class DataPlaneInfo:
    """Resolved data plane connection info."""
    id: str
    endpoint_url: str
    api_key_hash: str
    status: str


# In-memory cache: tenant_id -> (DataPlaneInfo, timestamp)
_cache: dict[str, tuple[DataPlaneInfo, float]] = {}


async def resolve_data_plane(tenant_id: str) -> Optional[DataPlaneInfo]:
    """
    Look up the healthy data plane for a tenant.

    Uses an in-memory cache with TTL to avoid DB queries on every request.
    Returns None if no healthy data plane is found.
    """
    # Check cache
    if tenant_id in _cache:
        info, cached_at = _cache[tenant_id]
        if time.time() - cached_at < CACHE_TTL_SECONDS:
            if info.status == "healthy":
                return info
            # Cached but unhealthy — fall through to DB check

    # Query database
    async with db_module.AsyncSessionLocal() as session:
        result = await session.execute(
            select(DataPlane).where(
                DataPlane.tenant_id == tenant_id,
                DataPlane.status == "healthy",
            ).limit(1)
        )
        dp = result.scalars().first()

        if dp:
            info = DataPlaneInfo(
                id=dp.id,
                endpoint_url=dp.endpoint_url,
                api_key_hash=dp.api_key_hash,
                status=dp.status,
            )
            _cache[tenant_id] = (info, time.time())
            return info

    # No healthy data plane found
    logger.warning(f"No healthy data plane for tenant: {tenant_id}")
    return None


def invalidate_cache(tenant_id: str = None):
    """Clear the routing cache (all or for a specific tenant)."""
    if tenant_id:
        _cache.pop(tenant_id, None)
    else:
        _cache.clear()
