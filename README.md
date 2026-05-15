# skill-channel-telegram

Standalone Telegram channel gateway service repo.

## Responsibility

This repo owns the Telegram gateway boundary as a service skill. Core should call it only through the service contract declared in `skill.yaml`.

Capabilities declared in `skill.yaml`:

- `channel_gateway.telegram_status`
- `channel_gateway.telegram_webhook`
- `channel_gateway.telegram_voice_note`

## Contract

- Mode: `service`
- Entrypoint: `src.skill_channel_telegram_service.app:app`
- Healthcheck: `http://127.0.0.1:8421/health`
- Execute endpoint: `http://127.0.0.1:8421/execute`
- Manifest endpoint: `http://127.0.0.1:8421/manifest`
- Core API compatibility: `>=1.0,<2.0`

## Permissions

- `external_actions: true`
- `internet_access: true`
- `file_write: true`
- `read_memory: false`
- `write_memory: true`

## Integration rule

Core integration must stay at the service boundary defined by `skill.yaml`. Core should not host Telegram webhook or auth logic directly once this service is present.
## Verification

- Recommended command: `python -m pytest -q`
- Current minimum coverage: manifest and contract smoke tests inside `tests/`

## Implementation status

This repo already owns the Telegram webhook boundary. Voice-note handling may coordinate with the separate voice-pipeline service, but the gateway contract itself lives here and should remain independent from core internals.

Current dependency note: the service still resolves the core repo location, so implementation independence is not complete yet.
