from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_backend_status() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "rakshak-ai-backend"
    assert body["environment"] == "development"
    assert body["phoenix_project_name"] == "rakshak-ai-backend"
    assert body["openai_enabled"] is False
    assert body["openai_model"] == "gpt-5.2"
