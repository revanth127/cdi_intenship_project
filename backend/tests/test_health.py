from fastapi import status
from fastapi.testclient import TestClient


def test_health_check_endpoint(client: TestClient):
    """
    Test GET /health succeeds and returns active database connectivity status.
    """
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "environment" in data


def test_api_v1_health_check_endpoint(client: TestClient):
    """
    Test GET /api/v1/health is also reachable through the versioned router.
    """
    response = client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
