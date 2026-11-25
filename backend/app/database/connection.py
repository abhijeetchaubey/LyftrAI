"""
Database connection, session management, and table initialization.
"""
import os
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.database.models import Base


def _normalize_database_url(url: str) -> str:
    """
    Normalize SQLite database URL and ensure the target directory exists.
    Handles relative paths, Docker volume paths (/data/app.db), and Windows paths.
    """
    if url.startswith("sqlite:///"):
        path = url.replace("sqlite:///", "", 1)
        # On Windows, sqlite:////data/app.db might be passed from Docker configs
        if path.startswith("/data/") and os.name == "nt":
            # Running locally on Windows outside Docker, map /data to ./data
            path = "./data/" + path[6:]
            url = f"sqlite:///{path}"

        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
    return url


# Normalize and initialize SQLAlchemy engine
normalized_db_url = _normalize_database_url(settings.DATABASE_URL)
engine = create_engine(
    normalized_db_url,
    connect_args={"check_same_thread": False} if normalized_db_url.startswith("sqlite") else {},
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create database tables and indexes automatically on startup."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields an active database session and ensures clean closure."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database_health() -> bool:
    """Verify database connectivity with a lightweight query."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
