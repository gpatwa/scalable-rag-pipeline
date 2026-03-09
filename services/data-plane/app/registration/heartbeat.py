# services/data-plane/app/registration/heartbeat.py
"""
Data plane registration and heartbeat with the control plane.

On startup:
  1. POST to {CONTROL_PLANE_URL}/internal/data-planes/register
  2. Start a periodic heartbeat loop

The heartbeat keeps the control plane informed of data plane health.
If heartbeats stop, the control plane marks the data plane as unhealthy
and stops routing traffic to it.
"""
import asyncio
import time
import logging
import httpx

logger = logging.getLogger(__name__)

_start_time = time.time()


async def registration_loop(
    control_plane_url: str,
    data_plane_id: str,
    data_plane_endpoint: str,
    api_key: str,
    internal_api_key: str,
    version: str,
    heartbeat_interval: int = 30,
    tenant_id: str = "default",
):
    """
    Background task: register with the control plane and send periodic heartbeats.

    Args:
        control_plane_url: Base URL of the control plane (e.g., https://control.example.com)
        data_plane_id: Unique ID for this data plane instance
        data_plane_endpoint: This data plane's reachable endpoint URL
        api_key: API key for this data plane (control plane uses this to authenticate)
        internal_api_key: Shared secret for internal control plane routes
        version: Application version
        heartbeat_interval: Seconds between heartbeats
        tenant_id: Customer/tenant this data plane serves
    """
    if not control_plane_url:
        logger.info("CONTROL_PLANE_URL not set — skipping registration (standalone mode)")
        return

    headers = {"X-Internal-Key": internal_api_key, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Step 1: Register with control plane
        registered = False
        for attempt in range(5):
            try:
                resp = await client.post(
                    f"{control_plane_url}/internal/data-planes/register",
                    json={
                        "data_plane_id": data_plane_id,
                        "endpoint_url": data_plane_endpoint,
                        "api_key": api_key,
                        "version": version,
                        "tenant_id": tenant_id,
                    },
                    headers=headers,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    heartbeat_interval = result.get("heartbeat_interval", heartbeat_interval)
                    logger.info(
                        f"Registered with control plane: {data_plane_id} "
                        f"(heartbeat every {heartbeat_interval}s)"
                    )
                    registered = True
                    break
                elif resp.status_code == 410:
                    logger.warning("Data plane decommissioned by control plane — shutting down")
                    return
                else:
                    logger.warning(f"Registration attempt {attempt+1} failed: {resp.status_code}")
            except Exception as e:
                logger.warning(f"Registration attempt {attempt+1} error: {e}")

            await asyncio.sleep(min(5 * (attempt + 1), 30))

        if not registered:
            logger.error("Failed to register with control plane after 5 attempts")
            # Continue running — the data plane can still serve requests directly
            return

        # Step 2: Periodic heartbeat
        while True:
            await asyncio.sleep(heartbeat_interval)
            try:
                resp = await client.post(
                    f"{control_plane_url}/internal/data-planes/heartbeat",
                    json={
                        "data_plane_id": data_plane_id,
                        "status": "healthy",
                        "uptime_seconds": int(time.time() - _start_time),
                        "metrics": {},
                    },
                    headers=headers,
                )
                if resp.status_code == 410:
                    logger.warning("Data plane decommissioned — stopping heartbeat")
                    return
                elif resp.status_code != 200:
                    logger.warning(f"Heartbeat response: {resp.status_code}")
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
