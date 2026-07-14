"""Admin analytics dashboard — aggregate queries and statistics.

Endpoints:
  GET  /api/v1/admin/{tenant_slug}/analytics/overview   Dashboard overview
  GET  /api/v1/admin/{tenant_slug}/analytics/intents    Intent distribution
  GET  /api/v1/admin/{tenant_slug}/analytics/daily       Daily trends
  GET  /api/v1/admin/{tenant_slug}/analytics/knowledge   Knowledge hit rankings
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.admin.auth import admin_auth
from app.api.deps import get_db, get_tenant
from app.models.tenant import Tenant
from app.services import analytics_service

router = APIRouter()


@router.get("/api/v1/admin/{tenant_slug}/analytics/overview")
async def analytics_overview(
    tenant_slug: str,
    days: int = Query(7, ge=1, le=365),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin=Depends(admin_auth),
):
    """Dashboard overview: conversation count, avg latency, cache hit rate, handoff rate."""
    return analytics_service.get_overview(db, tenant.id, days)


@router.get("/api/v1/admin/{tenant_slug}/analytics/intents")
async def analytics_intents(
    tenant_slug: str,
    days: int = Query(7, ge=1, le=365),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin=Depends(admin_auth),
):
    """Intent distribution for the given period."""
    return analytics_service.get_intent_distribution(db, tenant.id, days)


@router.get("/api/v1/admin/{tenant_slug}/analytics/daily")
async def analytics_daily(
    tenant_slug: str,
    days: int = Query(7, ge=1, le=365),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin=Depends(admin_auth),
):
    """Daily message trend with cache hit breakdown."""
    return analytics_service.get_daily_trend(db, tenant.id, days)


@router.get("/api/v1/admin/{tenant_slug}/analytics/knowledge")
async def analytics_knowledge(
    tenant_slug: str,
    days: int = Query(7, ge=1, le=365),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
    _admin=Depends(admin_auth),
):
    """Top-K knowledge items by query frequency."""
    return analytics_service.get_top_knowledge(db, tenant.id, days, limit)
