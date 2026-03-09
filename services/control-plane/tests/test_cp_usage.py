# services/control-plane/tests/test_cp_usage.py
"""
Control Plane usage tracking tests.

Run with:
    pytest services/control-plane/tests/test_cp_usage.py -v
"""
import pytest


# db_session fixture provided by conftest.py


class TestUsageModel:
    """Tests for the UsageEvent model."""

    def test_model_has_required_columns(self):
        from app.models.usage import UsageEvent

        columns = {c.name for c in UsageEvent.__table__.columns}
        expected = {"id", "tenant_id", "event_type", "token_count", "latency_ms", "created_at"}
        assert expected.issubset(columns)

    @pytest.mark.asyncio
    async def test_create_usage_event(self, db_session):
        from app.models.usage import UsageEvent
        from sqlalchemy import select

        async with db_session() as session:
            async with session.begin():
                event = UsageEvent(
                    tenant_id="acme",
                    event_type="chat",
                    token_count=150,
                    latency_ms=420,
                )
                session.add(event)

        async with db_session() as session:
            result = await session.execute(
                select(UsageEvent).where(UsageEvent.tenant_id == "acme")
            )
            event = result.scalars().first()
            assert event is not None
            assert event.event_type == "chat"
            assert event.token_count == 150
            assert event.latency_ms == 420

    @pytest.mark.asyncio
    async def test_multiple_usage_events(self, db_session):
        from app.models.usage import UsageEvent
        from sqlalchemy import select, func

        async with db_session() as session:
            async with session.begin():
                session.add(UsageEvent(tenant_id="beta", event_type="chat", token_count=100))
                session.add(UsageEvent(tenant_id="beta", event_type="chat", token_count=200))
                session.add(UsageEvent(tenant_id="beta", event_type="upload", token_count=0))

        async with db_session() as session:
            result = await session.execute(
                select(func.count(UsageEvent.id)).where(UsageEvent.tenant_id == "beta")
            )
            count = result.scalar()
            assert count == 3

            result = await session.execute(
                select(func.sum(UsageEvent.token_count)).where(
                    UsageEvent.tenant_id == "beta",
                    UsageEvent.event_type == "chat",
                )
            )
            total_tokens = result.scalar()
            assert total_tokens == 300


class TestUsageRequestModels:
    """Tests for usage request/response Pydantic models."""

    def test_usage_report_request(self):
        from app.routes.usage import UsageReportRequest

        req = UsageReportRequest(
            tenant_id="acme",
            event_type="chat",
            token_count=500,
            latency_ms=200,
        )
        assert req.tenant_id == "acme"
        assert req.event_type == "chat"

    def test_usage_report_request_defaults(self):
        from app.routes.usage import UsageReportRequest

        req = UsageReportRequest(tenant_id="acme", event_type="feedback")
        assert req.token_count == 0
        assert req.latency_ms == 0

    def test_usage_summary_model(self):
        from app.routes.usage import UsageSummary

        summary = UsageSummary(
            tenant_id="acme",
            period_start="2025-01-01T00:00:00",
            period_end="2025-01-31T23:59:59",
            total_events=100,
            total_tokens=5000,
            avg_latency_ms=350.5,
            by_event_type={"chat": {"count": 80, "tokens": 5000}},
        )
        assert summary.total_events == 100
        assert summary.by_event_type["chat"]["count"] == 80
