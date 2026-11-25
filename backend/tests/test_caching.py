"""
Unit tests for LiteLLM response caching, cache hits, token preservation, and cache misses.
"""
import shutil
import pytest
import litellm
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.database.models import Base
from app.database.connection import get_db
from app.api.routes import key_manager
from app.config import settings
from app.services.cache_service import initialize_cache

TEST_CACHE_DIR = "./data/test_llm_cache"
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
def setup_caching_and_db(monkeypatch):
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db

    # Configure disk cache for test
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)
    monkeypatch.setattr(settings, "CACHE_TYPE", "disk")
    monkeypatch.setattr(settings, "CACHE_DIR", TEST_CACHE_DIR)
    initialize_cache()

    yield

    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.clear()
    litellm.cache = None
    shutil.rmtree(TEST_CACHE_DIR, ignore_errors=True)


@pytest.fixture
def client():
    key_manager.load_keys(["mock_cache_key_1", "mock_cache_key_2"])
    return TestClient(app)


def test_cache_hit_on_identical_prompt_in_different_sessions(client, monkeypatch):
    """
    Test that an identical first message in a new session returns LLM_CACHE,
    with key_id=None, fallback_attempts=0, identical reply, and preserved token counts.
    """
    original_completion = litellm.completion

    def mock_litellm_completion(*args, **kwargs):
        # Default mock response for simulated provider without real API calls
        kwargs.setdefault("mock_response", "The capital of France is Paris.")
        return original_completion(*args, **kwargs)

    monkeypatch.setattr(litellm, "completion", mock_litellm_completion)

    # First request: Session 1
    resp_1 = client.post(
        "/chat",
        json={
            "session_id": "session-cache-1",
            "message": "What is the capital of France?",
            "system_prompt": "You are a geography bot."
        }
    )
    assert resp_1.status_code == 200
    data_1 = resp_1.json()
    assert data_1["reply"] == "The capital of France is Paris."
    meta_1 = data_1["metadata"]
    assert meta_1["resolution_source"] == "LIVE_INFERENCE"
    assert meta_1["key_id"] == "key_1"
    assert meta_1["fallback_attempts"] == 0

    # Second request: Different session, but identical prompt & system prompt
    resp_2 = client.post(
        "/chat",
        json={
            "session_id": "session-cache-2",
            "message": "What is the capital of France?",
            "system_prompt": "You are a geography bot."
        }
    )
    assert resp_2.status_code == 200
    data_2 = resp_2.json()
    assert data_2["reply"] == data_1["reply"]

    meta_2 = data_2["metadata"]
    assert meta_2["resolution_source"] == "LLM_CACHE"
    assert meta_2["key_id"] is None
    assert meta_2["fallback_attempts"] == 0
    assert meta_2["input_tokens"] == meta_1["input_tokens"]
    assert meta_2["output_tokens"] == meta_1["output_tokens"]


def test_cache_miss_for_different_prompts(client, monkeypatch):
    """
    Test that distinct user prompts produce cache misses and execute live inference.
    """
    original_completion = litellm.completion

    def mock_litellm_completion(*args, **kwargs):
        msg = kwargs.get("messages", [{}])[-1].get("content", "")
        kwargs.setdefault("mock_response", f"Answer to: {msg}")
        return original_completion(*args, **kwargs)

    monkeypatch.setattr(litellm, "completion", mock_litellm_completion)

    resp_a = client.post(
        "/chat",
        json={"session_id": "sess-a", "message": "First unique question"}
    )
    assert resp_a.status_code == 200
    assert resp_a.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"

    resp_b = client.post(
        "/chat",
        json={"session_id": "sess-b", "message": "Second unique question"}
    )
    assert resp_b.status_code == 200
    assert resp_b.json()["metadata"]["resolution_source"] == "LIVE_INFERENCE"
