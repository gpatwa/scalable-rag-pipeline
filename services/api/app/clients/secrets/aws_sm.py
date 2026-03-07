# services/api/app/clients/secrets/aws_sm.py
"""
AWS Secrets Manager implementation of SecretsClient.

Uses boto3 (async wrapper via asyncio.to_thread) so it works
inside FastAPI's async lifespan without blocking the event loop.

Environment variables used:
  AWS_REGION          — AWS region (default: us-east-1)
  AWS_SM_PREFIX       — Optional prefix for secret names (e.g. "rag-platform/prod/")
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AWSSecretsManagerClient:
    """Retrieve secrets from AWS Secrets Manager."""

    def __init__(self, region: Optional[str] = None, prefix: str = ""):
        import boto3

        self._region = region or "us-east-1"
        self._prefix = prefix
        self._client = boto3.client("secretsmanager", region_name=self._region)
        logger.info(
            "AWSSecretsManagerClient initialised "
            f"(region={self._region}, prefix='{self._prefix}')"
        )

    def _full_name(self, name: str) -> str:
        return f"{self._prefix}{name}"

    async def get_secret(self, name: str) -> Optional[str]:
        """Fetch a plaintext secret from Secrets Manager."""
        try:
            resp = await asyncio.to_thread(
                self._client.get_secret_value,
                SecretId=self._full_name(name),
            )
            return resp.get("SecretString")
        except self._client.exceptions.ResourceNotFoundException:
            logger.warning(f"Secret not found: {self._full_name(name)}")
            return None
        except Exception:
            logger.exception(f"Error fetching secret: {self._full_name(name)}")
            return None

    async def get_secret_json(self, name: str) -> Optional[dict]:
        """Fetch a JSON-structured secret and parse it."""
        raw = await self.get_secret(name)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"Secret '{name}' is not valid JSON")
            return None

    async def close(self) -> None:
        """boto3 client does not require explicit cleanup."""
        pass
