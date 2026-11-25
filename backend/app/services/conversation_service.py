"""
Conversation service for multi-turn history, SQLite persistence, and LLM message assembly.
"""
import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.database.models import Message

DEFAULT_SYSTEM_PROMPT = "You are a helpful AI assistant."


class ConversationService:
    """Manages multi-turn conversation state stored in SQLite."""

    @staticmethod
    def session_exists(db: Session, session_id: str) -> bool:
        """Check whether any messages exist for the given session_id."""
        stmt = select(Message.id).where(Message.session_id == session_id).limit(1)
        return db.scalar(stmt) is not None

    @staticmethod
    def get_session_messages(db: Session, session_id: str) -> List[Message]:
        """
        Retrieve all stored messages for a session in chronological order.
        Oldest first.
        """
        stmt = select(Message).where(Message.session_id == session_id).order_by(Message.id.asc())
        return list(db.scalars(stmt).all())

    @staticmethod
    def save_turn(
        db: Session,
        session_id: str,
        user_content: str,
        assistant_content: str,
        assistant_metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[Message, Message]:
        """
        Atomically save user message and assistant reply to SQLite.
        Never save failed requests.
        """
        now_iso = datetime.now(timezone.utc).isoformat()

        user_msg = Message(
            session_id=session_id,
            role="user",
            content=user_content,
            metadata_json=None,
            created_at=now_iso
        )

        metadata_str = json.dumps(assistant_metadata) if assistant_metadata else None
        assistant_msg = Message(
            session_id=session_id,
            role="assistant",
            content=assistant_content,
            metadata_json=metadata_str,
            created_at=now_iso
        )

        db.add(user_msg)
        db.add(assistant_msg)
        db.commit()
        db.refresh(user_msg)
        db.refresh(assistant_msg)

        return user_msg, assistant_msg

    @staticmethod
    def build_llm_messages(
        db: Session,
        session_id: str,
        new_user_message: str,
        system_prompt: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Assemble the full conversation context to send to LiteLLM:
        1. System prompt (overridden or default)
        2. Previous history from SQLite in chronological order
        3. New user message
        """
        messages: List[Dict[str, str]] = []

        # 1. System prompt
        effective_system_prompt = system_prompt if system_prompt and system_prompt.strip() else DEFAULT_SYSTEM_PROMPT
        messages.append({
            "role": "system",
            "content": effective_system_prompt.strip()
        })

        # 2. Historical messages
        history = ConversationService.get_session_messages(db, session_id)
        for msg in history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })

        # 3. New message
        messages.append({
            "role": "user",
            "content": new_user_message.strip()
        })

        return messages
