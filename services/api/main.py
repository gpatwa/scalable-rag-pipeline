# services/api/main.py
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from services.api.app.clients.neo4j import neo4j_client
from services.api.app.clients.ray_llm import llm_client
from services.api.app.clients.ray_embed import embed_client
from services.api.app.cache.redis import redis_client
from services.api.app.routes import chat, upload, health, auth
from services.api.app.config import settings

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Centralized Resource Management.
    Initialize all connection pools here.
    """
    # 1. Startup
    logger.info("Initializing clients...")
    neo4j_client.connect()
    await redis_client.connect()
    await llm_client.start()
    await embed_client.start()

    # Wire up OpenTelemetry observability (tracing + auto-instrumentation)
    try:
        from services.api.app.observability import setup_observability
        setup_observability(app)
        logger.info("Observability instrumented")
    except Exception as e:
        logger.warning(f"Observability setup skipped (optional deps missing): {e}")

    yield

    # 2. Shutdown
    logger.info("Closing clients...")
    await neo4j_client.close()
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
