# services/control-plane/tests/test_cp_rate_limit.py
"""
Control Plane rate limiting tests.

Run with:
    pytest services/control-plane/tests/test_cp_rate_limit.py -v
"""
import pytest


# db_session fixture provided by conftest.py


@pytest.fixture(autouse=True)
def clear_rate_limits():
    """Reset rate limit state between tests."""
    from app.middleware.rate_limit import reset_rate_limits
    reset_rate_limits()
    yield
    reset_rate_limits()


class TestRateLimiting:
    """Tests for per-tenant rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limit_allows_under_limit(self, db_session):
        from app.middleware.rate_limit import check_rate_limit

        # Default limit is 10 RPM in test config
        for _ in range(5):
            await check_rate_limit("test-tenant")
        # Should not raise

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_over_limit(self, db_session):
        from app.middleware.rate_limit import check_rate_limit
        from fastapi import HTTPException

        # Send requests up to the default limit (10)
        for _ in range(10):
            await check_rate_limit("limited-tenant")

        # 11th request should fail
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit("limited-tenant")
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_rate_limit_per_tenant_isolation(self, db_session):
        from app.middleware.rate_limit import check_rate_limit
        from fastapi import HTTPException

        # Fill up tenant-a's limit
        for _ in range(10):
            await check_rate_limit("tenant-a")

        # tenant-b should still be allowed
        await check_rate_limit("tenant-b")

        # tenant-a should be blocked
        with pytest.raises(HTTPException):
            await check_rate_limit("tenant-a")

    @pytest.mark.asyncio
    async def test_rate_limit_uses_tenant_config(self, db_session):
        """Tenant with custom rate limit should use that limit."""
        from app.middleware.rate_limit import check_rate_limit
        from app.models.tenant import Tenant
        from fastapi import HTTPException

        # Create tenant with custom rate limit of 3
        async with db_session() as session:
            async with session.begin():
                session.add(Tenant(
                    id="limited-3", name="Limited Corp",
                    rate_limit_rpm=3,
                ))

        # 3 requests should succeed
        for _ in range(3):
            await check_rate_limit("limited-3")

        # 4th should fail
        with pytest.raises(HTTPException) as exc_info:
            await check_rate_limit("limited-3")
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_rate_limit_zero_means_unlimited(self, db_session):
        """Tenant with rate_limit_rpm=0 should have no limit."""
        from app.middleware.rate_limit import check_rate_limit
        from app.models.tenant import Tenant

        async with db_session() as session:
            async with session.begin():
                session.add(Tenant(
                    id="unlimited", name="Unlimited Corp",
                    rate_limit_rpm=0,
                ))

        # Should not raise even with many requests
        for _ in range(100):
            await check_rate_limit("unlimited")

    @pytest.mark.asyncio
    async def test_reset_rate_limits(self, db_session):
        from app.middleware.rate_limit import check_rate_limit, reset_rate_limits

        # Fill up limit
        for _ in range(10):
            await check_rate_limit("reset-tenant")

        # Reset and try again
        reset_rate_limits("reset-tenant")

        # Should succeed again
        await check_rate_limit("reset-tenant")
