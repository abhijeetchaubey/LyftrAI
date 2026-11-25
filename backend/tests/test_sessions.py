"""
Unit tests for SQLite database, conversation service, and session history endpoint.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.database.models import Base
from app.database.connection import get_db
from app.services.conversation_service import ConversationService
from app.api.routes import key_manager
from app.config import settings

# Test database setup (in-memory SQLite with StaticPool so all connections share the DB)
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    # Ensure health requirements pass
    key_manager.load_keys(["test_key_1", "test_key_2"])
    return TestClient(app)


def test_session_not_found(client):
    """GET /sessions/{session_id}/messages returns 404 for non-existent session."""
    response = client.get("/sessions/unknown-session-999/messages")
    assert response.status_code == 404
    data = response.json()
    assert data["detail"] == "session not found"


def test_save_and_retrieve_messages(client):
    """Verify storing user and assistant messages with metadata and retrieval in order."""
    db = TestingSessionLocal()
    session_id = "test-session-100"

    assistant_meta = {
        "resolution_source": "LIVE_INFERENCE",
        "model": "groq/llama-3.3-70b-versatile",
        "latency_ms": 450,
        "input_tokens": 30,
        "output_tokens": 15,
        "key_id": "key_1",
        "fallback_attempts": 0
    }

    # Save turn
    ConversationService.save_turn(
        db=db,
        session_id=session_id,
        user_content="Hello, AI!",
        assistant_content="Hello! How can I help you?",
        assistant_metadata=assistant_meta
    )

    # Retrieve via API endpoint
    response = client.get(f"/sessions/{session_id}/messages")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == session_id
    messages = data["messages"]
    assert len(messages) == 2

    # Verify user message
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello, AI!"
    assert messages[0]["metadata"] is None

    # Verify assistant message and metadata
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Hello! How can I help you?"
    assert messages[1]["metadata"]["resolution_source"] == "LIVE_INFERENCE"
    assert messages[1]["metadata"]["input_tokens"] == 30
    assert messages[1]["metadata"]["output_tokens"] == 15
    db.close()


def test_session_isolation(client):
    """Verify sessions remain completely isolated from each other."""
    db = TestingSessionLocal()
    ConversationService.save_turn(
        db=db,
        session_id="session-A",
        user_content="Message A",
        assistant_content="Reply A",
        assistant_metadata={"output_tokens": 10}
    )

    ConversationService.save_turn(
        db=db,
        session_id="session-B",
        user_content="Message B",
        assistant_content="Reply B",
        assistant_metadata={"output_tokens": 12}
    )

    # Fetch session A
    res_a = client.get("/sessions/session-A/messages")
    assert res_a.status_code == 200
    msgs_a = res_a.json()["messages"]
    assert len(msgs_a) == 2
    assert msgs_a[0]["content"] == "Message A"

    # Fetch session B
    res_b = client.get("/sessions/session-B/messages")
    assert res_b.status_code == 200
    msgs_b = res_b.json()["messages"]
    assert len(msgs_b) == 2
    assert msgs_b[0]["content"] == "Message B"
    db.close()


def test_build_llm_messages_context():
    """Verify build_llm_messages builds full context without metadata and includes system prompt."""
    db = TestingSessionLocal()
    session_id = "context-session"

    ConversationService.save_turn(
        db=db,
        session_id=session_id,
        user_content="First user question",
        assistant_content="First assistant reply",
        assistant_metadata={"tokens": 10}
    )

    llm_msgs = ConversationService.build_llm_messages(
        db=db,
        session_id=session_id,
        new_user_message="Second user question",
        system_prompt="Custom system prompt"
    )

    # Should contain: system prompt, turn 1 user, turn 1 assistant, turn 2 user
    assert len(llm_msgs) == 4
    assert llm_msgs[0] == {"role": "system", "content": "Custom system prompt"}
    assert llm_msgs[1] == {"role": "user", "content": "First user question"}
    assert llm_msgs[2] == {"role": "assistant", "content": "First assistant reply"}
    assert llm_msgs[3] == {"role": "user", "content": "Second user question"}
    db.close()
