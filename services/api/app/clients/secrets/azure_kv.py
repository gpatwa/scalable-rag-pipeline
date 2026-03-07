# services/api/app/clients/secrets/azure_kv.py
"""
Azure Key Vault implementation of SecretsClient.

Uses the azure-identity + azure-keyvault-secrets SDK.
Authentication is via DefaultAzureCredential (supports Workload Identity,
Managed Identity, CLI, and env-var credentials).

Environment variables used:
  AZURE_KEY_VAULT_URL  — Key Vault URI (e.g. https://my-vault.vault.azure.net)
  AZURE_KV_PREFIX      — Optional prefix for secret names (default: "")

Note: Azure Key Vault secret names allow only alphanumerics and hyphens.
      Underscores in logical names are automatically converted to hyphens.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy-check for azure SDK
try:
    from azure.identity.aio import DefaultAzureCredential
    from azure.keyvault.secrets.aio import SecretClient

    _AZURE_KV_AVAILABLE = True
except ImportError:
    _AZURE_KV_AVAILABLE = False


class AzureKeyVaultClient:
    """Retrieve secrets from Azure Key Vault."""

    def __init__(self, vault_url: str, prefix: str = ""):
        if not _AZURE_KV_AVAILABLE:
            raise ImportError(
                "azure-identity and azure-keyvault-secrets are required. "
                "Install: pip install azure-identity azure-keyvault-secrets"
            )
        self._vault_url = vault_url
        self._prefix = prefix
        self._credential = DefaultAzureCredential()
        self._client = SecretClient(
            vault_url=vault_url, credential=self._credential
        )
        logger.info(
            f"AzureKeyVaultClient initialised (vault={vault_url}, prefix='{prefix}')"
        )

    @staticmethod
    def _sanitise_name(name: str) -> str:
        """Convert underscores to hyphens (Key Vault requirement)."""
        return name.replace("_", "-")

    def _full_name(self, name: str) -> str:
        return self._sanitise_name(f"{self._prefix}{name}")

    async def get_secret(self, name: str) -> Optional[str]:
        """Fetch a plaintext secret from Azure Key Vault."""
        try:
            secret = await self._client.get_secret(self._full_name(name))
            return secret.value
        except Exception as e:
            if "SecretNotFound" in str(type(e).__name__) or "not found" in str(e).lower():
                logger.warning(f"Secret not found: {self._full_name(name)}")
                return None
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
        """Close the async HTTP sessions."""
        await self._client.close()
        await self._credential.close()
