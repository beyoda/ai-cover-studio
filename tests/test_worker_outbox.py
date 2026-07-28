"""Worker completed → outbox notify event (no Feishu)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from aivoice_studio.cover.domain.result import CoverResult
from aivoice_studio.worker.executor import execute_claimed_job
from aivoice_studio.worker.models import JobStatus, NotifyStatus
from aivoice_studio.worker.outbox import (
    outbox_notify_path,
    write_completed_outbox_event,
)
from aivoice_studio.worker.queue import FileJobQueue


def test_complete_writes_outbox(tmp_path: Path):
    q = FileJobQueue(tmp_path)
    audio = tmp_path / "in.mp3"
    audio.write_bytes(b"ID3x")
    job = q.enqueue_job(
        input_audio=str(audio),
        voice_id="example_voice_b",
        hermes_session_id="sess-outbox",
        metadata={"song": "clip30", "voice": "ExampleVoiceB"},
    )
    out = tmp_path / "outputs" / job.job_id / "cover.mp3"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"ID3out" * 100)

    claimed = q.claim_next_job()
    assert claimed is not None
    fake = CoverResult(success=True, job_id=job.job_id, mp3_path=str(out))

    with patch("aivoice_studio.worker.executor.CoverService") as CS:
        inst = MagicMock()
        inst.run.return_value = fake
        CS.return_value = inst
        with patch(
            "aivoice_studio.worker.executor.build_cover_request_for_voice",
            return_value=(MagicMock(), MagicMock()),
        ):
            done = execute_claimed_job(q, claimed)

    assert done.status == JobStatus.COMPLETED
    assert q.job_path(JobStatus.COMPLETED, job.job_id).is_file()
    notify = outbox_notify_path(tmp_path, job.job_id)
    assert notify.is_file()
    payload = json.loads(notify.read_text(encoding="utf-8"))
    assert payload["job_id"] == job.job_id
    assert payload["status"] == "completed"
    assert payload["notify_status"] == NotifyStatus.PENDING
    assert payload["output_path"] == done.output_path == str(out)
    assert payload["song"] == "clip30"
    assert payload["voice_id"] == "example_voice_b"
    assert payload["hermes_session_id"] == "sess-outbox"
    assert payload["feishu_chat_id"] is None
    assert payload["retry_count"] == 0


def test_fail_does_not_write_outbox(tmp_path: Path):
    q = FileJobQueue(tmp_path)
    job = q.enqueue_job(input_audio=str(tmp_path / "missing.mp3"), voice_id="example_voice_b")
    claimed = q.claim_next_job()
    assert claimed is not None
    failed = execute_claimed_job(q, claimed)
    assert failed.status == JobStatus.FAILED
    assert q.job_path(JobStatus.FAILED, job.job_id).is_file()
    assert not outbox_notify_path(tmp_path, job.job_id).exists()


def test_outbox_idempotent_keeps_sent(tmp_path: Path):
    q = FileJobQueue(tmp_path)
    audio = tmp_path / "in.mp3"
    audio.write_bytes(b"ID3x")
    job = q.enqueue_job(input_audio=str(audio), voice_id="example_voice_b")
    claimed = q.claim_next_job()
    assert claimed is not None
    done = q.complete_job(job.job_id, output_path=str(tmp_path / "x.mp3"))
    notify = outbox_notify_path(tmp_path, job.job_id)
    notify.parent.mkdir(parents=True, exist_ok=True)
    notify.write_text(
        json.dumps(
            {
                "job_id": job.job_id,
                "status": "completed",
                "notify_status": NotifyStatus.SENT,
                "output_path": "old",
                "retry_count": 0,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    write_completed_outbox_event(tmp_path, done)
    kept = json.loads(notify.read_text(encoding="utf-8"))
    assert kept["notify_status"] == NotifyStatus.SENT
    assert kept["output_path"] == "old"
