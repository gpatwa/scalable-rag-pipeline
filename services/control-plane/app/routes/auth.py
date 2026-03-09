# services/control-plane/app/routes/auth.py
"""
Authentication routes for the control plane.

Provides a dev token endpoint (disabled in production).
In production, clients authenticate via external IdP (Auth0, Azure AD, Cognito).
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from ..config import cp_settings
from ..auth.jwt import create_token

router = APIRouter()


class TokenRequest(BaseModel):
    user_id: str = "testuser"
    tenant_id: str = "default"
    role: str = "user"


@router.post("/token")
async def generate_token(req: TokenRequest):
    """
    Generate a dev JWT token.

    Only available when ENV=dev. In production, use your IdP.
    """
    if cp_settings.ENV not in ("dev", "development", "test"):
        raise HTTPException(
            status_code=403,
            detail="Token endpoint disabled in production. Use your IdP.",
        )

    token = create_token(
        user_id=req.user_id,
        tenant_id=req.tenant_id,
        role=req.role,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "tenant_id": req.tenant_id,
    }
