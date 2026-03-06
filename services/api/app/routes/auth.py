# services/api/app/routes/auth.py
"""
Dev-only token endpoint.
In production, tokens would be issued by an external IdP (Cognito, Auth0, etc.).
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.config import settings
from app.auth.jwt import create_token

router = APIRouter()


class TokenRequest(BaseModel):
    user_id: str = Field(default="dev-user", description="User ID for the token")
    role: str = Field(default="admin", description="User role")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    expires_in: int


@router.post("/token", response_model=TokenResponse)
async def issue_dev_token(req: TokenRequest = TokenRequest()):
    """
    Issues a JWT token for local development.
    Only available when ENV=dev.
    """
    if settings.ENV != "dev":
        raise HTTPException(
            status_code=403,
            detail="Token endpoint is only available in dev mode."
        )

    expires_in = 86400  # 24 hours
    token = create_token(
        user_id=req.user_id,
        role=req.role,
        expires_in=expires_in,
    )

    return TokenResponse(
        access_token=token,
        user_id=req.user_id,
        expires_in=expires_in,
    )
