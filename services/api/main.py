# services/api/main.py
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from app.clients.ray_llm import llm_client
from app.clients.ray_embed import embed_client
from app.clients.vectordb.factory import create_vectordb_client
from app.clients.graphdb.factory import create_graphdb_client
from app.clients.secrets.factory import create_secrets_client
from app.cache.redis import redis_client
from app.cache.semantic import set_vectordb_client as set_semantic_vectordb
from app.agents.nodes.retriever import set_clients as set_retriever_clients
from app.routes import chat, upload, health, auth
from app.routes.health import set_clients as set_health_clients
from app.config import settings

logger = logging.getLogger(__name__)

# Create VectorDB, GraphDB, and Secrets clients via provider factories
vectordb_client = create_vectordb_client(settings.VECTORDB_PROVIDER)
graphdb_client = create_graphdb_client(settings.GRAPHDB_PROVIDER)
secrets_client = create_secrets_client(
    settings.SECRETS_PROVIDER,
    region=settings.AWS_REGION,
    prefix=settings.SECRETS_PREFIX,
    vault_url=settings.AZURE_KEY_VAULT_URL,
)


async def _inject_secrets_from_vault():
    """
    Fetch sensitive values from Key Vault / Secrets Manager and inject
    them into settings *before* any database client is initialised.

    This runs only when SECRETS_PROVIDER is not "env".  When using the
    "env" provider, secrets are already present as environment variables
    (injected via K8s Secret or .env file).
    """
    if settings.SECRETS_PROVIDER == "env":
        logger.info("Secrets provider: env — secrets loaded from environment")
        return

    logger.info(f"Secrets provider: {settings.SECRETS_PROVIDER} — fetching from vault")

    # Map of setting attribute -> vault secret name
    secret_map = {
        "DB_PASSWORD":    "db-password",
        "JWT_SECRET_KEY": "jwt-secret-key",
        "NEO4J_PASSWORD": "neo4j-password",
        "REDIS_PASSWORD": "redis-primary-key",
        "OPENAI_API_KEY": "openai-api-key",
    }

    for attr, vault_key in secret_map.items():
        current = getattr(settings, attr, None)
        if current:
            # Already set via env var — don't overwrite
            continue
        value = await secrets_client.get_secret(vault_key)
        if value:
            # Inject into the settings singleton (bypass frozen validation)
            object.__setattr__(settings, attr, value)
            logger.info(f"  Injected {attr} from vault")
        else:
            logger.warning(f"  Secret '{vault_key}' not found in vault for {attr}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Centralized Resource Management.

    Order of operations:
      1. Fetch secrets from Key Vault (if configured)
      2. Initialise database engine (using injected secrets)
      3. Connect all clients
      4. Wire up route dependencies
    """
    # 1. Inject secrets from vault BEFORE initialising DB connections
    await _inject_secrets_from_vault()

    # 2. Initialise Postgres engine (now that DB_PASSWORD is available)
    from app.memory.postgres import init_engine
    init_engine()
    logger.info("Database engine initialised")

    # 3. Connect core clients
    await redis_client.connect()
    try:
        await llm_client.start()
    except Exception as e:
        logger.warning(f"LLM client init skipped: {e}")
    try:
        await embed_client.start()
    except Exception as e:
        logger.warning(f"Embed client init skipped: {e}")

    # Abstracted DB clients (VectorDB + GraphDB)
    await vectordb_client.connect()
    await graphdb_client.connect()

    # 4. Inject abstracted clients into modules that need them
    set_retriever_clients(vectordb_client, graphdb_client)
    set_semantic_vectordb(vectordb_client)
    set_health_clients(vectordb_client, graphdb_client)

    # Load per-tenant configurations
    from app.tenants.registry import tenant_registry
    await tenant_registry.load(source=settings.TENANT_CONFIG_SOURCE)

    # Initialize JWKS fetcher for external IdP (Auth0, Azure AD, Cognito)
    if settings.AUTH_PROVIDER != "local" and settings.JWT_JWKS_URL:
        from app.auth.jwks import init_jwks_fetcher
        await init_jwks_fetcher(settings.JWT_JWKS_URL)
        logger.info(f"JWKS fetcher initialised for {settings.AUTH_PROVIDER}")

    # Wire up OpenTelemetry observability (tracing + auto-instrumentation)
    try:
        from app.observability import setup_observability
        setup_observability(app)
        logger.info("Observability instrumented")
    except Exception as e:
        logger.warning(f"Observability setup skipped (optional deps missing): {e}")

    yield

    # Shutdown
    logger.info("Closing clients...")
    await secrets_client.close()
    await vectordb_client.close()
    await graphdb_client.close()
    await redis_client.close()
    await llm_client.close()
    await embed_client.close()

# FastAPI Application
app = FastAPI(title="Enterprise RAG Platform", version="1.0.0", lifespan=lifespan)

# CORS Middleware — configurable via CORS_ORIGINS env var
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routes
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(upload.router, prefix="/api/v1/upload", tags=["Upload"])
app.include_router(health.router, prefix="/health", tags=["Health"])

# Serve Chat UI at root "/"
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

@app.get("/", include_in_schema=False)
async def serve_ui():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

if __name__ == "__main__":
    import uvicorn
    # In production, this is run via Gunicorn/Uvicorn in Docker
    uvicorn.run(app, host="0.0.0.0", port=8000)
