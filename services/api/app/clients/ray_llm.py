# services/api/app/clients/ray_llm.py
import httpx
import logging
import backoff
from typing import List, Dict, Optional
from app.config import settings

logger = logging.getLogger(__name__)

class RayLLMClient:
    """
    Async Client with proper Connection Pooling.
    """
    def __init__(self):
        self.endpoint = settings.RAY_LLM_ENDPOINT 
        # Client is initialized in startup_event
        self.client: Optional[httpx.AsyncClient] = None

    async def start(self):
        """Called during App Startup"""
        # Limits: prevent opening too many connections to Ray
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
        self.client = httpx.AsyncClient(
            timeout=120.0, 
            limits=limits
        )
        logger.info("Ray LLM Client initialized.")

    async def close(self):
        """Called during App Shutdown"""
        if self.client:
            await self.client.aclose()

    @backoff.on_exception(backoff.expo, httpx.HTTPError, max_tries=3)
    async def chat_completion(self, messages: List[Dict], temperature: float = 0.7, json_mode: bool = False) -> str:
        if not self.client:
            raise RuntimeError("Client not initialized. Call start() first.")

        payload = {
            "model": settings.LLM_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1024,
            "stream": False
        }
        
        response = await self.client.post(self.endpoint, json=payload)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

# Global Instance — created via factory based on LLM_PROVIDER env var.
# Consumers import `llm_client` from this module; the factory decides
# whether it's a RayLLMClient, OpenAILLMClient, etc.
from app.clients.factory import create_llm_client as _create_llm
llm_client = _create_llm(settings.LLM_PROVIDER)