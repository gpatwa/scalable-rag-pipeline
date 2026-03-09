# services/data-plane/tests/test_dp_registration.py
"""
Data Plane registration and heartbeat tests.

Tests use mocked httpx to verify control plane communication.

Run with:
    pytest services/data-plane/tests/test_dp_registration.py -v
"""
import asyncio

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# Path setup and env vars handled by conftest.py


class TestRegistration:
    """Tests for data plane registration with control plane."""

    @pytest.mark.asyncio
    async def test_skips_registration_when_no_url(self):
        """Should not attempt registration when CONTROL_PLANE_URL is not set."""
        from dp_app.registration.heartbeat import registration_loop

        # Should return immediately without errors
        await registration_loop(
            control_plane_url="",  # Empty = standalone mode
            data_plane_id="dp-test",
            data_plane_endpoint="http://localhost:8080",
            api_key="test-key",
            internal_api_key="internal-key",
            version="1.0.0",
        )

    @pytest.mark.asyncio
    async def test_successful_registration(self):
        """Should register successfully with control plane."""
        from dp_app.registration.heartbeat import registration_loop

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "registered", "heartbeat_interval": 30}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            # Run registration but cancel after first heartbeat sleep
            task = asyncio.create_task(
                registration_loop(
                    control_plane_url="http://control-plane:8001",
                    data_plane_id="dp-test",
                    data_plane_endpoint="http://localhost:8080",
                    api_key="test-key",
                    internal_api_key="internal-key",
                    version="1.0.0",
                    heartbeat_interval=1,  # Short interval for test
                )
            )

            # Give it time to register and start heartbeat
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify registration was called
            calls = mock_client.post.call_args_list
            assert len(calls) >= 1
            register_call = calls[0]
            assert "/internal/data-planes/register" in register_call.args[0]
            body = register_call.kwargs.get("json", {})
            assert body["data_plane_id"] == "dp-test"

    @pytest.mark.asyncio
    async def test_decommissioned_stops_registration(self):
        """Should stop if control plane returns 410 (decommissioned)."""
        from dp_app.registration.heartbeat import registration_loop

        mock_response = MagicMock()
        mock_response.status_code = 410

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            # Should return without starting heartbeat loop
            await registration_loop(
                control_plane_url="http://control-plane:8001",
                data_plane_id="dp-decom",
                data_plane_endpoint="http://localhost:8080",
                api_key="test-key",
                internal_api_key="internal-key",
                version="1.0.0",
            )

            # Should only be called once (the register attempt)
            assert mock_client.post.call_count == 1


class TestDataPlaneConfig:
    """Tests for data plane configuration."""

    def test_config_defaults(self):
        from dp_app.config import DataPlaneSettings

        settings = DataPlaneSettings(
            DATA_PLANE_ID="test-dp",
            _env_file=None,  # Don't read .env in tests
        )
        assert settings.DATA_PLANE_ID == "test-dp"
        assert settings.HEARTBEAT_INTERVAL_SECONDS == 30
        assert settings.APP_VERSION == "0.1.0"

    def test_config_with_custom_values(self):
        from dp_app.config import DataPlaneSettings

        settings = DataPlaneSettings(
            DATA_PLANE_ID="dp-custom",
            CONTROL_PLANE_URL="https://control.example.com",
            DATA_PLANE_API_KEY="my-api-key",
            HEARTBEAT_INTERVAL_SECONDS=60,
            INTERNAL_API_KEY="internal-secret",
            APP_VERSION="2.0.0",
            _env_file=None,
        )
        assert settings.DATA_PLANE_ID == "dp-custom"
        assert settings.CONTROL_PLANE_URL == "https://control.example.com"
        assert settings.HEARTBEAT_INTERVAL_SECONDS == 60
        assert settings.APP_VERSION == "2.0.0"
