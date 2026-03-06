# services/api/app/auth/jwt.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.config import settings
import time

# OAuth2 scheme tells Swagger UI where to send the token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def create_token(
    user_id: str = "dev-user",
    role: str = "admin",
    permissions: list = None,
    expires_in: int = 86400,  # 24 hours
) -> str:
    """
    Creates a signed JWT token.
    Used by the /auth/token endpoint and the CLI helper.
    """
    payload = {
        "sub": user_id,
        "role": role,
        "permissions": permissions or ["read", "write"],
        "iat": int(time.time()),
        "exp": int(time.time()) + expires_in,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Validates the JWT Token from the Authorization header.
    Decodes user info (ID, Role, Permissions).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 1. Decode Token
        # Verify signature using the Secret Key defined in Config
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )

        user_id: str = payload.get("sub")
        role: str = payload.get("role", "user")

        if user_id is None:
            raise credentials_exception

        # 2. Check Expiration (Redundant if jwt.decode does it, but good for safety)
        exp = payload.get("exp")
        if exp and time.time() > exp:
            raise HTTPException(status_code=401, detail="Token expired")

        # Return user context dict
        return {
            "id": user_id,
            "role": role,
            "permissions": payload.get("permissions", [])
        }

    except JWTError:
        raise credentials_exception
