# services/data-plane/tests/test_dp_auth.py
"""
Data Plane authentication tests — API key validation, user context extraction.

Run with:
    pytest services/data-plane/tests/test_dp_auth.py -v
"""
import pytest


# Path setup and env vars handled by conftest.py


class TestAPIKeyValidation:
    """Tests for X-DataPlane-Key authentication."""

    @pytest.mark.asyncio
    async def test_valid_api_key(self):
        from dp_app.auth.control_plane_auth import (
            set_api_key,
            validate_control_plane_request,
        )
        from unittest.mock import MagicMock

        set_api_key("test-dp-key-123")

        mock_request = MagicMock()
        mock_request.headers = {
            "X-DataPlane-Key": "test-dp-key-123",
            "X-User-Id": "alice",
            "X-User-Role": "user",
        }

        result = await validate_control_plane_request(mock_request)
        assert result["user_id"] == "alice"
        assert result["role"] == "user"

    @pytest.mark.asyncio
    async def test_invalid_api_key(self):
        from dp_app.auth.control_plane_auth import (
            set_api_key,
            validate_control_plane_request,
        )
        from fastapi import HTTPException
        from unittest.mock import MagicMock

        set_api_key("correct-key")

        mock_request = MagicMock()
        mock_request.headers = {
            "X-DataPlane-Key": "wrong-key",
            "X-User-Id": "alice",
        }

        with pytest.raises(HTTPException) as exc_info:
            await validate_control_plane_request(mock_request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_api_key_when_configured(self):
        from dp_app.auth.control_plane_auth import (
            set_api_key,
            validate_control_plane_request,
        )
        from fastapi import HTTPException
        from unittest.mock import MagicMock

        set_api_key("configured-key")

        mock_request = MagicMock()
        mock_request.headers = {"X-User-Id": "alice"}

        with pytest.raises(HTTPException) as exc_info:
            await validate_control_plane_request(mock_request)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_api_key_configured_allows_all(self):
        """When no API key is set (dev mode), all requests pass."""
        from dp_app.auth.control_plane_auth import (
            set_api_key,
            validate_control_plane_request,
        )
        from unittest.mock import MagicMock

        set_api_key("")  # No key configured

        mock_request = MagicMock()
        mock_request.headers = {"X-User-Id": "bob", "X-User-Role": "admin"}

        result = await validate_control_plane_request(mock_request)
        assert result["user_id"] == "bob"
        assert result["role"] == "admin"


class TestUserContextExtraction:
    """Tests for user context forwarded via headers."""

    @pytest.mark.asyncio
    async def test_extracts_user_headers(self):
        from dp_app.auth.control_plane_auth import (
            set_api_key,
            validate_control_plane_request,
        )
        from unittest.mock import MagicMock

        set_api_key("")

        mock_request = MagicMock()
        mock_request.headers = {
            "X-User-Id": "charlie",
            "X-User-Role": "admin",
        }

        result = await validate_control_plane_request(mock_request)
        assert result["user_id"] == "charlie"
        assert result["role"] == "admin"

    @pytest.mark.asyncio
    async def test_defaults_for_missing_headers(self):
        from dp_app.auth.control_plane_auth import (
            set_api_key,
            validate_control_plane_request,
        )
        from unittest.mock import MagicMock

        set_api_key("")

        mock_request = MagicMock()
        mock_request.headers = {}

        result = await validate_control_plane_request(mock_request)
        assert result["user_id"] == "anonymous"
        assert result["role"] == "user"


class TestDataPlaneContext:
    """Tests for TenantContext in single-tenant mode."""

    def test_tenant_context_uses_default_tenant(self):
        """In data plane mode, tenant_id should always be DEFAULT_TENANT_ID."""
        from app.auth.tenant import TenantContext, DEFAULT_TENANT_ID

        ctx = TenantContext(
            tenant_id=DEFAULT_TENANT_ID,
            user_id="alice",
            role="user",
            permissions=["read", "write"],
        )
        assert ctx.tenant_id == DEFAULT_TENANT_ID

    def test_tenant_context_immutable(self):
        from app.auth.tenant import TenantContext

        ctx = TenantContext(
            tenant_id="default", user_id="bob",
            role="user", permissions=["read"],
        )
        with pytest.raises(AttributeError):
            ctx.tenant_id = "hacked"
