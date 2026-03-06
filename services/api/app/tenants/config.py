# services/api/app/tenants/config.py
"""
Per-tenant configuration model.

Each tenant can override default LLM/model, rate limits, and storage quotas.
Unknown tenants fall back to the global defaults defined in Settings.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class TenantConfig:
    """
    Immutable configuration for a single tenant.

    Fields:
        tenant_id: Unique tenant identifier.
        llm_provider: Override LLM provider ("ray", "openai", None=global).
        llm_model: Override LLM model name (None=global).
        embed_provider: Override embedding provider (None=global).
        embed_model: Override embedding model name (None=global).
        rate_limit_rpm: Requests-per-minute limit (0=unlimited).
        storage_quota_mb: Max storage in MB (0=unlimited).
        enabled: Whether the tenant is active.
        metadata: Arbitrary key-value pairs for custom config.
    """

    tenant_id: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    embed_provider: Optional[str] = None
    embed_model: Optional[str] = None
    rate_limit_rpm: int = 60
    storage_quota_mb: int = 0  # 0 = unlimited
    enabled: bool = True
    metadata: dict = field(default_factory=dict)


# Default config for tenants that don't have explicit overrides
DEFAULT_TENANT_CONFIG = TenantConfig(
    tenant_id="default",
    rate_limit_rpm=60,
    storage_quota_mb=0,
    enabled=True,
)
