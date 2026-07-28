"""Job status enums and views for CoverService async API."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from aivoice_studio.cover.domain.progress import ProgressEvent
from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.domain.result import CoverResult
from aivoice_studio.cover.domain.stage import Stage


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}


@dataclass(slots=True)
class CoverJobRecord:
    job_id: str
    request: CoverRequest
    status: JobStatus = JobStatus.QUEUED
    stage: Stage | None = None
    progress: ProgressEvent | None = None
    result: CoverResult | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    uvr_cache_hit: bool = False


@dataclass(slots=True)
class JobStatusView:
    job_id: str
    status: JobStatus
    stage: Stage | None = None
    progress: ProgressEvent | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    uvr_cache_hit: bool = False
