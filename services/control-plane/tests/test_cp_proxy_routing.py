# services/control-plane/tests/test_cp_proxy_routing.py
"""
Control Plane proxy routing tests — tenant → data plane resolution.

Run with:
    pytest services/control-plane/tests/test_cp_proxy_routing.py -v
"""
from datetime import datetime

import pytest


# db_session fixture provided by conftest.py


@pytest.fixture(autouse=True)
def clear_routing_cache():
    """Clear the routing cache before each test."""
    from app.proxy.router import invalidate_cache
    invalidate_cache()
    yield
    invalidate_cache()


class TestResolveDataPlane:
    """Tests for resolve_data_plane routing."""

    @pytest.mark.asyncio
    async def test_resolve_healthy_data_plane(self, db_session):
        from app.models.data_plane import DataPlane
        from app.proxy.router import resolve_data_plane

        async with db_session() as session:
            async with session.begin():
                session.add(DataPlane(
                    id="dp-healthy", tenant_id="acme",
                    endpoint_url="https://dp-healthy:8080",
                    api_key_hash="hash123", status="healthy",
                    version="1.0.0", last_heartbeat_at=datetime.utcnow(),
                ))

        result = await resolve_data_plane("acme")
        assert result is not None
        assert result.id == "dp-healthy"
        assert result.endpoint_url == "https://dp-healthy:8080"
        assert result.api_key_hash == "hash123"

    @pytest.mark.asyncio
    async def test_resolve_returns_none_for_unhealthy(self, db_session):
        from app.models.data_plane import DataPlane
        from app.proxy.router import resolve_data_plane

        async with db_session() as session:
            async with session.begin():
                session.add(DataPlane(
                    id="dp-unhealthy", tenant_id="beta",
                    endpoint_url="https://dp-unhealthy:8080",
                    api_key_hash="hash456", status="unhealthy",
                    version="1.0.0", last_heartbeat_at=datetime.utcnow(),
                ))

        result = await resolve_data_plane("beta")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_returns_none_for_unknown_tenant(self, db_session):
        from app.proxy.router import resolve_data_plane

        result = await resolve_data_plane("nonexistent-tenant")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_returns_none_for_decommissioned(self, db_session):
        from app.models.data_plane import DataPlane
        from app.proxy.router import resolve_data_plane

        async with db_session() as session:
            async with session.begin():
                session.add(DataPlane(
                    id="dp-decom", tenant_id="gamma",
                    endpoint_url="https://dp-decom:8080",
                    api_key_hash="hash789", status="decommissioned",
                    version="1.0.0", last_heartbeat_at=datetime.utcnow(),
                ))

        result = await resolve_data_plane("gamma")
        assert result is None


class TestCacheInvalidation:
    """Tests for routing cache invalidation."""

    @pytest.mark.asyncio
    async def test_cache_invalidation_specific_tenant(self, db_session):
        from app.models.data_plane import DataPlane
        from app.proxy.router import resolve_data_plane, invalidate_cache, _cache

        async with db_session() as session:
            async with session.begin():
                session.add(DataPlane(
                    id="dp-cache", tenant_id="cached-tenant",
                    endpoint_url="https://dp-cache:8080",
                    api_key_hash="hash-c", status="healthy",
                    version="1.0.0", last_heartbeat_at=datetime.utcnow(),
                ))

        # Populate cache
        await resolve_data_plane("cached-tenant")
        assert "cached-tenant" in _cache

        # Invalidate just this tenant
        invalidate_cache("cached-tenant")
        assert "cached-tenant" not in _cache

    @pytest.mark.asyncio
    async def test_cache_invalidation_all(self, db_session):
        from app.models.data_plane import DataPlane
        from app.proxy.router import resolve_data_plane, invalidate_cache, _cache

        async with db_session() as session:
            async with session.begin():
                session.add(DataPlane(
                    id="dp-c1", tenant_id="tenant-a",
                    endpoint_url="https://dp-c1:8080",
                    api_key_hash="ha", status="healthy",
                    version="1.0.0", last_heartbeat_at=datetime.utcnow(),
                ))
                session.add(DataPlane(
                    id="dp-c2", tenant_id="tenant-b",
                    endpoint_url="https://dp-c2:8080",
                    api_key_hash="hb", status="healthy",
                    version="1.0.0", last_heartbeat_at=datetime.utcnow(),
                ))

        await resolve_data_plane("tenant-a")
        await resolve_data_plane("tenant-b")
        assert len(_cache) == 2

        invalidate_cache()
        assert len(_cache) == 0
