"""
Prometheus metrics endpoint
Implements O1 from PLAN_AMELIORATION_COMPLET_LOKO_2026-07-10.md

SECURITY: /metrics endpoint is admin-only, never exposed publicly.
"""

from fastapi import APIRouter, Depends, Response
from loko.api.auth import verify_admin_token
from loko.monitoring.metrics import get_metrics

router = APIRouter(tags=["monitoring"])


@router.get("/metrics")
async def prometheus_metrics(
    _admin: str = Depends(verify_admin_token)
) -> Response:
    """
    Prometheus metrics endpoint (admin-only).

    Security:
    - Requires admin token
    - Never exposed via public Caddy route
    - Accessible only from internal Docker network or authenticated admin

    Returns:
        Prometheus text format metrics
    """
    metrics_data = get_metrics()

    return Response(
        content=metrics_data,
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )
