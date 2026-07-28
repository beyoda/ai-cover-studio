"""Persistent cover job record (filesystem queue JSON)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def default_options() -> dict[str, Any]:
    return {
        "reverb": "关闭",
        "export_mp3": True,
        "f0_method": "rmvpe",
        "accompaniment": "",
    }


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    ALL = (QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED)
    BUCKETS = ALL  # directory names match status


class NotifyStatus:
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class CoverJobRecord:
    """v1.3 job.json model (schema_version=1)."""

    job_id: str
    status: str
    created_at: str
    updated_at: str
    input_audio: str
    voice_id: str
    pitch: int = 0
    options: dict[str, Any] = field(default_factory=default_options)
    output_path: str | None = None
    error: str | None = None
    # optional / contract fields
    source: str | None = None
    provider: str | None = None
    track_id: str | None = None
    requester: str | None = None
    feishu_chat_id: str | None = None
    hermes_session_id: str | None = None
    current_stage: str | None = "pending"
    progress: dict[str, Any] | None = None
    started_at: str | None = None
    finished_at: str | None = None
    notify_status: str = NotifyStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CoverJobRecord:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        payload = {k: v for k, v in data.items() if k in known}
        if "options" not in payload or payload["options"] is None:
            payload["options"] = default_options()
        if "metadata" not in payload or payload["metadata"] is None:
            payload["metadata"] = {}
        return cls(**payload)
