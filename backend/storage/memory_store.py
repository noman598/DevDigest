# backend/storage/memory_store.py
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set
import uuid

from sqlalchemy.orm import Session
from storage.models import UserMemory
from utils.logger import log


def get_or_create_user_memory(session: Session, user_id: uuid.UUID) -> UserMemory:
    """Retrieves existing memory for a user or initializes a new memory record."""
    mem = session.query(UserMemory).filter(UserMemory.user_id == user_id).first()
    if not mem:
        mem = UserMemory(
            id=uuid.uuid4(),
            user_id=user_id,
            delivered_history=[],
            recent_topics={},
            agent_notes="Initial memory initialized.",
            last_curated_at=datetime.now(),
        )
        session.add(mem)
        session.commit()
        session.refresh(mem)
        log.info("memory_store.created", user_id=str(user_id))
    return mem


def get_delivered_history_ids(session: Session, user_id: uuid.UUID, days_window: int = 7) -> Set[str]:
    """
    Returns the set of external_ids delivered to this user within the last `days_window` days.
    Used for strict deduplication to prevent showing the same content across multiple days.
    """
    mem = session.query(UserMemory).filter(UserMemory.user_id == user_id).first()
    if not mem or not mem.delivered_history:
        return set()

    cutoff = datetime.now() - timedelta(days=days_window)
    recent_ids = set()

    for entry in mem.delivered_history:
        if isinstance(entry, dict):
            delivered_at_str = entry.get("delivered_at")
            ext_id = entry.get("external_id")
            if ext_id and delivered_at_str:
                try:
                    delivered_at = datetime.fromisoformat(delivered_at_str)
                    if delivered_at >= cutoff:
                        recent_ids.add(ext_id)
                except Exception:
                    recent_ids.add(ext_id)
            elif ext_id:
                recent_ids.add(ext_id)

    return recent_ids


def get_memory_context_string(session: Session, user_id: uuid.UUID) -> str:
    """Formats user memory into a concise string for LLM Agent context (~60 tokens)."""
    mem = session.query(UserMemory).filter(UserMemory.user_id == user_id).first()
    if not mem:
        return "User Memory: First time receiving digest. No prior history."

    history = mem.delivered_history or []
    recent_items = [f"'{h.get('title', h.get('external_id', 'item'))}'" for h in history[-5:] if isinstance(h, dict)]
    history_str = ", ".join(recent_items) if recent_items else "None"

    # Top fatigue topics
    topics_dict = mem.recent_topics or {}
    sorted_topics = sorted(topics_dict.items(), key=lambda x: x[1], reverse=True)[:4]
    fatigue_str = ", ".join(f"{t} ({cnt}x)" for t, cnt in sorted_topics) if sorted_topics else "None"

    notes = mem.agent_notes or "Evolving profile in progress."

    return (
        f"User Memory Context:\n"
        f"• Recently Delivered (Past few days): {history_str}\n"
        f"• Frequent Topics Delivered: {fatigue_str}\n"
        f"• Agent Continuity Notes: {notes}"
    )


def record_curated_digest(
    session: Session,
    user_id: uuid.UUID,
    delivered_items: List[Dict[str, Any]],
    agent_note_update: Optional[str] = None,
) -> None:
    """
    Persists newly delivered articles into user memory, increments topic counts,
    and records any new episodic continuity notes from the Agent.
    """
    mem = get_or_create_user_memory(session, user_id)
    history = list(mem.delivered_history or [])
    now_iso = datetime.now().isoformat()

    topics_dict = dict(mem.recent_topics or {})

    for item in delivered_items:
        ext_id = item.get("external_id") or item.get("id")
        title = item.get("title", "")
        if ext_id:
            history.append({
                "external_id": str(ext_id),
                "title": title,
                "delivered_at": now_iso,
            })

        # Track topic distribution
        for t in item.get("topics", []) + item.get("tech_stack", []):
            topics_dict[t] = topics_dict.get(t, 0) + 1

    # Keep at most last 100 delivered entries
    mem.delivered_history = history[-100:]
    mem.recent_topics = topics_dict
    mem.last_curated_at = datetime.now()

    if agent_note_update:
        mem.agent_notes = f"{mem.agent_notes}\n[{now_iso[:10]}] {agent_note_update}".strip()

    session.commit()
    log.info("memory_store.updated", user_id=str(user_id), items_added=len(delivered_items))

