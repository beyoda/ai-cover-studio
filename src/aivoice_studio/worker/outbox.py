"""Write notification outbox events after successful job completion.

No Feishu SDK / API — filesystem event only for a future Notifier.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from aivoice_studio.worker.models import CoverJobRecord, NotifyStatus, utc_now_iso

LOG = logging.getLogger("aivoice.worker")


def outbox_notify_path(jobs_root: Path, job_id: str) -> Path:
    return Path(jobs_root) / "outbox" / f"{job_id}.notify.json"


def outbox_sent_path(jobs_root: Path, job_id: str) -> Path:
    return Path(jobs_root) / "outbox" / f"{job_id}.notify.sent.json"


def _song_from_job(job: CoverJobRecord) -> str | None:
    meta = job.metadata or {}
    song = meta.get("song") or job.source
    if song is None:
        return None
    text = str(song).strip()
    return text or None


def build_completed_outbox_payload(job: CoverJobRecord) -> dict[str, Any]:
    """MVP schema for Notifier (v1.3-0.4.2-a + completion timestamps)."""
    return {
        "job_id": job.job_id,
        "status": "completed",
        "notify_status": NotifyStatus.PENDING,
        "output_path": job.output_path,
        "song": _song_from_job(job),
        "voice_id": job.voice_id,
        "pitch": int(job.pitch or 0),
        "hermes_session_id": job.hermes_session_id,
        "feishu_chat_id": job.feishu_chat_id,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "retry_count": 0,
        "created_at": utc_now_iso(),
    }


def _write_json_atomic(dest: Path, data: dict[str, Any]) -> None:
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


def write_completed_outbox_event(
    jobs_root: Path | str,
    job: CoverJobRecord,
) -> Path | None:
    """Create ``outbox/{job_id}.notify.json`` after ``complete_job`` (idempotent).

    - If pending/sent outbox already exists → keep (do not overwrite).
    - Never calls Feishu.
    - Errors are logged; callers should not fail the cover job.
    """
    root = Path(jobs_root)
    job_id = job.job_id
    dest = outbox_notify_path(root, job_id)
    sent = outbox_sent_path(root, job_id)

    if sent.is_file() or dest.is_file():
        LOG.info(
            "event=outbox_skip job_id=%s reason=already_exists path=%s",
            job_id,
            sent if sent.is_file() else dest,
        )
        return dest if dest.is_file() else sent

    payload = build_completed_outbox_payload(job)
    try:
        _write_json_atomic(dest, payload)
    except Exception:
        LOG.exception("event=outbox_write_failed job_id=%s", job_id)
        return None

    LOG.info("event=outbox_written job_id=%s path=%s", job_id, dest)
    return dest
