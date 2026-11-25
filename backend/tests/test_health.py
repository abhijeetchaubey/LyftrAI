"""
Unit tests for the /health endpoint.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api.routes import key_manager
from app.config import settings


@pytest.fixture
def client():
    return TestClient(app)


def test_health_success(client, monkeypatch):
    """
    Test /health returns 200 with required structure when conditions are met:
    - >= 2 keys configured
    - cache enabled
    """
    # Configure 2 mock keys
    key_manager.load_keys(["gsk_test_key_1", "gsk_test_key_2"])
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)

    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["keys_configured"] >= 2
    assert data["cache_enabled"] is True


def test_health_insufficient_keys(client):
    """
    Test /health returns 503 when fewer than 2 keys are configured.
    """
    key_manager.load_keys(["only_one_key"])
    response = client.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert "detail" in data


def test_health_cache_disabled(client, monkeypatch):
    """
    Test /health returns 503 when cache is disabled.
    """
    key_manager.load_keys(["gsk_test_key_1", "gsk_test_key_2"])
    monkeypatch.setattr(settings, "CACHE_ENABLED", False)

    response = client.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert "detail" in data
