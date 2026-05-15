from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


def _is_core_repo(candidate: Path) -> bool:
    return candidate.is_dir() and (candidate / "pyproject.toml").is_file() and (candidate / "ecosystem").is_dir()


def _candidate_core_repos() -> list[Path]:
    current_file = Path(__file__).resolve()
    repo_root = current_file.parents[2]
    candidates: list[Path] = []

    configured = str(os.getenv("AUTOBOT_CORE_REPO", "")).strip()
    if configured:
        candidates.append(Path(configured).expanduser())

    for anchor in (current_file.parent, Path.cwd().resolve()):
        candidates.extend([anchor, *anchor.parents])

    parent_dir = repo_root.parent
    if parent_dir.exists():
        candidates.extend(path for path in parent_dir.iterdir() if path.is_dir())

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        key = str(resolved).lower()
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return unique


def _default_core_repo() -> Path:
    for candidate in _candidate_core_repos():
        if _is_core_repo(candidate):
            return candidate
    raise RuntimeError("Unable to locate the core repo. Set AUTOBOT_CORE_REPO to a valid core repo path.")


def _ensure_core_repo_on_path() -> Path:
    candidate = _default_core_repo()
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
    return candidate


_CORE_REPO = _ensure_core_repo_on_path()

if TYPE_CHECKING:
    from ecosystem.domains.channels.telegram import TelegramChannelManager
    from ecosystem.domains.voice import VoicePipelineModule


class ExecuteRequest(BaseModel):
    capability: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = None
    session_id: str | None = None


class ExecuteResponse(BaseModel):
    task_id: str
    status: str
    detail: str
    capability: str
    module_name: str = "skill-channel-telegram"
    artifacts: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    next_actions: list[str] = Field(default_factory=list)
    failure_category: str | None = None


