from fastapi.testclient import TestClient


def test_health_success(client: TestClient, monkeypatch) -> None:
    """Verify health endpoint returns 200 ok when database check passes."""
    monkeypatch.setattr("app.api.v1.health.check_db_connection", lambda: True)

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"


def test_health_degraded(client: TestClient, monkeypatch) -> None:
    """Verify health endpoint returns 503 degraded when database is unavailable."""
    monkeypatch.setattr("app.api.v1.health.check_db_connection", lambda: False)

    response = client.get("/api/v1/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "degraded"
    assert data["database"] == "disconnected"
