# services/api/app/clients/secrets/env.py
"""
Environment-only SecretsClient — no remote secret store.

Reads secrets from environment variables or the .env file.
This is the default for local development and for clusters
where secrets are injected via Kubernetes Secrets / envFrom.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class EnvSecretsClient:
    """
    Read-only 'secrets' client backed by environment variables.

    This is the zero-dependency fallback used when SECRETS_PROVIDER
    is set to "env" (the default).
    """

    def __init__(self, prefix: str = ""):
        self._prefix = prefix
        logger.info(
            f"EnvSecretsClient initialised (prefix='{prefix}'). "
            "Secrets will be read from environment variables."
        )

    def _full_name(self, name: str) -> str:
        return f"{self._prefix}{name}".upper()

    async def get_secret(self, name: str) -> Optional[str]:
        """Read a secret from the environment."""
        value = os.environ.get(self._full_name(name))
        if value is None:
            logger.debug(f"Env var not set: {self._full_name(name)}")
        return value

    async def get_secret_json(self, name: str) -> Optional[dict]:
        """Read a JSON-formatted env var."""
        raw = await self.get_secret(name)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"Env var '{self._full_name(name)}' is not valid JSON")
            return None

    async def close(self) -> None:
        """No resources to release."""
        pass
