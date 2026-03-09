# services/control-plane/tests/test_cp_data_plane_registry.py
"""
Control Plane data plane registry tests — registration, heartbeat, stale detection.

Run with:
    pytest services/control-plane/tests/test_cp_data_plane_registry.py -v
"""
from datetime import datetime, timedelta

import pytest


# db_session fixture provided by conftest.py


class TestDataPlaneModel:
    """Tests for the DataPlane SQLAlchemy model."""

    def test_model_has_required_columns(self):
        from app.models.data_plane import DataPlane

        columns = {c.name for c in DataPlane.__table__.columns}
        expected = {
            "id", "tenant_id", "endpoint_url", "api_key_hash",
            "status", "version", "last_heartbeat_at",
        }
        assert expected.issubset(columns)

    @pytest.mark.asyncio
    async def test_register_data_plane(self, db_session):
        from app.models.data_plane import DataPlane
        from sqlalchemy import select

        async with db_session() as session:
            async with session.begin():
                dp = DataPlane(
                    id="dp-001",
                    tenant_id="acme",
                    endpoint_url="https://dp-001.acme.internal:8080",
                    api_key_hash="abc123hash",
                    status="healthy",
                    version="1.0.0",
                    last_heartbeat_at=datetime.utcnow(),
                )
                session.add(dp)

        async with db_session() as session:
            result = await session.execute(
                select(DataPlane).where(DataPlane.id == "dp-001")
            )
            dp = result.scalars().first()
            assert dp is not None
            assert dp.tenant_id == "acme"
            assert dp.status == "healthy"
            assert dp.endpoint_url == "https://dp-001.acme.internal:8080"

    @pytest.mark.asyncio
    async def test_heartbeat_updates_timestamp(self, db_session):
        from app.models.data_plane import DataPlane
        from sqlalchemy import select

        old_time = datetime.utcnow() - timedelta(minutes=5)

        async with db_session() as session:
            async with session.begin():
                session.add(DataPlane(
                    id="dp-002", tenant_id="beta",
                    endpoint_url="https://dp-002:8080",
                    api_key_hash="hash2", status="healthy",
                    version="1.0.0", last_heartbeat_at=old_time,
                ))

        new_time = datetime.utcnow()
        async with db_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(DataPlane).where(DataPlane.id == "dp-002")
                )
                dp = result.scalars().first()
                dp.last_heartbeat_at = new_time

        async with db_session() as session:
            result = await session.execute(
                select(DataPlane).where(DataPlane.id == "dp-002")
            )
            dp = result.scalars().first()
            assert dp.last_heartbeat_at >= new_time

    @pytest.mark.asyncio
    async def test_stale_data_plane_detection(self, db_session):
        """Data planes with stale heartbeat should be detectable."""
        from app.models.data_plane import DataPlane
        from app.registry.manager import DEFAULT_HEARTBEAT_INTERVAL, STALE_MULTIPLIER
        from sqlalchemy import select

        stale_threshold = timedelta(seconds=DEFAULT_HEARTBEAT_INTERVAL * STALE_MULTIPLIER)
        stale_time = datetime.utcnow() - stale_threshold - timedelta(seconds=10)

        async with db_session() as session:
            async with session.begin():
                session.add(DataPlane(
                    id="dp-stale", tenant_id="gamma",
                    endpoint_url="https://dp-stale:8080",
                    api_key_hash="hash3", status="healthy",
                    version="1.0.0", last_heartbeat_at=stale_time,
                ))

        async with db_session() as session:
            result = await session.execute(
                select(DataPlane).where(DataPlane.id == "dp-stale")
            )
            dp = result.scalars().first()
            now = datetime.utcnow()
            assert (now - dp.last_heartbeat_at) > stale_threshold

    @pytest.mark.asyncio
    async def test_decommission_data_plane(self, db_session):
        from app.models.data_plane import DataPlane
        from sqlalchemy import select

        async with db_session() as session:
            async with session.begin():
                session.add(DataPlane(
                    id="dp-decom", tenant_id="delta",
                    endpoint_url="https://dp-decom:8080",
                    api_key_hash="hash4", status="healthy",
                    version="1.0.0", last_heartbeat_at=datetime.utcnow(),
                ))

        async with db_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(DataPlane).where(DataPlane.id == "dp-decom")
                )
                dp = result.scalars().first()
                dp.status = "decommissioned"

        async with db_session() as session:
            result = await session.execute(
                select(DataPlane).where(DataPlane.id == "dp-decom")
            )
            dp = result.scalars().first()
            assert dp.status == "decommissioned"


class TestDataPlaneRequestModels:
    """Tests for data plane registration request models."""

    def test_register_request_defaults(self):
        from app.routes.data_planes import RegisterRequest

        req = RegisterRequest(
            data_plane_id="dp-1",
            endpoint_url="https://dp-1:8080",
            api_key="secret-key",
        )
        assert req.version == "0.0.0"
        assert req.tenant_id == "default"

    def test_heartbeat_request_defaults(self):
        from app.routes.data_planes import HeartbeatRequest

        req = HeartbeatRequest(data_plane_id="dp-1")
        assert req.status == "healthy"
        assert req.uptime_seconds == 0
        assert req.metrics == {}

    def test_data_plane_response_model(self):
        from app.routes.data_planes import DataPlaneResponse

        resp = DataPlaneResponse(
            id="dp-1", tenant_id="acme",
            endpoint_url="https://dp-1:8080",
            status="healthy", version="1.0.0",
        )
        assert resp.id == "dp-1"
        assert resp.last_heartbeat_at is None
