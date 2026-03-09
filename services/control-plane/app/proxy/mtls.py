# services/control-plane/app/proxy/mtls.py
"""
mTLS client for secure communication with data planes.

Creates an httpx.AsyncClient configured with:
  - Client certificate + key (control plane identity)
  - CA certificate (to verify data plane server cert)
"""
import ssl
import httpx
import logging
from typing import Optional
from ..config import cp_settings

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None


def create_mtls_client() -> httpx.AsyncClient:
    """
    Create an httpx.AsyncClient with mTLS configuration.

    If mTLS paths are not configured, creates a standard HTTPS client.
    """
    global _client

    if _client:
        return _client

    if (
        cp_settings.DATA_PLANE_MTLS_CERT_PATH
        and cp_settings.DATA_PLANE_MTLS_KEY_PATH
    ):
        # Full mTLS
        logger.info("Creating mTLS client for data plane communication")
        _client = httpx.AsyncClient(
            cert=(
                cp_settings.DATA_PLANE_MTLS_CERT_PATH,
                cp_settings.DATA_PLANE_MTLS_KEY_PATH,
            ),
            verify=cp_settings.DATA_PLANE_MTLS_CA_PATH or True,
            timeout=httpx.Timeout(
                connect=5.0,
                read=300.0,  # Long timeout for streaming responses
                write=5.0,
                pool=5.0,
            ),
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=50,
            ),
        )
    else:
        # No mTLS — plain HTTPS (or HTTP for dev)
        logger.info("Creating standard HTTP client for data plane communication (no mTLS)")
        _client = httpx.AsyncClient(
            verify=False,  # Dev mode — disable SSL verification
            timeout=httpx.Timeout(
                connect=5.0,
                read=300.0,
                write=5.0,
                pool=5.0,
            ),
            limits=httpx.Limits(
                max_keepalive_connections=20,
                max_connections=50,
            ),
        )

    return _client


async def close_mtls_client():
    """Close the mTLS client."""
    global _client
    if _client:
        await _client.aclose()
        _client = None
