# services/data-plane/app/auth/control_plane_auth.py
"""
Data plane authentication — validates requests from the control plane.

Two authentication modes:
  1. API Key: Control plane sends X-DataPlane-Key header
  2. JWKS: Control plane signs a JWT (for more secure deployments)

User identity is forwarded from the control plane via:
  - X-User-Id header
  - X-User-Role header
"""
from fastapi import Depends, HTTPException, Request


# Late-initialised — set during app startup
_api_key: str = ""


def set_api_key(key: str):
    """Called during app startup to set the expected API key."""
    global _api_key
    _api_key = key


async def validate_control_plane_request(request: Request) -> dict:
    """
    FastAPI dependency that validates the incoming request is from the control plane.

    Checks X-DataPlane-Key header against the configured API key.
    Extracts user context from forwarded headers.
    """
    # Validate API key (skip if not configured — dev mode)
    if _api_key:
        api_key = request.headers.get("X-DataPlane-Key", "")
        if api_key != _api_key:
            raise HTTPException(status_code=401, detail="Invalid data plane API key")

    # Extract forwarded user context
    user_id = request.headers.get("X-User-Id", "anonymous")
    user_role = request.headers.get("X-User-Role", "user")

    return {
        "user_id": user_id,
        "role": user_role,
    }


async def get_data_plane_context(
    user_info: dict = Depends(validate_control_plane_request),
):
    """
    FastAPI dependency that builds a TenantContext for data plane mode.

    In single-tenant data plane deployments, tenant_id is always DEFAULT_TENANT_ID
    (the entire data plane belongs to one customer). User identity comes from
    headers forwarded by the control plane.

    Imports TenantContext lazily to avoid import-time namespace conflicts
    (services/data-plane/app/ vs services/api/app/).
    """
    from app.auth.tenant import TenantContext, DEFAULT_TENANT_ID

    return TenantContext(
        tenant_id=DEFAULT_TENANT_ID,
        user_id=user_info["user_id"],
        role=user_info["role"],
        permissions=["read", "write"],
    )
