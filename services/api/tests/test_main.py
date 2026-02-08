"""Tests for main API endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


def test_root(client: TestClient) -> None:
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Milestone API"
    assert data["status"] == "running"


def test_health(client: TestClient) -> None:
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "write_mode" in data


def test_mode_readonly_by_default(client: TestClient) -> None:
    """Test that mode is read-only by default."""
    response = client.get("/mode")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "read-only"


def test_scan_status_idle(client: TestClient) -> None:
    """Test scan status endpoint returns idle by default."""
    response = client.get("/scan/status")
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "idle"


def test_drives_list_empty(client: TestClient) -> None:
    """Test drives list when empty."""
    response = client.get("/drives")
    assert response.status_code == 200
    data = response.json()
    assert "drives" in data


def test_roots_list_empty(client: TestClient) -> None:
    """Test roots list when empty."""
    response = client.get("/roots")
    assert response.status_code == 200
    data = response.json()
    assert "roots" in data


def test_files_list_empty(client: TestClient) -> None:
    """Test files list when empty."""
    response = client.get("/files")
    assert response.status_code == 200
    data = response.json()
    assert "files" in data
    assert "total" in data
