"""Versioned contracts shared across independently deployable products."""

from packages.platform_contracts.analytics import (
    AnalyticsHealthResponse,
    AnalyticsQueryRequest,
    AnalyticsQueryResponse,
    AnalyticsSchemaResponse,
)
from packages.platform_contracts.analytics_v2 import AnalyticsV2Response

__all__ = [
    "AnalyticsHealthResponse",
    "AnalyticsQueryRequest",
    "AnalyticsQueryResponse",
    "AnalyticsSchemaResponse",
    "AnalyticsV2Response",
]
