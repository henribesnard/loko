"""LOKO Analytics — Dashboard API endpoints (OBS-2).

Prefix: /api/bot/{bot_id}/analytics
Covers: KPIs, intent distribution, latency trends, event breakdown,
escalation analysis, guardrail triggers, session event log.

All endpoints are read-only and fail-open (empty results if analytics.db
is unavailable).  Auth uses require_tenant_or_ops (same as bot_dashboard).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from loko.analytics import queries
from loko.api.session_middleware import require_tenant_or_ops

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/bot",
    tags=["analytics-dashboard"],
)


def _resolve_date_range(from_date: str | None, to_date: str | None) -> tuple[str, str]:
    """Resolve date range with defaults (last 30 days)."""
    today = date.today()
    if not to_date:
        to_date = (today + timedelta(days=1)).isoformat()
    if not from_date:
        from_date = (today - timedelta(days=30)).isoformat()
    return from_date, to_date


# ---------------------------------------------------------------------------
# KPI overview
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/analytics/kpi")
async def get_analytics_kpi(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
    from_date: str = Query(default=None, alias="from"),
    to_date: str = Query(default=None, alias="to"),
) -> dict[str, Any]:
    """Get high-level KPI metrics for a bot."""
    f, t = _resolve_date_range(from_date, to_date)
    try:
        return queries.query_kpi_overview(bot_id, f, t)
    except Exception:
        logger.warning("analytics/kpi failed (fail-open)", exc_info=True)
        return queries._empty_kpi()


# ---------------------------------------------------------------------------
# Intent distribution
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/analytics/intents")
async def get_analytics_intents(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
    from_date: str = Query(default=None, alias="from"),
    to_date: str = Query(default=None, alias="to"),
    limit: int = Query(default=20, le=100),
) -> list[dict[str, Any]]:
    """Get top intents by volume with average confidence scores."""
    f, t = _resolve_date_range(from_date, to_date)
    try:
        return queries.query_intent_distribution(bot_id, f, t, limit)
    except Exception:
        logger.warning("analytics/intents failed (fail-open)", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Latency trends
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/analytics/latency")
async def get_analytics_latency(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
    from_date: str = Query(default=None, alias="from"),
    to_date: str = Query(default=None, alias="to"),
) -> list[dict[str, Any]]:
    """Get daily p50/p95 latency trends."""
    f, t = _resolve_date_range(from_date, to_date)
    try:
        return queries.query_latency_trends(bot_id, f, t)
    except Exception:
        logger.warning("analytics/latency failed (fail-open)", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Event type breakdown
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/analytics/events")
async def get_analytics_event_breakdown(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
    from_date: str = Query(default=None, alias="from"),
    to_date: str = Query(default=None, alias="to"),
) -> list[dict[str, Any]]:
    """Get event type distribution over the period."""
    f, t = _resolve_date_range(from_date, to_date)
    try:
        return queries.query_event_type_breakdown(bot_id, f, t)
    except Exception:
        logger.warning("analytics/events failed (fail-open)", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Event type timeseries
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/analytics/events/timeseries")
async def get_analytics_event_timeseries(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
    from_date: str = Query(default=None, alias="from"),
    to_date: str = Query(default=None, alias="to"),
    event_types: str = Query(default=None, description="Comma-separated event types"),
) -> list[dict[str, Any]]:
    """Get daily event type breakdown for charting."""
    f, t = _resolve_date_range(from_date, to_date)
    types_list = None
    if event_types:
        types_list = [e.strip() for e in event_types.split(",") if e.strip()]
    try:
        return queries.query_event_type_timeseries(bot_id, f, t, types_list)
    except Exception:
        logger.warning("analytics/events/timeseries failed (fail-open)", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Escalation analysis
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/analytics/escalations")
async def get_analytics_escalations(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
    from_date: str = Query(default=None, alias="from"),
    to_date: str = Query(default=None, alias="to"),
) -> dict[str, Any]:
    """Get escalation reasons breakdown by motif and intent."""
    f, t = _resolve_date_range(from_date, to_date)
    try:
        return queries.query_escalation_analysis(bot_id, f, t)
    except Exception:
        logger.warning("analytics/escalations failed (fail-open)", exc_info=True)
        return {"total_escalations": 0, "by_motif": [], "by_intent": []}


# ---------------------------------------------------------------------------
# Guardrail triggers
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/analytics/guardrails")
async def get_analytics_guardrails(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
    from_date: str = Query(default=None, alias="from"),
    to_date: str = Query(default=None, alias="to"),
) -> list[dict[str, Any]]:
    """Get most-triggered guardrail rules."""
    f, t = _resolve_date_range(from_date, to_date)
    try:
        return queries.query_guardrail_triggers(bot_id, f, t)
    except Exception:
        logger.warning("analytics/guardrails failed (fail-open)", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Session events
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/analytics/sessions/{session_id}")
async def get_analytics_session_events(
    bot_id: str,
    session_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
) -> list[dict[str, Any]]:
    """Get all analytics events for a specific session (debugging)."""
    try:
        return queries.query_session_events(bot_id, session_id)
    except Exception:
        logger.warning("analytics/sessions failed (fail-open)", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# KPI overview enriched (monitoring dashboard)
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/analytics/overview")
async def get_analytics_overview(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
    from_date: str = Query(default=None, alias="from"),
    to_date: str = Query(default=None, alias="to"),
) -> dict[str, Any]:
    """Enriched KPI overview with selfcare rate, satisfaction, avg turns."""
    f, t = _resolve_date_range(from_date, to_date)
    try:
        return queries.query_kpi_overview_enriched(bot_id, f, t)
    except Exception:
        logger.warning("analytics/overview failed (fail-open)", exc_info=True)
        return queries._empty_kpi_enriched()


# ---------------------------------------------------------------------------
# KPI timeseries (sparklines / charts)
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/analytics/kpi/timeseries")
async def get_analytics_kpi_timeseries(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
    from_date: str = Query(default=None, alias="from"),
    to_date: str = Query(default=None, alias="to"),
    granularity: str = Query(default="day", pattern="^(day|hour)$"),
) -> list[dict[str, Any]]:
    """KPI metrics per time bucket for sparklines and line charts."""
    f, t = _resolve_date_range(from_date, to_date)
    try:
        return queries.query_kpi_timeseries(bot_id, f, t, granularity)
    except Exception:
        logger.warning("analytics/kpi/timeseries failed (fail-open)", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Funnel
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/analytics/funnel")
async def get_analytics_funnel(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
    from_date: str = Query(default=None, alias="from"),
    to_date: str = Query(default=None, alias="to"),
) -> list[dict[str, Any]]:
    """5-step conversion funnel: messages → classified → answered → surveyed → resolved."""
    f, t = _resolve_date_range(from_date, to_date)
    try:
        return queries.query_funnel(bot_id, f, t)
    except Exception:
        logger.warning("analytics/funnel failed (fail-open)", exc_info=True)
        return queries._empty_funnel()


# ---------------------------------------------------------------------------
# Intent detail (monitoring table)
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/analytics/intents/detail")
async def get_analytics_intents_detail(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
    from_date: str = Query(default=None, alias="from"),
    to_date: str = Query(default=None, alias="to"),
    limit: int = Query(default=50, le=200),
) -> list[dict[str, Any]]:
    """Per-intent detail: volume, selfcare%, clarifications, escalations, trend."""
    f, t = _resolve_date_range(from_date, to_date)
    try:
        return queries.query_intent_detail(bot_id, f, t, limit)
    except Exception:
        logger.warning("analytics/intents/detail failed (fail-open)", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Sub-motif drill-down
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/analytics/intents/{intent_id}/sub-motifs")
async def get_analytics_sub_motifs(
    bot_id: str,
    intent_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
    from_date: str = Query(default=None, alias="from"),
    to_date: str = Query(default=None, alias="to"),
) -> list[dict[str, Any]]:
    """Sub-motif breakdown for a given intent."""
    f, t = _resolve_date_range(from_date, to_date)
    try:
        return queries.query_sub_motif_detail(bot_id, intent_id, f, t)
    except Exception:
        logger.warning("analytics/sub-motifs failed (fail-open)", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


@router.get("/{bot_id}/analytics/export")
async def get_analytics_export(
    bot_id: str,
    request: Request,
    _auth=Depends(require_tenant_or_ops),
    from_date: str = Query(default=None, alias="from"),
    to_date: str = Query(default=None, alias="to"),
    view: str = Query(default="overview", pattern="^(overview|intents|sub_motifs)$"),
) -> StreamingResponse:
    """Export analytics data as CSV."""
    f, t = _resolve_date_range(from_date, to_date)
    try:
        csv_content = queries.export_csv(bot_id, f, t, view)
    except Exception:
        logger.warning("analytics/export failed (fail-open)", exc_info=True)
        csv_content = ""

    filename = f"loko-analytics-{view}-{f}-{t}.csv"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
