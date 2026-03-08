# services/api/app/clients/ray_embed.py
import httpx
import logging
import backoff
from typing import Optional
from app.config import settings

logger = logging.getLogger(__name__)

class RayEmbedClient:
    """
    Client for the Embedding Service.
    Supports both Ray Serve (prod) and Ollama (local dev) APIs.
    Ollama endpoint: POST /api/embeddings {"model": "...", "prompt": "..."}
    """
    def __init__(self):
        self.endpoint = settings.RAY_EMBED_ENDPOINT
        self.model = settings.EMBED_MODEL
        self.client: Optional[httpx.AsyncClient] = None

    async def start(self):
        """Called during App Startup — initializes the connection pool."""
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
        self.client = httpx.AsyncClient(timeout=60.0, limits=limits)
        logger.info("Embed Client initialized.")

    async def close(self):
        """Called during App Shutdown."""
        if self.client:
            await self.client.aclose()

    @backoff.on_exception(backoff.expo, httpx.HTTPError, max_tries=3)
    async def embed_query(self, text: str) -> list[float]:
        if not self.client:
            raise RuntimeError("Client not initialized. Call start() first.")
        response = await self.client.post(
            self.endpoint,
            json={"model": self.model, "prompt": text}
        )
        response.raise_for_status()
        return response.json()["embedding"]

    @backoff.on_exception(backoff.expo, httpx.HTTPError, max_tries=3)
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts (sequentially for Ollama, batched for Ray)."""
        if not self.client:
            raise RuntimeError("Client not initialized. Call start() first.")
        embeddings = []
        for text in texts:
            response = await self.client.post(
                self.endpoint,
                json={"model": self.model, "prompt": text}
            )
            response.raise_for_status()
            embeddings.append(response.json()["embedding"])
        return embeddings

# Global Instance — created via factory based on EMBED_PROVIDER env var.
# Consumers import `embed_client` from this module; the factory decides
# whether it's a RayEmbedClient, OpenAIEmbedClient, etc.
from app.clients.factory import create_embed_client as _create_embed
embed_client = _create_embed(settings.EMBED_PROVIDER)
