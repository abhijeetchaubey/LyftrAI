"""
SQLAlchemy database models.
"""
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import Integer, String, Text, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Message(Base):
    """
    Message model storing conversation history per session.
    Strictly follows the assignment SQLite schema:
    id INTEGER PRIMARY KEY AUTOINCREMENT
    session_id TEXT NOT NULL
    role TEXT NOT NULL -- 'user' or 'assistant'
    content TEXT NOT NULL
    metadata TEXT -- JSON string, assistant messages only
    created_at TEXT NOT NULL -- server time, ISO-8601
    """
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column("metadata", Text, nullable=True)
    created_at: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
        default=lambda: datetime.now(timezone.utc).isoformat()
    )

    __table_args__ = (
        Index("idx_messages_session_id", "session_id"),
        Index("idx_messages_created_at", "created_at"),
    )

    @property
    def parsed_metadata(self) -> Optional[Dict[str, Any]]:
        """Safely parse metadata JSON string into a dictionary."""
        if not self.metadata_json:
            return None
        try:
            return json.loads(self.metadata_json)
        except (json.JSONDecodeError, TypeError):
            return None

    def __repr__(self) -> str:
        return f"<Message id={self.id} session={self.session_id} role={self.role}>"
