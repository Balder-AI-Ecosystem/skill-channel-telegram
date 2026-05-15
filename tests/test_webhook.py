# tests/test_webhook.py
import json
from unittest.mock import patch, MagicMock

VALID_TELEGRAM_PAYLOAD = {
    "update_id": 123456,
    "message": {
        "message_id": 1,
        "chat": {"id": 111, "type": "private"},
        "from": {"id": 111, "first_name": "Test"},
        "text": "hello"
    }
}

def test_webhook_missing_payload_returns_error():
    # POST /execute without payload field should return 422 or error status
    from fastapi.testclient import TestClient
    from src.skill_channel_telegram_service.app import app
    client = TestClient(app)
    resp = client.post("/execute", json={
        "capability": "channel_gateway.telegram_webhook",
        "parameters": {}  # missing payload
    })
    assert resp.status_code in (400, 422)

def test_health_endpoint_returns_200():
    from fastapi.testclient import TestClient
    from src.skill_channel_telegram_service.app import app
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200

def test_webhook_valid_payload_success():
    from fastapi.testclient import TestClient
    from src.skill_channel_telegram_service.app import app
    from unittest.mock import patch, MagicMock

    with patch("src.skill_channel_telegram_service.app._manager") as mock_manager_func:
        mock_manager = MagicMock()
        mock_manager.verify_webhook_secret.return_value = True
        
        # In Python 3.8+, AsyncMock is available in unittest.mock
        from unittest.mock import AsyncMock
        mock_manager.handle_webhook = AsyncMock(return_value={"status": "completed", "detail": "Success"})
        mock_manager_func.return_value = mock_manager

        client = TestClient(app)
        resp = client.post("/execute", json={
            "capability": "channel_gateway.telegram_webhook",
            "parameters": {
                "payload": VALID_TELEGRAM_PAYLOAD,
                "provided_secret": "my-secret"
            }
        })
        
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["detail"] == "Success"

def test_webhook_invalid_secret_returns_blocked():
    from fastapi.testclient import TestClient
    from src.skill_channel_telegram_service.app import app
    from unittest.mock import patch, MagicMock

    with patch("src.skill_channel_telegram_service.app._manager") as mock_manager_func:
        mock_manager = MagicMock()
        mock_manager.verify_webhook_secret.return_value = False
        mock_manager_func.return_value = mock_manager

        client = TestClient(app)
        resp = client.post("/execute", json={
            "capability": "channel_gateway.telegram_webhook",
            "parameters": {
                "payload": VALID_TELEGRAM_PAYLOAD,
                "provided_secret": "wrong"
            }
        })
        
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "blocked"
        assert data["failure_category"] == "permission_denied"

def test_webhook_service_error_handling():
    from fastapi.testclient import TestClient
    from src.skill_channel_telegram_service.app import app
    from unittest.mock import patch, MagicMock

    with patch("src.skill_channel_telegram_service.app._manager") as mock_manager_func:
        mock_manager = MagicMock()
        mock_manager.verify_webhook_secret.return_value = True
        
        from unittest.mock import AsyncMock
        mock_manager.handle_webhook = AsyncMock(return_value={"status": "failed", "detail": "Internal processing error"})
        mock_manager_func.return_value = mock_manager

        client = TestClient(app)
        resp = client.post("/execute", json={
            "capability": "channel_gateway.telegram_webhook",
            "parameters": {
                "payload": VALID_TELEGRAM_PAYLOAD
            }
        })
        
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["detail"] == "Internal processing error"
