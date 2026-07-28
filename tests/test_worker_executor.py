"""Worker executor with mocked CoverService (no real UVR/SVC)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from aivoice_studio.cover.domain.result import CoverResult
from aivoice_studio.worker.models import JobStatus
from aivoice_studio.worker.queue import FileJobQueue
from aivoice_studio.worker.executor import execute_claimed_job


def test_execute_claimed_job_completes(tmp_path: Path):
    q = FileJobQueue(tmp_path)
    audio = tmp_path / "in.mp3"
    audio.write_bytes(b"ID3x")
    out = tmp_path / "out" / "jid000000001" / "cover.mp3"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"ID3y")

    job = q.enqueue_job(input_audio=str(audio), voice_id="example_voice_b", pitch=0)
    claimed = q.claim_next_job()
    assert claimed is not None

    fake_result = CoverResult(
        success=True,
        job_id=job.job_id,
        mp3_path=str(out),
        wav_path=None,
    )

    with patch("aivoice_studio.worker.executor.CoverService") as CS:
        inst = MagicMock()
        inst.run.return_value = fake_result
        CS.return_value = inst
        with patch(
            "aivoice_studio.worker.executor.build_cover_request_for_voice",
            return_value=(MagicMock(), MagicMock()),
        ):
            done = execute_claimed_job(q, claimed)

    assert done.status == JobStatus.COMPLETED
    assert done.output_path == str(out)
    assert q.job_path(JobStatus.COMPLETED, job.job_id).is_file()
    assert not q.job_path(JobStatus.RUNNING, job.job_id).exists()
    assert inst.run.call_args.kwargs.get("job_id") == job.job_id


def test_execute_missing_input_fails(tmp_path: Path):
    q = FileJobQueue(tmp_path)
    job = q.enqueue_job(
        input_audio=str(tmp_path / "missing.mp3"),
        voice_id="example_voice_b",
    )
    claimed = q.claim_next_job()
    assert claimed is not None
    failed = execute_claimed_job(q, claimed)
    assert failed.status == JobStatus.FAILED
    assert q.job_path(JobStatus.FAILED, job.job_id).is_file()
