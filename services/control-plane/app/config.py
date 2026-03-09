# services/control-plane/app/config.py
"""
Control Plane configuration.

The control plane has its own database (tenants, data plane registry, usage)
and manages authentication, routing, and administration.
"""
from pydantic_settings import BaseSettings
from typing import Optional


class ControlPlaneSettings(BaseSettings):
    """Settings for the SaaS control plane."""

    # General
    ENV: str = "prod"
    LOG_LEVEL: str = "INFO"

    # Control plane database (tenants, data planes, usage)
    DATABASE_URL: str = "sqlite+aiosqlite:///control_plane.db"

    # Redis (rate limiting + caching)
    REDIS_URL: Optional[str] = None

    # Authentication (end users)
    AUTH_PROVIDER: str = "local"  # "local" | "auth0" | "azure_ad" | "cognito"
    JWT_SECRET_KEY: str = "dev-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_JWKS_URL: Optional[str] = None
    JWT_AUDIENCE: Optional[str] = None
    JWT_ISSUER: Optional[str] = None

    # Internal authentication (data plane -> control plane)
    INTERNAL_API_KEY: str = "internal-dev-key"

    # mTLS to data planes
    DATA_PLANE_MTLS_CA_PATH: Optional[str] = None
    DATA_PLANE_MTLS_CERT_PATH: Optional[str] = None
    DATA_PLANE_MTLS_KEY_PATH: Optional[str] = None

    # Rate limiting
    RATE_LIMIT_DEFAULT_RPM: int = 60

    # CORS
    CORS_ORIGINS: str = "*"

    # Chat UI static files
    STATIC_DIR: Optional[str] = None  # Path to Chat UI SPA

    # Observability
    OTEL_EXPORTER: str = "none"
    OTEL_SERVICE_NAME: str = "rag-control-plane"
    OTEL_ENDPOINT: Optional[str] = None

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore env vars not defined as fields


cp_settings = ControlPlaneSettings()
