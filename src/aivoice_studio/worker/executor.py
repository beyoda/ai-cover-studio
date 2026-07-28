"""Execute a claimed FS job via CoverService.run (+ completed outbox event)."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from aivoice_studio.cover.domain.progress import ProgressEvent
from aivoice_studio.cover.service.cover_service import CoverService
from aivoice_studio.cover.voice_request import build_cover_request_for_voice
from aivoice_studio.worker.models import CoverJobRecord, utc_now_iso
from aivoice_studio.worker.outbox import write_completed_outbox_event
from aivoice_studio.worker.queue import FileJobQueue

LOG = logging.getLogger("aivoice.worker")


def _friendly_error(exc: BaseException | str | None) -> str:
    text = str(exc or "翻唱失败").strip().splitlines()[0]
    if "traceback" in text.lower():
        return "翻唱过程出错，请重试。"
    return text[:200] if text else "翻唱失败"


def _stage_value(stage: object) -> str:
    if stage is None:
        return "pending"
    return str(getattr(stage, "value", stage))


def execute_claimed_job(queue: FileJobQueue, job: CoverJobRecord) -> CoverJobRecord:
    """Run cover for an already-claimed job; complete or fail on the FS queue."""
    job_id = job.job_id
    audio = Path(job.input_audio)
    if not audio.is_file():
        LOG.error("event=fail job_id=%s error=missing_input", job_id)
        return queue.fail_job(job_id, error="找不到输入音频文件。")

    opts = dict(job.options or {})
    try:
        request, _asset = build_cover_request_for_voice(
            input_audio=str(audio),
            voice_id=str(job.voice_id),
            pitch=int(job.pitch or 0),
            reverb=str(opts.get("reverb") or "关闭"),
            f0_method=str(opts.get("f0_method") or "rmvpe"),
            export_mp3=bool(opts.get("export_mp3", True)),
            accompaniment=str(opts.get("accompaniment") or ""),
            client="worker",
            request_id=job_id,
        )
    except Exception as exc:
        LOG.exception("event=fail job_id=%s error=voice_resolve", job_id)
        return queue.fail_job(job_id, error=_friendly_error(exc))

    last_write = 0.0
    last_percent = -1

    def on_progress(event: ProgressEvent) -> None:
        nonlocal last_write, last_percent
        stage = _stage_value(event.stage)
        now = time.monotonic()
        percent = int(event.percent)
        # Always write on stage change; throttle percent-only updates.
        should = (
            stage != (job.current_stage or "")
            or percent >= last_percent + 5
            or (now - last_write) >= 2.0
            or percent >= 100
        )
        if not should:
            return
        last_write = now
        last_percent = percent
        job.current_stage = stage
        meta = dict(job.metadata or {})
        meta["last_heartbeat_at"] = utc_now_iso()
        queue.update_job(
            job_id,
            current_stage=stage,
            progress={"percent": percent, "message": str(event.message or "")},
            metadata=meta,
        )
        LOG.info(
            "event=stage job_id=%s stage=%s percent=%s",
            job_id,
            stage,
            percent,
        )

    LOG.info("event=execute_start job_id=%s voice_id=%s", job_id, job.voice_id)
    service = CoverService()
    try:
        result = service.run(request, job_id=job_id, on_progress=on_progress)
    except Exception as exc:
        LOG.exception("event=fail job_id=%s error=run_raised", job_id)
        return queue.fail_job(job_id, error=_friendly_error(exc))

    if result.success:
        output = result.mp3_path or result.wav_path
        if not output or not Path(output).is_file():
            LOG.error("event=fail job_id=%s error=missing_output", job_id)
            return queue.fail_job(job_id, error="完成但缺少输出文件。")
        done = queue.complete_job(job_id, output_path=str(output))
        # Notification event only — never fail the cover if outbox write fails.
        write_completed_outbox_event(queue.root, done)
        LOG.info(
            "event=complete job_id=%s output_path=%s",
            job_id,
            output,
        )
        print(f"complete job {job_id} → {output}", flush=True)
        return done

    failed = queue.fail_job(job_id, error=_friendly_error(result.error))
    LOG.error("event=fail job_id=%s error=%s", job_id, failed.error)
    print(f"fail job {job_id}: {failed.error}", flush=True)
    return failed
