#!/usr/bin/env python3
"""Accept Worker claim+execute with mocked cover (queued → completed)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from aivoice_studio.cover.domain.result import CoverResult  # noqa: E402
from aivoice_studio.worker import FileJobQueue, JobStatus, WorkerRuntime  # noqa: E402
from aivoice_studio.worker import executor as executor_mod  # noqa: E402


def main() -> int:
    report: dict = {"ok": False, "steps": []}
    tmp = Path(tempfile.mkdtemp(prefix="aivoice_worker_skel_"))
    try:
        q = FileJobQueue(tmp)
        audio = tmp / "a.mp3"
        audio.write_bytes(b"ID3x")
        job = q.enqueue_job(input_audio=str(audio), voice_id="example_voice", source="skel")
        assert q.job_path(JobStatus.QUEUED, job.job_id).is_file()
        report["steps"].append({"step": "enqueue", "job_id": job.job_id, "ok": True})

        out = tmp / "outputs" / job.job_id / "cover.mp3"
        out.parent.mkdir(parents=True)
        out.write_bytes(b"ID3y")
        fake = CoverResult(success=True, job_id=job.job_id, mp3_path=str(out))

        with patch.object(executor_mod, "CoverService") as CS:
            inst = MagicMock()
            inst.run.return_value = fake
            CS.return_value = inst
            with patch.object(
                executor_mod,
                "build_cover_request_for_voice",
                return_value=(MagicMock(), MagicMock()),
            ):
                rt = WorkerRuntime(jobs_root=tmp, once=True, skip_lock=True, idle_sleep_s=0.2)
                rc = rt.run()

        report["steps"].append(
            {
                "step": "worker_once",
                "returncode": rc,
                "ok": rc == 0,
            }
        )
        assert rc == 0
        assert q.job_path(JobStatus.COMPLETED, job.job_id).is_file()
        assert not q.job_path(JobStatus.QUEUED, job.job_id).exists()
        report["steps"].append({"step": "queued_to_completed", "ok": True})
        report["ok"] = True
    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
