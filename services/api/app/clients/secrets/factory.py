# services/api/app/clients/secrets/factory.py
"""
Factory for creating a SecretsClient based on SECRETS_PROVIDER setting.

Supported providers:
  "env"        — Environment variables (default, zero dependencies)
  "aws_sm"     — AWS Secrets Manager (requires boto3)
  "azure_kv"   — Azure Key Vault (requires azure-identity, azure-keyvault-secrets)
"""
from __future__ import annotations

import logging

from app.clients.secrets.base import SecretsClient

logger = logging.getLogger(__name__)


def create_secrets_client(provider: str, **kwargs) -> SecretsClient:
    """
    Instantiate a SecretsClient for the given provider.

    Keyword arguments are forwarded to the provider constructor:
      - env:      prefix (str)
      - aws_sm:   region (str), prefix (str)
      - azure_kv: vault_url (str), prefix (str)
    """
    provider = provider.lower().strip()

    if provider == "env":
        from app.clients.secrets.env import EnvSecretsClient

        return EnvSecretsClient(prefix=kwargs.get("prefix", ""))

    elif provider == "aws_sm":
        from app.clients.secrets.aws_sm import AWSSecretsManagerClient

        return AWSSecretsManagerClient(
            region=kwargs.get("region"),
            prefix=kwargs.get("prefix", ""),
        )

    elif provider == "azure_kv":
        from app.clients.secrets.azure_kv import AzureKeyVaultClient

        vault_url = kwargs.get("vault_url")
        if not vault_url:
            raise ValueError(
                "AZURE_KEY_VAULT_URL is required when SECRETS_PROVIDER='azure_kv'"
            )
        return AzureKeyVaultClient(
            vault_url=vault_url,
            prefix=kwargs.get("prefix", ""),
        )

    else:
        raise ValueError(
            f"Unknown SECRETS_PROVIDER: '{provider}'. "
            f"Supported: 'env', 'aws_sm', 'azure_kv'"
        )
