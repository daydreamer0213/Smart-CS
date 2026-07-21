"""Persistence helpers for the authenticated enterprise assistant."""

from datetime import datetime, timedelta, timezone
import re

from sqlalchemy.orm import Session

from app.config import settings
from app.models.conversation import Conversation, Message


_SOURCE_CITATION_PATTERN = re.compile(r"\[source:([^\]]+)\]")


def render_reply_for_display(reply: str, sources: list[dict]) -> str:
    """Replace machine citation tokens with tenant-authorized source titles."""
    titles = {
        str(source.get("source_id")): str(source.get("title") or "").strip()
        for source in sources
        if source.get("source_id")
    }

    def replace_citation(match: re.Match) -> str:
        title = titles.get(match.group(1)) or "企业知识库文档"
        return f"来源：《{title}》"

    return _SOURCE_CITATION_PATTERN.sub(replace_citation, reply)


def load_history(db: Session, tenant_id: str, user_id: str, session_id: str) -> list[dict[str, str]]:
    """Return only this employee's recent completed assistant turns."""
    conversation = db.query(Conversation).filter(
        Conversation.tenant_id == tenant_id,
        Conversation.visitor_id == user_id,
        Conversation.session_id == session_id,
    ).first()
    if conversation is None:
        return []
    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id, Message.role.in_(("user", "assistant")))
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(settings.max_conversation_turns * 2)
        .all()
    )
    return [{"role": item.role, "content": item.content} for item in reversed(messages)]


def persist_turn(db: Session, tenant_id: str, user_id: str, session_id: str, message: str, reply: str) -> None:
    """Persist a completed turn, scoped to the authenticated user."""
    conversation = db.query(Conversation).filter(
        Conversation.tenant_id == tenant_id,
        Conversation.visitor_id == user_id,
        Conversation.session_id == session_id,
    ).first()
    if conversation is None:
        conversation = Conversation(tenant_id=tenant_id, visitor_id=user_id, session_id=session_id, status="active", message_count=0)
        db.add(conversation)
        db.flush()
    conversation.message_count = (conversation.message_count or 0) + 1
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add_all([
        Message(conversation_id=conversation.id, role="user", content=message, created_at=now),
        Message(conversation_id=conversation.id, role="assistant", content=reply, created_at=now + timedelta(microseconds=1)),
    ])
    db.commit()
