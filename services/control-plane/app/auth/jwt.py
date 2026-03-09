# services/control-plane/app/auth/jwt.py
"""
JWT authentication for the control plane.

Supports local HS256 tokens (dev) and external IdP via JWKS (production).
Same pattern as the monolith but standalone — no imports from services/api/.
"""
import time
import logging
from typing import Optional
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from ..config import cp_settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

# Default admin user for dev
DEFAULT_ADMIN_ID = "admin"


def create_token(
    user_id: str,
    tenant_id: str = "default",
    role: str = "user",
    expires_in: int = 86400,
) -> str:
    """Create a signed JWT token (dev mode)."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "permissions": ["read", "write"] if role != "admin" else ["read", "write", "admin"],
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, cp_settings.JWT_SECRET_KEY, algorithm=cp_settings.JWT_ALGORITHM)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """
    FastAPI dependency that validates JWT and returns user claims.

    Supports:
      - Bearer token from Authorization header
      - Query parameter ?token=... (for SSE connections)
    """
    token = None

    if credentials:
        token = credentials.credentials
    else:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    try:
        payload = jwt.decode(
            token,
            cp_settings.JWT_SECRET_KEY,
            algorithms=[cp_settings.JWT_ALGORITHM],
        )
        return {
            "id": payload.get("sub", "anonymous"),
            "tenant_id": payload.get("tenant_id", "default"),
            "role": payload.get("role", "user"),
            "permissions": payload.get("permissions", []),
        }
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency that requires admin role."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def validate_internal_key(request: Request) -> bool:
    """
    Validate internal API key for data plane -> control plane routes.

    Checks X-Internal-Key header against the configured shared secret.
    """
    key = request.headers.get("X-Internal-Key", "")
    if key != cp_settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid internal API key")
    return True
