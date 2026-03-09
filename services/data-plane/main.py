# services/data-plane/main.py
"""
Data Plane API server.

A slimmed-down version of the monolith API that handles only query processing.
Shares code from services/api/app/ for the agent pipeline, clients, cache,
and memory modules.

Key differences from monolith:
  - No multi-tenant resolution (SINGLE_TENANT_MODE=True)
  - Auth via API key from control plane (not JWT)
  - Heartbeat registration with control plane
  - No Chat UI serving (control plane serves the UI)
  - No /auth/token endpoint
"""
import os
import sys
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Path setup: import shared code from services/api/app/
# ---------------------------------------------------------------------------
_base_dir = os.path.dirname(os.path.abspath(__file__))
_api_dir = os.path.join(_base_dir, "..", "api")
sys.path.insert(0, _api_dir)

# Also make data-plane's own app importable as dp_app
sys.path.insert(0, _base_dir)
import services  # noqa: prevent namespace collision
sys.modules.setdefault("dp_app", __import__("app", fromlist=["app"]))
# Re-alias so dp_app.auth.control_plane_auth works
dp_app_path = os.path.join(_base_dir, "app")
if dp_app_path not in sys.path:
    sys.path.insert(0, _base_dir)

# Now we can import from the shared api/app/ and our local dp_app/
from app.config import settings  # noqa: E402

# Force single-tenant mode for data plane
object.__setattr__(settings, "DEPLOYMENT_MODE", "data_plane")
object.__setattr__(settings, "SINGLE_TENANT_MODE", True)

from app.clients.factory import create_llm_client, create_embed_client  # noqa: E402
from app.clients.vectordb.factory import create_vectordb_client  # noqa: E402
from app.clients.graphdb.factory import create_graphdb_client  # noqa: E402
from app.clients.storage.factory import create_storage_client  # noqa: E402
from app.clients.secrets.factory import create_secrets_client  # noqa: E402
from app.clients.reranker.factory import create_reranker_client  # noqa: E402
from app.clients.ray_llm import llm_client  # noqa: E402
from app.clients.ray_embed import embed_client  # noqa: E402
from app.cache.redis import redis_client  # noqa: E402
from app.memory.postgres import init_engine  # noqa: E402
from app.agents.nodes.retriever import set_clients as set_retriever_clients  # noqa: E402
from app.cache.semantic import set_vectordb_client as set_semantic_vectordb  # noqa: E402

# Data plane specific
from dp_app.config import dp_settings  # noqa: E402
from dp_app.auth.control_plane_auth import set_api_key  # noqa: E402
from dp_app.routes import chat, upload, health  # noqa: E402
from dp_app.routes.upload import set_storage_client as set_upload_storage  # noqa: E402
from dp_app.routes.health import set_health_clients, set_health_metadata  # noqa: E402
from dp_app.registration.heartbeat import registration_loop  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client singletons (created from settings via factory pattern)
# ---------------------------------------------------------------------------
secrets_client = create_secrets_client(settings.SECRETS_PROVIDER)
vectordb_client = create_vectordb_client(settings.VECTORDB_PROVIDER)
graphdb_client = create_graphdb_client(settings.GRAPHDB_PROVIDER)
storage_client = create_storage_client(settings.STORAGE_PROVIDER)
reranker_client = create_reranker_client(
    settings.RERANKER_PROVIDER,
    score_threshold=settings.RERANKER_SCORE_THRESHOLD,
)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Data plane startup and shutdown sequence."""
    logger.info(f"Starting data plane: {dp_settings.DATA_PLANE_ID}")

    # 1. Inject secrets from vault (if configured)
    if settings.SECRETS_PROVIDER != "env":
        await _inject_secrets_from_vault()

    # 2. Initialize database engine
    init_engine()

    # 3. Connect all clients
    await redis_client.connect()
    await llm_client.start()
    await embed_client.start()
    await vectordb_client.connect()
    await graphdb_client.connect()
    await reranker_client.start()

    # 4. Wire up client references
    set_retriever_clients(vectordb_client, graphdb_client, reranker_client)
    set_semantic_vectordb(vectordb_client)
    set_health_clients(vectordb_client, graphdb_client)
    set_health_metadata(dp_settings.DATA_PLANE_ID, dp_settings.APP_VERSION)
    set_upload_storage(storage_client)
    set_api_key(dp_settings.DATA_PLANE_API_KEY)

    # 5. Start heartbeat registration (background task)
    heartbeat_task = asyncio.create_task(
        registration_loop(
            control_plane_url=dp_settings.CONTROL_PLANE_URL,
            data_plane_id=dp_settings.DATA_PLANE_ID,
            data_plane_endpoint=f"http://localhost:8080",  # TODO: configurable
            api_key=dp_settings.DATA_PLANE_API_KEY,
            internal_api_key=dp_settings.INTERNAL_API_KEY,
            version=dp_settings.APP_VERSION,
            heartbeat_interval=dp_settings.HEARTBEAT_INTERVAL_SECONDS,
        )
    )

    logger.info("Data plane startup complete")

    yield

    # Shutdown
    heartbeat_task.cancel()
    await secrets_client.close()
    await vectordb_client.close()
    await graphdb_client.close()
    await reranker_client.close()
    await redis_client.close()
    await llm_client.close()
    await embed_client.close()
    logger.info("Data plane shutdown complete")


async def _inject_secrets_from_vault():
    """Fetch secrets from vault and inject into settings."""
    secret_map = {
        "db-password": "DB_PASSWORD",
        "jwt-secret-key": "JWT_SECRET_KEY",
        "neo4j-password": "NEO4J_PASSWORD",
        "redis-primary-key": "REDIS_PASSWORD",
        "openai-api-key": "OPENAI_API_KEY",
    }
    for secret_name, attr in secret_map.items():
        value = await secrets_client.get_secret(secret_name)
        if value:
            object.__setattr__(settings, attr, value)
            logger.info(f"Injected secret: {attr}")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="RAG Data Plane",
    version=dp_settings.APP_VERSION,
    lifespan=lifespan,
)

# Routes — query processing only (no auth, no admin, no UI)
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(upload.router, prefix="/api/v1/upload", tags=["Upload"])
app.include_router(health.router, prefix="/health", tags=["Health"])