class _ServiceBackedVoicePipeline:
    def __init__(self, *, state_dir: Path | None = None, outputs_dir: Path | None = None) -> None:
        self.state_dir = state_dir
        self.outputs_dir = outputs_dir
        self._local: VoicePipelineModule | None = None

    def _parameters(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.state_dir is not None:
            payload["state_dir"] = str(self.state_dir)
        if self.outputs_dir is not None:
            payload["outputs_dir"] = str(self.outputs_dir)
        return payload

    def _local_runtime(self) -> "VoicePipelineModule":
        if self._local is None:
            from ecosystem.domains.voice import VoicePipelineModule

            self._local = VoicePipelineModule(state_dir=self.state_dir, outputs_dir=self.outputs_dir)
        return self._local

    def snapshot(self) -> dict[str, Any]:
        from ecosystem.skills import execute_service_skill_sync

        payload = execute_service_skill_sync(
            capability="voice_pipeline.runtime_snapshot",
            parameters=self._parameters(),
            task_id=f"telegram-voice-snapshot-{uuid4().hex}",
        )
        if payload is not None:
            return payload
        return self._local_runtime().snapshot()

    async def transcribe_audio(self, **kwargs: Any) -> dict[str, Any]:
        from ecosystem.skills import execute_service_skill

        parameters = self._parameters()
        parameters.update(kwargs)
        if isinstance(parameters.get("audio_path"), Path):
            parameters["audio_path"] = str(parameters["audio_path"])
        payload = await execute_service_skill(
            capability="voice_pipeline.speech_to_text",
            parameters=parameters,
            task_id=f"telegram-voice-transcribe-{uuid4().hex}",
            session_id=str(kwargs.get("session_id") or "").strip() or None,
        )
        if payload is not None:
            return payload
        return await self._local_runtime().transcribe_audio(**kwargs)


app = FastAPI(title="skill-channel-telegram", version="0.1.0")


def _manager(parameters: dict[str, Any] | None = None) -> "TelegramChannelManager":
    from ecosystem.domains.channels.telegram import TelegramChannelManager

    params = dict(parameters or {})
    state_dir_raw = str(params.get("state_dir") or "").strip()
    outputs_dir_raw = str(params.get("outputs_dir") or "").strip()
    state_dir = Path(state_dir_raw) if state_dir_raw else None
    outputs_dir = Path(outputs_dir_raw) if outputs_dir_raw else None
    return TelegramChannelManager(
        state_dir=state_dir,
        outputs_dir=outputs_dir,
        voice_pipeline=_ServiceBackedVoicePipeline(state_dir=state_dir, outputs_dir=outputs_dir),
    )


def _manifest() -> dict[str, Any]:
    return {
        "name": "skill-channel-telegram",
        "version": "0.1.0",
        "mode": "service",
        "entrypoint": "src.skill_channel_telegram_service.app:app",
        "core_api": ">=1.0,<2.0",
        "service": {
            "base_url": "http://127.0.0.1:8421",
            "execute_path": "/execute",
            "health_path": "/health",
        },
        "capabilities": [
            "channel_gateway.telegram_status",
            "channel_gateway.telegram_webhook",
            "channel_gateway.telegram_voice_note",
        ],
    }


def _task_result(
    *,
    task_id: str,
    capability: str,
    status: str,
    detail: str,
    artifacts: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    next_actions: list[str] | None = None,
    failure_category: str | None = None,
) -> ExecuteResponse:
    return ExecuteResponse(
        task_id=task_id,
        status=status,
        detail=detail,
        capability=capability,
        artifacts=dict(artifacts or {}),
        evidence=dict(evidence or {}),
        next_actions=list(next_actions or []),
        failure_category=failure_category,
    )


@app.get("/health")
def health() -> dict[str, Any]:
    snapshot = _manager().snapshot()
    snapshot["service"] = _manifest()["service"]
    return snapshot


@app.get("/manifest")
def manifest() -> dict[str, Any]:
    return _manifest()


@app.post("/execute")
async def execute(request: ExecuteRequest) -> dict[str, Any]:
    task_id = str(request.task_id or f"skill-channel-telegram-{uuid4().hex}")
    capability = str(request.capability or "").strip()
    parameters = dict(request.parameters or {})
    manager = _manager(parameters)

    if capability == "channel_gateway.telegram_status":
        payload = manager.snapshot()
        return _task_result(
            task_id=task_id,
            capability=capability,
            status="completed",
            detail="Telegram gateway snapshot ready.",
            artifacts={"result": payload},
            evidence={"service_mode": True},
        ).model_dump()

    if capability in {"channel_gateway.telegram_webhook", "channel_gateway.telegram_voice_note"}:
        from ecosystem.runtime.orchestrator import run_turn

        payload = parameters.get("payload") if isinstance(parameters.get("payload"), dict) else None
        if payload is None:
            raise HTTPException(status_code=400, detail=f"{capability} requires payload.")
        provided_secret = str(parameters.get("provided_secret") or "").strip() or None
        if not manager.verify_webhook_secret(provided_secret):
            result = {
                "status": "blocked",
                "detail": "Telegram webhook secret mismatch.",
                "failure_category": "permission_denied",
            }
            return _task_result(
                task_id=task_id,
                capability=capability,
                status="blocked",
                detail=result["detail"],
                artifacts={"result": result},
                evidence={"service_mode": True},
                failure_category="permission_denied",
            ).model_dump()
        webhook_result = await manager.handle_webhook(payload, turn_runner=run_turn)
        return _task_result(
            task_id=task_id,
            capability=capability,
            status=str(webhook_result.get("status") or "failed"),
            detail=str(webhook_result.get("detail") or "Telegram webhook processed."),
            artifacts={"result": webhook_result},
            evidence={"service_mode": True, "session_id": request.session_id},
            next_actions=list(webhook_result.get("next_actions") or []),
            failure_category=str(webhook_result.get("failure_category") or "").strip() or None,
        ).model_dump()

    raise HTTPException(status_code=404, detail=f"Unsupported capability: {capability}")
