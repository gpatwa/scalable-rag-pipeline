# services/control-plane/app/registry/manager.py
"""
Data plane health monitor.

Background task that periodically checks the data_plane_registry table
and marks data planes as unhealthy if their heartbeat is stale.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select
from .. import db as db_module
from ..models.data_plane import DataPlane
from ..proxy.router import invalidate_cache

logger = logging.getLogger(__name__)

# Consider a data plane unhealthy if no heartbeat in 3x the interval
STALE_MULTIPLIER = 3
DEFAULT_HEARTBEAT_INTERVAL = 30  # seconds


async def health_monitor_loop(check_interval: int = 60):
    """
    Background task: periodically check data plane health.

    Marks data planes as "unhealthy" if their last heartbeat is older
    than 3x the expected heartbeat interval.
    """
    stale_threshold = timedelta(seconds=DEFAULT_HEARTBEAT_INTERVAL * STALE_MULTIPLIER)

    while True:
        await asyncio.sleep(check_interval)

        try:
            async with db_module.AsyncSessionLocal() as session:
                async with session.begin():
                    result = await session.execute(
                        select(DataPlane).where(
                            DataPlane.status.in_(["healthy", "provisioning"])
                        )
                    )
                    data_planes = result.scalars().all()

                    now = datetime.utcnow()
                    for dp in data_planes:
                        if dp.last_heartbeat_at and (now - dp.last_heartbeat_at) > stale_threshold:
                            logger.warning(
                                f"Data plane {dp.id} stale "
                                f"(last heartbeat: {dp.last_heartbeat_at})"
                            )
                            dp.status = "unhealthy"
                            invalidate_cache(dp.tenant_id)

        except Exception as e:
            logger.error(f"Health monitor error: {e}")
