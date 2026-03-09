# services/control-plane/main.py
"""
Control Plane API server.

The SaaS management layer that handles:
  - End-user authentication (JWT)
  - Tenant management (CRUD)
  - Data plane registry + health monitoring
  - Request routing + streaming proxy to data planes
  - Rate limiting
  - Usage tracking
  - Chat UI serving

This service has its own database (separate from data plane databases)
and communicates with data planes via REST + optional mTLS.
"""
import os
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response

from app.config import cp_settings
from app.db import init_engine, create_tables
from app.proxy.mtls import close_mtls_client
from app.registry.manager import health_monitor_loop
from app.routes import auth, tenants, data_planes, proxy, admin_health
from app.routes import usage

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=getattr(logging, cp_settings.LOG_LEVEL),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Control plane startup and shutdown sequence.

    Startup:
      1. Initialize control plane database
      2. Start health monitor background task
      3. Initialize JWKS fetcher (if external IdP)

    Shutdown:
      1. Cancel health monitor
      2. Close mTLS client
    """
    logger.info("Starting control plane...")

    # 1. Initialize database engine + create tables
    init_engine()
    await create_tables()
    logger.info("Control plane database initialized")

    # 2. Start background health monitor
    monitor_task = asyncio.create_task(health_monitor_loop(check_interval=60))
    logger.info("Health monitor started (check every 60s)")

    # 3. Initialize JWKS fetcher for external IdP (if configured)
    if cp_settings.AUTH_PROVIDER != "local" and cp_settings.JWT_JWKS_URL:
        logger.info(
            f"External auth provider: {cp_settings.AUTH_PROVIDER} "
            f"(JWKS: {cp_settings.JWT_JWKS_URL})"
        )
        # TODO: Initialize JWKS fetcher for RS256 validation

    logger.info("Control plane startup complete")

    yield

    # Shutdown
    logger.info("Shutting down control plane...")
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    await close_mtls_client()
    logger.info("Control plane shutdown complete")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="RAG Control Plane",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
origins = [o.strip() for o in cp_settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

# Auth routes
app.include_router(auth.router, prefix="/auth", tags=["Auth"])

# End-user proxy routes (forwarded to data planes)
app.include_router(proxy.router, prefix="/api/v1", tags=["Proxy"])

# Admin routes
app.include_router(tenants.router, prefix="/admin/tenants", tags=["Tenants"])
app.include_router(data_planes.router, prefix="/admin/data-planes", tags=["Data Planes"])
app.include_router(usage.router, prefix="/admin/usage", tags=["Usage"])

# Health + admin dashboard
app.include_router(admin_health.router, prefix="/health", tags=["Health"])

# ---------------------------------------------------------------------------
# Chat UI static files
# ---------------------------------------------------------------------------
STATIC_DIR = cp_settings.STATIC_DIR or os.path.join(
    os.path.dirname(__file__), "..", "api", "static"
)


@app.get("/", include_in_schema=False)
async def serve_ui():
    """Serve Chat UI SPA."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "RAG Control Plane API", "docs": "/docs"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
