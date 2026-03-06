# services/api/app/routes/health.py
from fastapi import APIRouter, Response, status
from app.cache.redis import redis_client

router = APIRouter()

# Late-initialised — set by main.py lifespan
_graphdb_client = None
_vectordb_client = None


def set_clients(vectordb, graphdb):
    """Called once during app startup to inject abstracted clients."""
    global _graphdb_client, _vectordb_client
    _graphdb_client = graphdb
    _vectordb_client = vectordb


@router.get("/liveness")
async def liveness():
    """
    K8s Liveness Probe.
    Returns 200 if the server process is running.
    """
    return {"status": "ok"}


@router.get("/readiness")
async def readiness(response: Response):
    """
    K8s Readiness Probe.
    Checks connections to critical dependencies (Redis, VectorDB, GraphDB).
    If this fails, K8s stops sending traffic to this pod.
    """
    status_report = {"redis": "down", "vectordb": "down", "graphdb": "down"}
    is_healthy = True

    # 1. Check Redis
    try:
        r = redis_client.get_client()
        if await r.ping():
            status_report["redis"] = "up"
    except Exception:
        is_healthy = False

    # 2. Check VectorDB (connectivity)
    try:
        if _vectordb_client and _vectordb_client.client:
            status_report["vectordb"] = "up"
        else:
            is_healthy = False
    except Exception:
        is_healthy = False

    # 3. Check GraphDB (connectivity)
    try:
        if _graphdb_client and hasattr(_graphdb_client, "is_connected"):
            if _graphdb_client.is_connected:
                status_report["graphdb"] = "up"
            else:
                is_healthy = False
        elif _graphdb_client:
            # NullGraphClient is always "up"
            status_report["graphdb"] = "up"
        else:
            is_healthy = False
    except Exception:
        is_healthy = False

    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return status_report
