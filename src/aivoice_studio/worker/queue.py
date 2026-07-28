"""Filesystem job queue: enqueue / claim / update / complete / fail."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from aivoice_studio.utils.paths import project_root
from aivoice_studio.worker.models import (
    CoverJobRecord,
    JobStatus,
    NotifyStatus,
    default_options,
    utc_now_iso,
)


class JobQueueError(RuntimeError):
    """Filesystem queue protocol error."""


def default_jobs_root() -> Path:
    return project_root() / "jobs"


class FileJobQueue:
    """Persistent FS queue per aivoice_v1.3_worker_interface_contract.md."""

    BUCKETS = JobStatus.BUCKETS

    def __init__(self, jobs_root: Path | str | None = None) -> None:
        self.root = Path(jobs_root) if jobs_root else default_jobs_root()
        self.ensure_layout()

    def ensure_layout(self) -> None:
        for name in (*self.BUCKETS, "outbox"):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        lock = self.root / "worker.lock"
        if not lock.exists():
            # Placeholder empty file so tree matches contract; real lock acquired by Worker later.
            lock.write_text("", encoding="utf-8")

    def bucket_dir(self, status: str) -> Path:
        if status not in self.BUCKETS:
            raise JobQueueError(f"unknown bucket/status: {status!r}")
        return self.root / status

    def job_path(self, status: str, job_id: str) -> Path:
        return self.bucket_dir(status) / f"{job_id}.json"

    def find_job_path(self, job_id: str) -> Path | None:
        for status in self.BUCKETS:
            path = self.job_path(status, job_id)
            if path.is_file():
                return path
        return None

    def _write_json_atomic(self, dest: Path, data: dict[str, Any]) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{dest.stem}.",
            suffix=".tmp",
            dir=str(dest.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, dest)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _read_job(self, path: Path) -> CoverJobRecord:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise JobQueueError(f"invalid job json: {path}")
        return CoverJobRecord.from_dict(data)

    def enqueue_job(
        self,
        *,
        input_audio: str,
        voice_id: str,
        pitch: int = 0,
        options: dict[str, Any] | None = None,
        source: str | None = None,
        provider: str | None = None,
        track_id: str | None = None,
        requester: str | None = None,
        feishu_chat_id: str | None = None,
        hermes_session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        job_id: str | None = None,
    ) -> CoverJobRecord:
        """Create job JSON via temp file, atomic rename into queued/."""
        self.ensure_layout()
        jid = (job_id or uuid4().hex[:12]).strip()
        if len(jid) != 12:
            raise JobQueueError("job_id must be 12 characters")
        if self.find_job_path(jid) is not None:
            raise JobQueueError(f"job_id already exists: {jid}")

        audio = str(input_audio or "").strip()
        vid = str(voice_id or "").strip()
        if not audio:
            raise JobQueueError("input_audio is required")
        if not vid:
            raise JobQueueError("voice_id is required")

        now = utc_now_iso()
        opts = dict(default_options())
        if options:
            opts.update(options)

        notify = NotifyStatus.PENDING if feishu_chat_id else NotifyStatus.SKIPPED
        job = CoverJobRecord(
            job_id=jid,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
            input_audio=audio,
            voice_id=vid,
            pitch=int(pitch),
            options=opts,
            source=source,
            provider=provider,
            track_id=track_id,
            requester=requester,
            feishu_chat_id=feishu_chat_id,
            hermes_session_id=hermes_session_id,
            current_stage="pending",
            notify_status=notify,
            metadata=dict(metadata or {}),
        )
        dest = self.job_path(JobStatus.QUEUED, jid)
        self._write_json_atomic(dest, job.to_dict())
        return job

    def claim_next_job(self) -> CoverJobRecord | None:
        """Scan queued/ (oldest first), rename into running/, return job."""
        self.ensure_layout()
        queued = self.bucket_dir(JobStatus.QUEUED)
        candidates = sorted(queued.glob("*.json"), key=lambda p: p.stat().st_mtime)
        for src in candidates:
            if src.name.startswith("."):
                continue
            job_id = src.stem
            dest = self.job_path(JobStatus.RUNNING, job_id)
            try:
                os.replace(str(src), str(dest))
            except OSError:
                # Lost race or file vanished — try next
                continue
            job = self._read_job(dest)
            now = utc_now_iso()
            job.status = JobStatus.RUNNING
            job.started_at = now
            job.updated_at = now
            job.current_stage = job.current_stage or "pending"
            self._write_json_atomic(dest, job.to_dict())
            return job
        return None

    def update_job(
        self,
        job_id: str,
        mutator: Callable[[CoverJobRecord], None] | None = None,
        **fields: Any,
    ) -> CoverJobRecord:
        """Update job JSON in its current bucket (does not move buckets)."""
        path = self.find_job_path(job_id)
        if path is None:
            raise JobQueueError(f"job not found: {job_id}")
        job = self._read_job(path)
        if mutator:
            mutator(job)
        for key, value in fields.items():
            if not hasattr(job, key):
                raise JobQueueError(f"unknown field: {key}")
            setattr(job, key, value)
        job.updated_at = utc_now_iso()
        self._write_json_atomic(path, job.to_dict())
        return job

    def _finalize(
        self,
        job_id: str,
        *,
        target_status: str,
        output_path: str | None = None,
        error: str | None = None,
        current_stage: str | None = None,
    ) -> CoverJobRecord:
        src = self.find_job_path(job_id)
        if src is None:
            raise JobQueueError(f"job not found: {job_id}")
        job = self._read_job(src)
        if job.status not in (JobStatus.RUNNING, JobStatus.QUEUED):
            raise JobQueueError(
                f"cannot move job {job_id} from status={job.status} to {target_status}"
            )
        now = utc_now_iso()
        job.status = target_status
        job.finished_at = now
        job.updated_at = now
        if output_path is not None:
            job.output_path = output_path
        if error is not None:
            job.error = error
        if current_stage is not None:
            job.current_stage = current_stage
        elif target_status == JobStatus.COMPLETED:
            job.current_stage = "done"
        elif target_status == JobStatus.FAILED:
            job.current_stage = "failed"

        dest = self.job_path(target_status, job_id)
        # Write updated content to temp in dest dir, then replace after move
        if src.resolve() != dest.resolve():
            # Move first (atomic claim of terminal bucket name), then rewrite body
            os.replace(str(src), str(dest))
        self._write_json_atomic(dest, job.to_dict())
        return job

    def complete_job(self, job_id: str, *, output_path: str) -> CoverJobRecord:
        if not str(output_path or "").strip():
            raise JobQueueError("output_path is required to complete a job")
        return self._finalize(
            job_id,
            target_status=JobStatus.COMPLETED,
            output_path=str(output_path),
            error=None,
            current_stage="done",
        )

    def fail_job(self, job_id: str, *, error: str) -> CoverJobRecord:
        msg = str(error or "").strip() or "unknown error"
        return self._finalize(
            job_id,
            target_status=JobStatus.FAILED,
            error=msg,
            current_stage="failed",
        )
