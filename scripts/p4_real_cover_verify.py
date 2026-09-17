"""P4 real cover verification: submit → poll status → result.

Run this only on a machine that has your own rights-cleared audio and model:

    python scripts/p4_real_cover_verify.py --input <your-track.mp3> --model <checkpoint-stem>

No song and no checkpoint ships with this repository, so both arguments are
required and the script exits with a clear message when they are absent.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aivoice_studio.cover.domain.job_record import JobStatus
from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.service.cover_service import CoverService
from aivoice_studio.cover.uvr_cache import UvrCache


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        required=True,
        help="Path to an audio file you are authorized to process",
    )
    parser.add_argument(
        "--model",
        required=True,
        help="SVC checkpoint stem installed under svc.models_dir",
    )
    parser.add_argument("--pitch", type=int, default=0)
    args = parser.parse_args()

    audio = Path(args.input).expanduser()
    if not audio.is_file():
        print(f"MISSING input audio: {audio}")
        return 2

    request = CoverRequest(
        input_audio=str(audio),
        model_name=args.model,
        pitch=args.pitch,
        reverb="关闭",
        f0_method="rmvpe",
        export_mp3=True,
        client="p4_verify",
    )

    service = CoverService()
    t0 = time.perf_counter()
    job_id = service.submit(request)
    print(f"submit ok job_id={job_id}")

    history: list[dict] = []
    last = None
    while True:
        view = service.status(job_id)
        snap = {
            "t": round(time.perf_counter() - t0, 2),
            "status": view.status.value,
            "stage": view.stage.value if view.stage else None,
            "percent": view.progress.percent if view.progress else None,
            "message": view.progress.message if view.progress else None,
            "uvr_cache_hit": view.uvr_cache_hit,
        }
        if snap != last:
            history.append(snap)
            print(
                f"status={snap['status']} stage={snap['stage']} "
                f"pct={snap['percent']} msg={snap['message']}"
            )
            last = snap
        if view.status.terminal:
            break
        if time.perf_counter() - t0 > 600:
            print("TIMEOUT")
            service.shutdown(wait=False)
            return 1
        time.sleep(1.0)

    elapsed = time.perf_counter() - t0
    result = service.result(job_id)
    cache = UvrCache()
    cache_hit = cache.get(audio) is not None

    out = {
        "job_id": job_id,
        "final_status": service.status(job_id).status.value,
        "elapsed_s": round(elapsed, 2),
        "success": result.success,
        "error": result.error,
        "wav_path": result.wav_path,
        "mp3_path": result.mp3_path,
        "uvr_cache_hit_during_job": service.status(job_id).uvr_cache_hit,
        "uvr_cache_populated_after": cache_hit,
        "status_history": history,
    }
    report_path = ROOT / "p4_real_cover_result.json"
    report_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    service.shutdown(wait=True)
    return 0 if result.success and out["final_status"] == JobStatus.COMPLETED.value else 1


if __name__ == "__main__":
    raise SystemExit(main())
