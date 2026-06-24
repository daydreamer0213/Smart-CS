"""Analytics service — aggregate queries from conversations/messages."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message


def _cutoff(days: int) -> datetime:
    """Return a timezone-aware UTC datetime `days` days ago."""
    return datetime.now(timezone.utc) - timedelta(days=days)


def get_overview(db: Session, tenant_id: str, days: int = 7) -> dict:
    """Dashboard overview: conversation count, avg latency, cache hit rate, handoff rate."""
    cutoff = _cutoff(days)
    total = (
        db.query(Conversation)
        .filter(
            Conversation.tenant_id == tenant_id,
            Conversation.created_at >= cutoff,
        )
        .count()
    )
    avg_latency = (
        db.query(func.avg(Message.latency_ms))
        .join(Conversation)
        .filter(
            Conversation.tenant_id == tenant_id,
            Message.created_at >= cutoff,
        )
        .scalar()
        or 0
    )
    cache_hits = (
        db.query(Message)
        .join(Conversation)
        .filter(
            Conversation.tenant_id == tenant_id,
            Message.cache_hit.in_(["L1", "L2"]),
            Message.created_at >= cutoff,
        )
        .count()
    )
    total_msgs = (
        db.query(Message)
        .join(Conversation)
        .filter(
            Conversation.tenant_id == tenant_id,
            Message.created_at >= cutoff,
        )
        .count()
    )
    handoffs = (
        db.query(Message)
        .join(Conversation)
        .filter(
            Conversation.tenant_id == tenant_id,
            Message.intent == "human",
            Message.created_at >= cutoff,
        )
        .count()
    )

    return {
        "total_conversations": total,
        "avg_latency_ms": round(float(avg_latency), 2),
        "cache_hit_rate": round(cache_hits / max(total_msgs, 1), 3),
        "handoff_rate": round(handoffs / max(total_msgs, 1), 3),
    }


def get_intent_distribution(db: Session, tenant_id: str, days: int = 7) -> list[dict]:
    """Intent distribution for the given period."""
    cutoff = _cutoff(days)
    results = (
        db.query(Message.intent, func.count(Message.id))
        .join(Conversation)
        .filter(
            Conversation.tenant_id == tenant_id,
            Message.intent.isnot(None),
            Message.created_at >= cutoff,
        )
        .group_by(Message.intent)
        .all()
    )
    return [{"intent": intent or "unknown", "count": count} for intent, count in results]


def get_daily_trend(db: Session, tenant_id: str, days: int = 7) -> list[dict]:
    """Daily message trend with cache hit breakdown."""
    cutoff = _cutoff(days)
    results = (
        db.query(
            func.date(Message.created_at).label("date"),
            func.count(Message.id).label("total"),
            func.sum(
                case((Message.cache_hit.in_(["L1", "L2"]), 1), else_=0)
            ).label("hits"),
        )
        .join(Conversation)
        .filter(
            Conversation.tenant_id == tenant_id,
            Message.created_at >= cutoff,
        )
        .group_by(func.date(Message.created_at))
        .order_by("date")
        .all()
    )
    return [
        {"date": str(r.date), "total": r.total, "hits": int(r.hits or 0)}
        for r in results
    ]


def get_top_knowledge(
    db: Session, tenant_id: str, days: int = 7, limit: int = 10
) -> list[dict]:
    """Top-K knowledge items by query frequency."""
    cutoff = _cutoff(days)
    results = (
        db.query(
            Message.sources_json,
            func.count(Message.id).label("count"),
        )
        .join(Conversation)
        .filter(
            Conversation.tenant_id == tenant_id,
            Message.sources_json.isnot(None),
            Message.created_at >= cutoff,
        )
        .group_by(Message.sources_json)
        .order_by(func.count(Message.id).desc())
        .limit(limit)
        .all()
    )
    return [{"sources": r.sources_json, "count": r.count} for r in results]
