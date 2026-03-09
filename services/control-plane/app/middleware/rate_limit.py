# services/control-plane/app/middleware/rate_limit.py
"""
Per-tenant rate limiting middleware.

Enforces requests-per-minute limits based on each tenant's `rate_limit_rpm`
setting from the database. Uses an in-memory sliding window counter
(production deployments should use Redis for distributed rate limiting).
"""
import time
import logging
from collections import defaultdict
from typing import Optional
from fastapi import Request, HTTPException
from sqlalchemy import select
from .. import db as db_module
from ..models.tenant import Tenant
from ..config import cp_settings

logger = logging.getLogger(__name__)

# In-memory rate tracking: tenant_id -> list of request timestamps
_request_log: dict[str, list[float]] = defaultdict(list)

# Cache tenant rate limits: tenant_id -> (rate_limit_rpm, cached_at)
_limit_cache: dict[str, tuple[int, float]] = {}
_LIMIT_CACHE_TTL = 120  # seconds


async def _get_tenant_rate_limit(tenant_id: str) -> int:
    """
    Get the rate limit for a tenant (with caching).

    Returns the tenant's rate_limit_rpm, or the system default if not found.
    """
    now = time.time()

    # Check cache
    if tenant_id in _limit_cache:
        limit, cached_at = _limit_cache[tenant_id]
        if now - cached_at < _LIMIT_CACHE_TTL:
            return limit

    # Query database
    try:
        async with db_module.AsyncSessionLocal() as session:
            result = await session.execute(
                select(Tenant.rate_limit_rpm).where(
                    Tenant.id == tenant_id,
                    Tenant.enabled == True,  # noqa: E712
                )
            )
            row = result.first()
            if row:
                limit = row[0]
                _limit_cache[tenant_id] = (limit, now)
                return limit
    except Exception as e:
        logger.warning(f"Rate limit lookup failed for {tenant_id}: {e}")

    # Fallback to default
    return cp_settings.RATE_LIMIT_DEFAULT_RPM


async def check_rate_limit(tenant_id: str) -> None:
    """
    Check if a tenant has exceeded their rate limit.

    Uses a sliding window of 60 seconds.
    Raises HTTPException(429) if the limit is exceeded.
    """
    limit_rpm = await _get_tenant_rate_limit(tenant_id)

    if limit_rpm <= 0:
        # 0 = unlimited
        return

    now = time.time()
    window_start = now - 60.0

    # Clean old entries and count recent requests
    log = _request_log[tenant_id]
    _request_log[tenant_id] = [ts for ts in log if ts > window_start]
    current_count = len(_request_log[tenant_id])

    if current_count >= limit_rpm:
        logger.warning(
            f"Rate limit exceeded for tenant {tenant_id}: "
            f"{current_count}/{limit_rpm} RPM"
        )
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limit_exceeded",
                "tenant_id": tenant_id,
                "limit_rpm": limit_rpm,
                "current_rpm": current_count,
                "retry_after_seconds": 60,
            },
        )

    # Record this request
    _request_log[tenant_id].append(now)


def reset_rate_limits(tenant_id: Optional[str] = None) -> None:
    """Clear rate limit tracking (for testing or admin reset)."""
    if tenant_id:
        _request_log.pop(tenant_id, None)
        _limit_cache.pop(tenant_id, None)
    else:
        _request_log.clear()
        _limit_cache.clear()
