# services/control-plane/app/routes/usage.py
"""
Usage tracking and billing endpoints.

Records usage events from data planes and provides admin
endpoints for querying usage by tenant.
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from sqlalchemy import select, func
from ..auth.jwt import require_admin, validate_internal_key
from .. import db as db_module
from ..models.usage import UsageEvent

router = APIRouter()


class UsageReportRequest(BaseModel):
    """Usage event reported by a data plane."""
    tenant_id: str
    event_type: str  # "chat" | "upload" | "feedback"
    token_count: int = 0
    latency_ms: int = 0


class UsageSummary(BaseModel):
    """Aggregated usage stats for a tenant."""
    tenant_id: str
    period_start: str
    period_end: str
    total_events: int
    total_tokens: int
    avg_latency_ms: float
    by_event_type: dict


# ── Internal route (data plane → control plane) ────────────────────────

@router.post("/internal/report")
async def report_usage(
    req: UsageReportRequest,
    _auth: bool = Depends(validate_internal_key),
):
    """
    Record a usage event from a data plane.

    Called by data planes after processing requests for billing/analytics.
    """
    async with db_module.AsyncSessionLocal() as session:
        async with session.begin():
            event = UsageEvent(
                tenant_id=req.tenant_id,
                event_type=req.event_type,
                token_count=req.token_count,
                latency_ms=req.latency_ms,
            )
            session.add(event)

    return {"status": "recorded"}


# ── Admin routes ────────────────────────────────────────────────────────

@router.get("/{tenant_id}")
async def get_usage(
    tenant_id: str,
    days: int = Query(default=30, ge=1, le=365),
    _admin: dict = Depends(require_admin),
):
    """
    Get usage summary for a tenant over the specified period.

    Defaults to last 30 days.
    """
    period_start = datetime.utcnow() - timedelta(days=days)
    period_end = datetime.utcnow()

    async with db_module.AsyncSessionLocal() as session:
        # Total events and tokens
        totals = await session.execute(
            select(
                func.count(UsageEvent.id).label("total_events"),
                func.coalesce(func.sum(UsageEvent.token_count), 0).label("total_tokens"),
                func.coalesce(func.avg(UsageEvent.latency_ms), 0).label("avg_latency"),
            ).where(
                UsageEvent.tenant_id == tenant_id,
                UsageEvent.created_at >= period_start,
            )
        )
        row = totals.first()

        # Breakdown by event type
        type_breakdown = await session.execute(
            select(
                UsageEvent.event_type,
                func.count(UsageEvent.id).label("count"),
                func.coalesce(func.sum(UsageEvent.token_count), 0).label("tokens"),
            ).where(
                UsageEvent.tenant_id == tenant_id,
                UsageEvent.created_at >= period_start,
            ).group_by(UsageEvent.event_type)
        )
        by_type = {
            r.event_type: {"count": r.count, "tokens": r.tokens}
            for r in type_breakdown
        }

    return UsageSummary(
        tenant_id=tenant_id,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        total_events=row.total_events or 0,
        total_tokens=row.total_tokens or 0,
        avg_latency_ms=round(float(row.avg_latency or 0), 2),
        by_event_type=by_type,
    )


@router.get("/")
async def list_usage_summary(
    days: int = Query(default=30, ge=1, le=365),
    _admin: dict = Depends(require_admin),
):
    """
    Get aggregated usage across all tenants for the specified period.
    """
    period_start = datetime.utcnow() - timedelta(days=days)

    async with db_module.AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                UsageEvent.tenant_id,
                func.count(UsageEvent.id).label("total_events"),
                func.coalesce(func.sum(UsageEvent.token_count), 0).label("total_tokens"),
                func.coalesce(func.avg(UsageEvent.latency_ms), 0).label("avg_latency"),
            ).where(
                UsageEvent.created_at >= period_start,
            ).group_by(UsageEvent.tenant_id)
        )
        summaries = [
            {
                "tenant_id": r.tenant_id,
                "total_events": r.total_events,
                "total_tokens": r.total_tokens,
                "avg_latency_ms": round(float(r.avg_latency or 0), 2),
            }
            for r in result
        ]

    return {
        "period_days": days,
        "period_start": period_start.isoformat(),
        "tenants": summaries,
    }
