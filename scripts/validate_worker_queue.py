#!/usr/bin/env python3
"""Validate filesystem job queue (no CoverService / no real cover)."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aivoice_studio.worker import FileJobQueue, JobStatus  # noqa: E402


def main() -> int:
    report: dict = {"ok": False, "steps": []}
    tmp = Path(tempfile.mkdtemp(prefix="aivoice_jobs_"))
    try:
        q = FileJobQueue(tmp)
        fake_audio = tmp / "sample.mp3"
        fake_audio.write_bytes(b"ID3fake")

        # --- enqueue ---
        job = q.enqueue_job(
            input_audio=str(fake_audio),
            voice_id="example_voice",
            pitch=0,
            source="validate",
        )
        queued_path = q.job_path(JobStatus.QUEUED, job.job_id)
        assert queued_path.is_file(), "queued file missing"
        assert not q.job_path(JobStatus.RUNNING, job.job_id).exists()
        report["steps"].append(
            {"step": "enqueue", "job_id": job.job_id, "path": str(queued_path), "ok": True}
        )

        # --- claim ---
        claimed = q.claim_next_job()
        assert claimed is not None
        assert claimed.job_id == job.job_id
        assert claimed.status == JobStatus.RUNNING
        assert not queued_path.exists(), "queued should disappear after claim"
        running_path = q.job_path(JobStatus.RUNNING, job.job_id)
        assert running_path.is_file(), "running file missing"
        report["steps"].append(
            {
                "step": "claim",
                "job_id": claimed.job_id,
                "status": claimed.status,
                "path": str(running_path),
                "ok": True,
            }
        )

        # --- update ---
        updated = q.update_job(
            job.job_id,
            current_stage="uvr",
            progress={"percent": 30, "message": "人声分离"},
        )
        assert updated.current_stage == "uvr"
        report["steps"].append({"step": "update", "stage": updated.current_stage, "ok": True})

        # --- complete ---
        out = tmp / "cover.mp3"
        out.write_bytes(b"ID3out")
        done = q.complete_job(job.job_id, output_path=str(out))
        assert done.status == JobStatus.COMPLETED
        assert not running_path.exists(), "running should disappear after complete"
        completed_path = q.job_path(JobStatus.COMPLETED, job.job_id)
        assert completed_path.is_file(), "completed file missing"
        report["steps"].append(
            {
                "step": "complete",
                "job_id": done.job_id,
                "output_path": done.output_path,
                "path": str(completed_path),
                "ok": True,
            }
        )

        # --- fail path (second job) ---
        job2 = q.enqueue_job(input_audio=str(fake_audio), voice_id="example_voice_b")
        c2 = q.claim_next_job()
        assert c2 and c2.job_id == job2.job_id
        failed = q.fail_job(job2.job_id, error="simulated failure")
        assert failed.status == JobStatus.FAILED
        assert q.job_path(JobStatus.FAILED, job2.job_id).is_file()
        report["steps"].append({"step": "fail", "job_id": job2.job_id, "ok": True})

        # layout exists
        for name in ("queued", "running", "completed", "failed", "cancelled", "outbox"):
            assert (tmp / name).is_dir()
        assert (tmp / "worker.lock").exists()
        report["steps"].append({"step": "layout", "ok": True})

        report["ok"] = True
        report["jobs_root"] = str(tmp)
    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    finally:
        # keep tmp if failed for debug; else remove
        if report.get("ok"):
            shutil.rmtree(tmp, ignore_errors=True)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
