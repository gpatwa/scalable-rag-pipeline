# services/data-plane/app/config.py
"""
Data Plane configuration.

Extends the shared Settings with data-plane-specific fields
for control plane registration and heartbeat.
"""
from pydantic_settings import BaseSettings
from typing import Optional


class DataPlaneSettings(BaseSettings):
    """Settings specific to the data plane deployment."""

    # Identity
    DATA_PLANE_ID: str = "dp-default"
    DATA_PLANE_API_KEY: str = ""  # API key used by control plane to authenticate

    # Control plane registration
    CONTROL_PLANE_URL: Optional[str] = None  # e.g., https://control.example.com
    HEARTBEAT_INTERVAL_SECONDS: int = 30
    INTERNAL_API_KEY: str = ""  # Shared secret for /internal/ routes on control plane

    # Version info (set at build time)
    APP_VERSION: str = "0.1.0"

    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore env vars not defined as fields


dp_settings = DataPlaneSettings()
