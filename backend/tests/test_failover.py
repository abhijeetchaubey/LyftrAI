"""
Unit tests for API key failover, transient error handling, and 503 exhaustion.
"""
from unittest.mock import patch, MagicMock
import pytest
import litellm
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.database.models import Base
from app.database.connection import get_db
from app.api.routes import key_manager
from app.services.conversation_service import ConversationService

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
    key_manager.load_keys(["mock_key_1", "mock_key_2"])
    return TestClient(app)


def make_mock_litellm_response(content="Successful answer", prompt_tokens=25, completion_tokens=10):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=content))]
    mock_resp.usage = MagicMock(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
    mock_resp.model = "groq/llama-3.3-70b-versatile"
    mock_resp._hidden_params = {}
    return mock_resp


def test_failover_on_http_429(client):
    """
    Test that when key_1 raises RateLimitError (429), the service automatically
    fails over to key_2, returns HTTP 200, key_id='key_2', and fallback_attempts=1.
    """
    rate_limit_err = litellm.RateLimitError(
        message="Rate limit exceeded",
        model="groq/llama-3.3-70b-versatile",
        llm_provider="groq"
    )
    success_resp = make_mock_litellm_response("Answer after failover")

    with patch("litellm.completion", side_effect=[rate_limit_err, success_resp]) as mock_comp:
        response = client.post(
            "/chat",
            json={"session_id": "session-failover-429", "message": "Test failover 429"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == "Answer after failover"
        assert data["metadata"]["key_id"] == "key_2"
        assert data["metadata"]["fallback_attempts"] == 1
        assert data["metadata"]["resolution_source"] == "LIVE_INFERENCE"

        # Verify litellm was called twice: first with mock_key_1, then with mock_key_2
        assert mock_comp.call_count == 2
        assert mock_comp.call_args_list[0][1]["api_key"] == "mock_key_1"
        assert mock_comp.call_args_list[1][1]["api_key"] == "mock_key_2"


def test_failover_on_http_500(client):
    """
    Test that when key_1 raises InternalServerError (500), the service automatically
    fails over to key_2, returns HTTP 200, key_id='key_2', and fallback_attempts=1.
    """
    server_err = litellm.InternalServerError(
        message="Internal server error at provider",
        model="groq/llama-3.3-70b-versatile",
        llm_provider="groq"
    )
    success_resp = make_mock_litellm_response("Answer after 500 failover")

    with patch("litellm.completion", side_effect=[server_err, success_resp]) as mock_comp:
        response = client.post(
            "/chat",
            json={"session_id": "session-failover-500", "message": "Test failover 500"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == "Answer after 500 failover"
        assert data["metadata"]["key_id"] == "key_2"
        assert data["metadata"]["fallback_attempts"] == 1

        assert mock_comp.call_count == 2
        assert mock_comp.call_args_list[0][1]["api_key"] == "mock_key_1"
        assert mock_comp.call_args_list[1][1]["api_key"] == "mock_key_2"


def test_all_keys_failing_returns_503(client):
    """
    Test that when every configured key in the pool fails, the service returns
    HTTP 503 with exact JSON body {"detail": "all providers unavailable"}.
    Also verifies that failed requests are NOT added to SQLite history.
    """
    rate_limit_1 = litellm.RateLimitError("Quota 1", model="m", llm_provider="groq")
    rate_limit_2 = litellm.RateLimitError("Quota 2", model="m", llm_provider="groq")

    with patch("litellm.completion", side_effect=[rate_limit_1, rate_limit_2]) as mock_comp:
        response = client.post(
            "/chat",
            json={"session_id": "exhausted-session", "message": "Will fail"}
        )

        assert response.status_code == 503
        data = response.json()
        assert data == {"detail": "all providers unavailable"}
        assert mock_comp.call_count == 2

    # Verify session was NOT created or stored in SQLite
    db = TestingSessionLocal()
    assert ConversationService.session_exists(db, "exhausted-session") is False
    db.close()

    # History endpoint must return 404 because session does not exist
    history_resp = client.get("/sessions/exhausted-session/messages")
    assert history_resp.status_code == 404


def test_failure_simulation_enabled_failover(client, monkeypatch):
    """
    When ENABLE_FAILURE_SIMULATION=True and X-Simulate-Failure: key_1=429,
    key_1 is simulated as failed and request fails over to key_2.
    """
    monkeypatch.setattr(settings, "ENABLE_FAILURE_SIMULATION", True)
    success_resp = make_mock_litellm_response("Recovered via key_2")

    with patch("litellm.completion", return_value=success_resp) as mock_comp:
        response = client.post(
            "/chat",
            headers={"X-Simulate-Failure": "key_1=429"},
            json={"session_id": "sim-failover-1", "message": "Hello"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == "Recovered via key_2"
        assert data["metadata"]["key_id"] == "key_2"
        assert data["metadata"]["fallback_attempts"] == 1
        mock_comp.assert_called_once()
        assert mock_comp.call_args[1]["api_key"] == "mock_key_2"


def test_failure_simulation_enabled_all_fail(client, monkeypatch):
    """
    When ENABLE_FAILURE_SIMULATION=True and X-Simulate-Failure: *=503 (or key_1=429,key_2=500),
    returns 503 {"detail": "all providers unavailable"} and does not store history.
    """
    monkeypatch.setattr(settings, "ENABLE_FAILURE_SIMULATION", True)

    with patch("litellm.completion") as mock_comp:
        response = client.post(
            "/chat",
            headers={"X-Simulate-Failure": "key_1=429,key_2=500"},
            json={"session_id": "sim-all-fail", "message": "Hello"}
        )

        assert response.status_code == 503
        assert response.json() == {"detail": "all providers unavailable"}
        mock_comp.assert_not_called()

    history_resp = client.get("/sessions/sim-all-fail/messages")
    assert history_resp.status_code == 404


def test_failure_simulation_disabled(client, monkeypatch):
    """
    When ENABLE_FAILURE_SIMULATION=False, X-Simulate-Failure header is ignored
    and key_1 is used normally.
    """
    monkeypatch.setattr(settings, "ENABLE_FAILURE_SIMULATION", False)
    success_resp = make_mock_litellm_response("Normal key_1 response")

    with patch("litellm.completion", return_value=success_resp) as mock_comp:
        response = client.post(
            "/chat",
            headers={"X-Simulate-Failure": "*=429"},
            json={"session_id": "sim-disabled", "message": "Hello"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == "Normal key_1 response"
        assert data["metadata"]["key_id"] == "key_1"
        assert data["metadata"]["fallback_attempts"] == 0
        mock_comp.assert_called_once()
        assert mock_comp.call_args[1]["api_key"] == "mock_key_1"


def test_failover_across_four_keys(client):
    """
    Test sequential failover across 4 configured keys when key_1, key_2, and key_3
    all fail with rate limit errors and key_4 succeeds.
    """
    key_manager.load_keys(["mock_key_1", "mock_key_2", "mock_key_3", "mock_key_4"])
    err = litellm.RateLimitError("Rate limit", model="m", llm_provider="groq")
    success_resp = make_mock_litellm_response("Answer from key_4")

    with patch("litellm.completion", side_effect=[err, err, err, success_resp]) as mock_comp:
        response = client.post(
            "/chat",
            json={"session_id": "session-4-keys", "message": "Test 4 key failover"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["reply"] == "Answer from key_4"
        assert data["metadata"]["key_id"] == "key_4"
        assert data["metadata"]["fallback_attempts"] == 3
        assert mock_comp.call_count == 4
        assert [c[1]["api_key"] for c in mock_comp.call_args_list] == [
            "mock_key_1",
            "mock_key_2",
            "mock_key_3",
            "mock_key_4",
        ]
