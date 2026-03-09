# services/data-plane/tests/test_dp_health.py
"""
Data Plane health endpoint tests.

Run with:
    pytest services/data-plane/tests/test_dp_health.py -v
"""
import pytest


# Path setup and env vars handled by conftest.py


class TestHealthEndpoints:
    """Tests for data plane health endpoints."""

    @pytest.mark.asyncio
    async def test_liveness(self):
        from dp_app.routes.health import liveness

        result = await liveness()
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_info_default_metadata(self):
        from dp_app.routes.health import info

        result = await info()
        assert "data_plane_id" in result
        assert "version" in result
        assert "uptime_seconds" in result
        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_info_custom_metadata(self):
        from dp_app.routes.health import info, set_health_metadata

        set_health_metadata("dp-test-001", "2.0.0")
        result = await info()
        assert result["data_plane_id"] == "dp-test-001"
        assert result["version"] == "2.0.0"
        assert result["uptime_seconds"] >= 0


class TestHealthClientInjection:
    """Tests for health check client injection."""

    def test_set_health_clients(self):
        from dp_app.routes.health import set_health_clients, _vectordb_client, _graphdb_client
        from unittest.mock import MagicMock

        mock_vectordb = MagicMock()
        mock_graphdb = MagicMock()

        set_health_clients(mock_vectordb, mock_graphdb)

        # Verify the globals were set (via module-level inspection)
        import dp_app.routes.health as health_module
        assert health_module._vectordb_client is mock_vectordb
        assert health_module._graphdb_client is mock_graphdb

    def test_set_health_metadata(self):
        from dp_app.routes.health import set_health_metadata
        import dp_app.routes.health as health_module

        set_health_metadata("dp-meta-test", "3.0.0")
        assert health_module._dp_id == "dp-meta-test"
        assert health_module._dp_version == "3.0.0"
