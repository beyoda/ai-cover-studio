"""CoverService — sync run + async job API (in-memory queue, no Redis/DB)."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from aivoice_studio.cover.adapter.pipeline_adapter import PipelineAdapter
from aivoice_studio.cover.contracts.protocols import ProgressCallback
from aivoice_studio.cover.domain.job_record import CoverJobRecord, JobStatus, JobStatusView
from aivoice_studio.cover.domain.progress import ProgressEvent
from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.domain.result import CoverResult
from aivoice_studio.cover.domain.stage import Stage
from aivoice_studio.cover.job_store import JobStore
from aivoice_studio.cover.uvr_cache import UvrCache


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


class ResultNotReady(RuntimeError):
    """Raised by result() when the job has not reached a terminal state."""


class JobNotFound(KeyError):
    """Unknown job_id."""


class CoverService:
    """Application entry for GUI / Hermes.

    - ``run()``: synchronous (unchanged contract for GUI)
    - ``submit`` / ``status`` / ``result``: async job API (thread pool size=1)
    """

    def __init__(
        self,
        adapter: PipelineAdapter | None = None,
        *,
        uvr_cache: UvrCache | None = None,
        max_workers: int = 1,
    ) -> None:
        self._uvr_cache = uvr_cache
        self._adapter = adapter or PipelineAdapter(uvr_cache=uvr_cache)
        self._store = JobStore()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="aivoice-job")
        self._futures: dict[str, Future] = {}
        self._lock = threading.RLock()

    def run(
        self,
        request: CoverRequest,
        *,
        job_id: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> CoverResult:
        """Synchronous cover — same contract as P1/P2 (GUI entry).

        Optional ``job_id`` is forwarded to PipelineAdapter so callers (Worker)
        can align ``outputs/{job_id}`` with an external queue id. Omitting it
        preserves prior GUI behavior (Adapter assigns a new id).
        """
        return self._adapter.run(request, job_id=job_id, on_progress=on_progress)

    def submit(self, request: CoverRequest) -> str:
        """Queue a cover job; return job_id immediately."""
        job_id = uuid4().hex[:12]
        record = CoverJobRecord(
            job_id=job_id,
            request=deepcopy(request),
            status=JobStatus.QUEUED,
            stage=Stage.PENDING,
        )
        self._store.put(record)

        def _task() -> None:
            self._execute_job(job_id)

        with self._lock:
            self._futures[job_id] = self._executor.submit(_task)
        return job_id

    def status(self, job_id: str) -> JobStatusView:
        job = self._store.get(job_id)
        if job is None:
            raise JobNotFound(job_id)
        return JobStatusView(
            job_id=job.job_id,
            status=job.status,
            stage=job.stage,
            progress=job.progress,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
            error_message=job.error_message,
            uvr_cache_hit=job.uvr_cache_hit,
        )

    def result(self, job_id: str) -> CoverResult:
        job = self._store.get(job_id)
        if job is None:
            raise JobNotFound(job_id)
        if not job.status.terminal:
            raise ResultNotReady(f"job {job_id} status={job.status.value}")
        if job.result is not None:
            return job.result
        # Cancelled / edge: synthesize failure result
        return CoverResult(
            success=False,
            job_id=job_id,
            error=job.error_message or f"job ended with status={job.status.value}",
        )

    def _execute_job(self, job_id: str) -> None:
        job = self._store.get(job_id)
        if job is None:
            return
        job.status = JobStatus.RUNNING
        job.started_at = _now()
        job.stage = Stage.PENDING
        self._store.update(job)

        hit_flag: list[bool] = []

        def on_progress(event: ProgressEvent) -> None:
            current = self._store.get(job_id)
            if current is None:
                return
            current.progress = event
            current.stage = event.stage
            self._store.update(current)

        try:
            cover_result = self._adapter.run(
                job.request,
                job_id=job_id,
                on_progress=on_progress,
                uvr_cache_hit_out=hit_flag,
            )
            job = self._store.get(job_id) or job
            job.uvr_cache_hit = bool(hit_flag and hit_flag[0])
            job.result = cover_result
            job.finished_at = _now()
            if cover_result.success:
                job.status = JobStatus.COMPLETED
                job.stage = Stage.DONE
                job.error_message = None
            else:
                job.status = JobStatus.FAILED
                job.stage = Stage.FAILED
                job.error_message = cover_result.error
            self._store.update(job)
        except Exception as exc:
            job = self._store.get(job_id) or job
            job.status = JobStatus.FAILED
            job.stage = Stage.FAILED
            job.error_message = str(exc)
            job.finished_at = _now()
            job.result = CoverResult(
                success=False, job_id=job_id, error=str(exc)
            )
            self._store.update(job)

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)
