# services/control-plane/tests/test_cp_auth.py
"""
Control Plane auth tests — JWT token creation, validation, admin/internal auth.

Run with:
    pytest services/control-plane/tests/test_cp_auth.py -v
"""
import pytest


# Path setup and env vars handled by conftest.py


class TestJWTTokenCreation:
    """Tests for control plane JWT token creation."""

    def test_create_token_includes_claims(self):
        from app.auth.jwt import create_token
        from jose import jwt
        from app.config import cp_settings

        token = create_token(
            user_id="alice",
            tenant_id="acme-corp",
            role="admin",
        )

        payload = jwt.decode(
            token, cp_settings.JWT_SECRET_KEY, algorithms=[cp_settings.JWT_ALGORITHM]
        )
        assert payload["sub"] == "alice"
        assert payload["tenant_id"] == "acme-corp"
        assert payload["role"] == "admin"
        assert "admin" in payload["permissions"]

    def test_create_token_user_permissions(self):
        from app.auth.jwt import create_token
        from jose import jwt
        from app.config import cp_settings

        token = create_token(user_id="bob", role="user")
        payload = jwt.decode(
            token, cp_settings.JWT_SECRET_KEY, algorithms=[cp_settings.JWT_ALGORITHM]
        )
        assert "admin" not in payload["permissions"]
        assert "read" in payload["permissions"]
        assert "write" in payload["permissions"]

    def test_create_token_default_values(self):
        from app.auth.jwt import create_token
        from jose import jwt
        from app.config import cp_settings

        token = create_token(user_id="charlie")
        payload = jwt.decode(
            token, cp_settings.JWT_SECRET_KEY, algorithms=[cp_settings.JWT_ALGORITHM]
        )
        assert payload["tenant_id"] == "default"
        assert payload["role"] == "user"

    def test_create_token_expiry(self):
        from app.auth.jwt import create_token
        from jose import jwt
        from app.config import cp_settings

        token = create_token(user_id="test", expires_in=3600)
        payload = jwt.decode(
            token, cp_settings.JWT_SECRET_KEY, algorithms=[cp_settings.JWT_ALGORITHM]
        )
        assert payload["exp"] - payload["iat"] == 3600


class TestJWTTokenValidation:
    """Tests for control plane JWT validation."""

    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self):
        from app.auth.jwt import create_token, get_current_user
        from unittest.mock import MagicMock

        token = create_token(user_id="alice", tenant_id="acme", role="user")

        # Mock the FastAPI Request and credentials
        mock_request = MagicMock()
        mock_request.query_params = {}

        mock_creds = MagicMock()
        mock_creds.credentials = token

        user = await get_current_user(mock_request, mock_creds)
        assert user["id"] == "alice"
        assert user["tenant_id"] == "acme"
        assert user["role"] == "user"

    @pytest.mark.asyncio
    async def test_get_current_user_expired_token(self):
        from app.auth.jwt import create_token, get_current_user
        from fastapi import HTTPException
        from unittest.mock import MagicMock

        token = create_token(user_id="expired", expires_in=-10)

        mock_request = MagicMock()
        mock_request.query_params = {}
        mock_creds = MagicMock()
        mock_creds.credentials = token

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, mock_creds)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_no_token(self):
        from app.auth.jwt import get_current_user
        from fastapi import HTTPException
        from unittest.mock import MagicMock

        mock_request = MagicMock()
        mock_request.query_params = {}

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, None)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_query_param_token(self):
        from app.auth.jwt import create_token, get_current_user
        from unittest.mock import MagicMock

        token = create_token(user_id="sse-user", tenant_id="sse-tenant")

        mock_request = MagicMock()
        mock_request.query_params = {"token": token}

        user = await get_current_user(mock_request, None)
        assert user["id"] == "sse-user"
        assert user["tenant_id"] == "sse-tenant"


class TestAdminAuth:
    """Tests for admin role enforcement."""

    @pytest.mark.asyncio
    async def test_require_admin_allows_admin(self):
        from app.auth.jwt import require_admin

        admin_user = {"id": "admin-user", "role": "admin", "permissions": ["admin"]}
        result = await require_admin(admin_user)
        assert result["id"] == "admin-user"

    @pytest.mark.asyncio
    async def test_require_admin_blocks_regular_user(self):
        from app.auth.jwt import require_admin
        from fastapi import HTTPException

        regular_user = {"id": "regular-user", "role": "user", "permissions": ["read"]}
        with pytest.raises(HTTPException) as exc_info:
            await require_admin(regular_user)
        assert exc_info.value.status_code == 403


class TestInternalAuth:
    """Tests for data plane -> control plane internal key validation."""

    @pytest.mark.asyncio
    async def test_valid_internal_key(self):
        from app.auth.jwt import validate_internal_key
        from app.config import cp_settings
        from unittest.mock import MagicMock

        mock_request = MagicMock()
        mock_request.headers = {"X-Internal-Key": cp_settings.INTERNAL_API_KEY}

        result = await validate_internal_key(mock_request)
        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_internal_key(self):
        from app.auth.jwt import validate_internal_key
        from fastapi import HTTPException
        from unittest.mock import MagicMock

        mock_request = MagicMock()
        mock_request.headers = {"X-Internal-Key": "wrong-key"}

        with pytest.raises(HTTPException) as exc_info:
            await validate_internal_key(mock_request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_internal_key(self):
        from app.auth.jwt import validate_internal_key
        from fastapi import HTTPException
        from unittest.mock import MagicMock

        mock_request = MagicMock()
        mock_request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            await validate_internal_key(mock_request)
        assert exc_info.value.status_code == 401
