# services/api/app/clients/secrets/base.py
"""
SecretsClient Protocol — cloud-agnostic interface for secret retrieval.

Implementations:
  - AWS Secrets Manager  (aws_sm.py)
  - Azure Key Vault      (azure_kv.py)
  - Environment-only     (env.py) — no remote secret store, read from env

The app uses this at startup to fetch sensitive config (DB passwords,
API keys) from the cloud provider's secret store instead of baking
secrets into env vars or Helm values.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class SecretsClient(Protocol):
    """
    Minimal interface for a cloud secret store.

    Methods
    -------
    get_secret(name)
        Retrieve a secret value by name / key.
    get_secret_json(name)
        Retrieve a JSON-structured secret and return as dict.
    close()
        Release any underlying resources.
    """

    async def get_secret(self, name: str) -> Optional[str]:
        """Return the plaintext value of *name*, or None if not found."""
        ...

    async def get_secret_json(self, name: str) -> Optional[dict]:
        """Return a JSON secret parsed as a dict, or None if not found."""
        ...

    async def close(self) -> None:
        """Clean up HTTP sessions / connections."""
        ...
