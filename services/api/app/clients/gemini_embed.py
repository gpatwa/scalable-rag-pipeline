# services/api/app/clients/gemini_embed.py
"""
Google Gemini Embedding provider (multimodal).
Uses Gemini Embedding 2 Preview for unified text + image embeddings.

Usage:
  EMBED_PROVIDER=gemini
  GOOGLE_API_KEY=...
  GEMINI_EMBED_MODEL=gemini-embedding-2-preview
  GEMINI_EMBED_DIMENSIONS=768

Note: Gemini Embedding 2 maps text, images, video, audio, and PDFs
into a unified embedding space, enabling cross-modal retrieval.
Image limit: 6 per request. Dimensions: 128-3072 (Matryoshka).
"""
import logging
from typing import Optional

import backoff
from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)


class GeminiEmbedClient:
    """Async-compatible Gemini embedding client with multimodal support."""

    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.GEMINI_EMBED_MODEL
        self.dimensions = settings.GEMINI_EMBED_DIMENSIONS
        self.client: Optional[genai.Client] = None

    async def start(self) -> None:
        """Initialize the Gemini client."""
        api_key = settings.GOOGLE_API_KEY
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY is required for Gemini embedding provider")

        self.client = genai.Client(api_key=api_key)
        logger.info(
            "Gemini Embed Client initialized (model=%s, dims=%d)",
            self.model,
            self.dimensions,
        )

    async def close(self) -> None:
        """Clean up resources."""
        self.client = None

    def _ensure_client(self):
        if not self.client:
            raise RuntimeError("Client not initialized. Call start() first.")

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        self._ensure_client()
        result = self.client.models.embed_content(
            model=self.model,
            contents=text,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=self.dimensions,
            ),
        )
        return list(result.embeddings[0].values)

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple texts in a single batch call."""
        self._ensure_client()
        result = self.client.models.embed_content(
            model=self.model,
            contents=texts,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=self.dimensions,
            ),
        )
        return [list(e.values) for e in result.embeddings]

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    async def embed_image(self, image_bytes: bytes, mime_type: str = "image/png") -> list[float]:
        """Embed a single image into the same vector space as text."""
        self._ensure_client()
        part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        result = self.client.models.embed_content(
            model=self.model,
            contents=part,
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_DOCUMENT",
                output_dimensionality=self.dimensions,
            ),
        )
        return list(result.embeddings[0].values)

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    async def embed_images(self, images: list[tuple[bytes, str]]) -> list[list[float]]:
        """
        Embed multiple images. Each item is (image_bytes, mime_type).
        Processes in batches of 6 (Gemini limit per request).
        """
        self._ensure_client()
        all_embeddings: list[list[float]] = []

        for i in range(0, len(images), 6):
            batch = images[i : i + 6]
            for image_bytes, mime_type in batch:
                part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                result = self.client.models.embed_content(
                    model=self.model,
                    contents=part,
                    config=types.EmbedContentConfig(
                        task_type="RETRIEVAL_DOCUMENT",
                        output_dimensionality=self.dimensions,
                    ),
                )
                all_embeddings.append(list(result.embeddings[0].values))

        return all_embeddings
