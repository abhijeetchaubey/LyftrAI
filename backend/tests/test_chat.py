"""
Unit tests for POST /chat endpoint, multi-turn memory, and validation.
"""
from unittest.mock import patch, MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.database.models import Base
from app.database.connection import get_db
from app.api.routes import key_manager

# Test database setup (in-memory SQLite with StaticPool)
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
    key_manager.load_keys(["test_key_1", "test_key_2"])
    return TestClient(app)


def make_mock_litellm_response(content="Paris is the capital of France.", prompt_tokens=42, completion_tokens=9):
    mock_resp = MagicMock()
    mock_resp.choices = [
        MagicMock(message=MagicMock(content=content))
    ]
    mock_resp.usage = MagicMock(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    mock_resp.model = "groq/llama-3.3-70b-versatile"
    mock_resp._hidden_params = {}
    return mock_resp


def test_chat_success(client, monkeypatch):
    """Test successful POST /chat response structure, tokens, and metadata."""
    monkeypatch.setattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
    mock_resp = make_mock_litellm_response("Paris is the capital of France.", prompt_tokens=42, completion_tokens=9)

    with patch("litellm.completion", return_value=mock_resp) as mock_complete:
        response = client.post(
            "/chat",
            json={
                "session_id": "test-session-1",
                "message": "What is the capital of France?",
                "system_prompt": "You are a geography bot."
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-1"
        assert data["reply"] == "Paris is the capital of France."
        meta = data["metadata"]
        assert meta["resolution_source"] == "LIVE_INFERENCE"
        assert meta["model"] == "groq/llama-3.3-70b-versatile"
        assert meta["input_tokens"] == 42
        assert meta["output_tokens"] == 9
        assert meta["key_id"] == "key_1"
        assert meta["fallback_attempts"] == 0
        assert meta["latency_ms"] >= 0

        # Verify litellm was called with the right prompt context
        mock_complete.assert_called_once()
        call_kwargs = mock_complete.call_args[1]
        assert call_kwargs["model"] == "groq/llama-3.3-70b-versatile"
        assert call_kwargs["api_key"] == "test_key_1"
        messages = call_kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "You are a geography bot."}
        assert messages[1] == {"role": "user", "content": "What is the capital of France?"}


def test_chat_multi_turn_memory(client):
    """Test that a second chat message retains previous turns in SQLite and sends them in context."""
    mock_resp_1 = make_mock_litellm_response("Nice to meet you, Alice!")
    mock_resp_2 = make_mock_litellm_response("Your name is Alice.")

    with patch("litellm.completion", side_effect=[mock_resp_1, mock_resp_2]) as mock_complete:
        # Turn 1
        client.post(
            "/chat",
            json={"session_id": "alice-session", "message": "My name is Alice."}
        )

        # Turn 2
        client.post(
            "/chat",
            json={"session_id": "alice-session", "message": "What is my name?"}
        )

        # Second call should have 4 messages: system, user 1, assistant 1, user 2
        assert mock_complete.call_count == 2
        second_call_messages = mock_complete.call_args[1]["messages"]
        assert len(second_call_messages) == 4
        assert second_call_messages[0]["role"] == "system"
        assert second_call_messages[1] == {"role": "user", "content": "My name is Alice."}
        assert second_call_messages[2] == {"role": "assistant", "content": "Nice to meet you, Alice!"}
        assert second_call_messages[3] == {"role": "user", "content": "What is my name?"}

    # Verify session history endpoint returns both turns
    history_resp = client.get("/sessions/alice-session/messages")
    assert history_resp.status_code == 200
    msgs = history_resp.json()["messages"]
    assert len(msgs) == 4
    assert msgs[0]["content"] == "My name is Alice."
    assert msgs[1]["content"] == "Nice to meet you, Alice!"
    assert msgs[2]["content"] == "What is my name?"
    assert msgs[3]["content"] == "Your name is Alice."


def test_chat_validation_empty_message(client):
    """Test 422 returned when message is empty or whitespace."""
    response = client.post(
        "/chat",
        json={"session_id": "s-123", "message": "   "}
    )
    assert response.status_code == 422
    assert "detail" in response.json()


def test_chat_validation_long_message(client):
    """Test 422 returned when message exceeds 4000 characters."""
    response = client.post(
        "/chat",
        json={"session_id": "s-123", "message": "x" * 4001}
    )
    assert response.status_code == 422
    assert "detail" in response.json()


def test_chat_validation_invalid_session_id(client):
    """Test 422 returned when session_id is empty."""
    response = client.post(
        "/chat",
        json={"session_id": "   ", "message": "Hello"}
    )
    assert response.status_code == 422
    assert "detail" in response.json()
