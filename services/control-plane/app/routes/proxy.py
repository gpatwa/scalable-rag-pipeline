# services/control-plane/app/routes/proxy.py
"""
Proxy routes — forward end-user requests to the appropriate data plane.

Flow:
  1. Validate JWT → extract tenant_id
  2. Resolve tenant_id → data plane endpoint
  3. Forward request with mTLS → stream response back
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from ..auth.jwt import get_current_user
from ..proxy.router import resolve_data_plane
from ..proxy.streaming import proxy_stream, proxy_json
from ..middleware.rate_limit import check_rate_limit

router = APIRouter()


async def _get_data_plane_for_user(user: dict):
    """Resolve the data plane for the authenticated user's tenant."""
    tenant_id = user.get("tenant_id", "default")

    # Enforce per-tenant rate limit
    await check_rate_limit(tenant_id)

    dp_info = await resolve_data_plane(tenant_id)
    if not dp_info:
        raise HTTPException(
            status_code=503,
            detail=f"No healthy data plane available for tenant: {tenant_id}",
        )
    return dp_info, user


@router.post("/chat/stream")
async def proxy_chat_stream(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Proxy chat stream request to the data plane."""
    dp_info, user = await _get_data_plane_for_user(user)
    return await proxy_stream(
        request=request,
        data_plane_url=dp_info.endpoint_url,
        api_key=dp_info.api_key_hash,  # Data plane validates this
        user_id=user["id"],
        user_role=user.get("role", "user"),
        path="/api/v1/chat/stream",
    )


@router.post("/upload/generate-presigned-url")
async def proxy_upload(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Proxy upload request to the data plane."""
    dp_info, user = await _get_data_plane_for_user(user)
    return await proxy_json(
        request=request,
        data_plane_url=dp_info.endpoint_url,
        api_key=dp_info.api_key_hash,
        user_id=user["id"],
        user_role=user.get("role", "user"),
        path="/api/v1/upload/generate-presigned-url",
    )


@router.post("/feedback")
async def proxy_feedback(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Proxy feedback request to the data plane."""
    dp_info, user = await _get_data_plane_for_user(user)
    return await proxy_json(
        request=request,
        data_plane_url=dp_info.endpoint_url,
        api_key=dp_info.api_key_hash,
        user_id=user["id"],
        user_role=user.get("role", "user"),
        path="/api/v1/feedback",
    )
