"""Service-level OpenSearch checks; never make unit CI depend on a cluster."""

import os

import pytest


pytestmark = pytest.mark.opensearch_integration


@pytest.mark.asyncio
async def test_local_opensearch_health_when_explicitly_enabled():
    if os.getenv("OPENSEARCH_INTEGRATION", "").lower() not in {"1", "true", "yes"}:
        pytest.skip("set OPENSEARCH_INTEGRATION=1 to run against the local OpenSearch profile")

    from app.search.opensearch import OpenSearchProvider
    from app.config import settings

    provider = OpenSearchProvider(config=settings)
    await provider.connect()
    try:
        health = await provider.health()
        assert health.status in {"healthy", "degraded"}
    finally:
        await provider.close()
