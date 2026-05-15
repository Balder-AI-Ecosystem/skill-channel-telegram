# UPDATE PLAN — skill-channel-telegram

> Audit date: 2026-04-21 | Grade: **B** | Priority: Medium

---

## Vấn đề tìm thấy

### 1. Schemas chưa khai báo properties (CRITICAL)
`telegram_status` và `telegram_voice_note` output schema là `{type: object}` thuần túy.  
`telegram_webhook` và `telegram_voice_note` có `required: [payload]` nhưng không có `properties` cho `payload`.

Từ implementation: fields thực tế là `payload`, `provided_secret`, `state_dir`, `outputs_dir`.

### 2. `state_dir` và `outputs_dir` không được document trong schema
Hai fields runtime này được đọc từ request nhưng không xuất hiện trong schema — caller không biết cần truyền gì.

### 3. Test coverage tối thiểu
Chỉ kiểm tra file manifest tồn tại. Không có test cho:
- Webhook parsing khi `payload` hợp lệ / không hợp lệ
- `provided_secret` validation
- Service error responses

---

## Fix cần làm

### Fix 1 — Cập nhật schemas trong skill.yaml

```yaml
# channel_gateway.telegram_status
input_schema:
  type: object
  additionalProperties: false
output_schema:
  type: object
  properties:
    status:
      type: string
      enum: [ok, error, degraded]
    gateway_name:
      type: string
    connected:
      type: boolean
    last_event_at:
      type: ["string", "null"]
  required: [status]

# channel_gateway.telegram_webhook
input_schema:
  type: object
  required: [payload]
  properties:
    payload:
      type: object
      description: "Raw Telegram webhook JSON as received from Telegram Bot API"
    provided_secret:
      type: ["string", "null"]
      description: "Webhook secret token for validation (X-Telegram-Bot-Api-Secret-Token)"
    state_dir:
      type: string
      description: "Runtime state directory path (injected by core)"
    outputs_dir:
      type: string
      description: "Runtime outputs directory path (injected by core)"
  additionalProperties: false
output_schema:
  type: object
  properties:
    status:
      type: string
      enum: [ok, error, ignored]
    reply_sent:
      type: boolean
    detail:
      type: ["string", "null"]
  required: [status]

# channel_gateway.telegram_voice_note
input_schema:
  type: object
  required: [payload]
  properties:
    payload:
      type: object
      description: "Raw Telegram webhook JSON containing voice note update"
    provided_secret:
      type: ["string", "null"]
    state_dir:
      type: string
    outputs_dir:
      type: string
  additionalProperties: false
output_schema:
  type: object
  properties:
    status:
      type: string
      enum: [ok, error, ignored]
    transcription:
      type: ["string", "null"]
    reply_sent:
      type: boolean
    detail:
      type: ["string", "null"]
  required: [status]
```

### Fix 2 — Thêm functional tests

```python
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
        "capability_id": "channel_gateway.telegram_webhook",
        "parameters": {}  # missing payload
    })
    assert resp.status_code in (400, 422)

def test_health_endpoint_returns_200():
    from fastapi.testclient import TestClient
    from src.skill_channel_telegram_service.app import app
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
```

---

## Không cần làm
- Không cần thay đổi TelegramChannelManager integration
- Không cần thay đổi service mode hoặc port
- Voice note pipeline dependency đã được xử lý đúng
