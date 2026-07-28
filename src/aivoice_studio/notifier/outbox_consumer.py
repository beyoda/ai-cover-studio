"""Scan jobs/outbox and consume pending notify events (mock-friendly)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aivoice_studio.notifier.feishu_client import FeishuClient, MockFeishuClient
from aivoice_studio.utils.paths import project_root
from aivoice_studio.worker.models import NotifyStatus, utc_now_iso

LOG = logging.getLogger("aivoice.notifier")


def default_jobs_root() -> Path:
    return project_root() / "jobs"


def format_cover_notify_text(
    *,
    song: str | None,
    voice_id: str | None,
    job_id: str,
    finished_at: str | None = None,
    started_at: str | None = None,
    pitch: int | None = None,
) -> str:
    title = (song or "翻唱").strip() or "翻唱"
    voice = (voice_id or "").strip() or "unknown"
    lines = [
        "翻唱完成！",
        "",
        f"🎵 {title}",
        f"🎤 {voice}",
    ]
    if pitch is not None and int(pitch) != 0:
        p = int(pitch)
        lines.append(f"🎚 音高：{'+' if p > 0 else ''}{p}")
    done_line = _format_finished_line(finished_at=finished_at, started_at=started_at)
    if done_line:
        lines.append(done_line)
    lines.extend(
        [
            f"🆔 {job_id}",
            "",
            "文件见附件。",
        ]
    )
    return "\n".join(lines)


def _format_finished_line(
    *, finished_at: str | None, started_at: str | None
) -> str | None:
    from datetime import datetime

    fin = _parse_iso(finished_at)
    if fin is None:
        return None
    stamp = fin.strftime("%Y-%m-%d %H:%M:%S")
    start = _parse_iso(started_at)
    if start is not None:
        secs = max(0, int((fin - start).total_seconds()))
        return f"✅ 完成时间：{stamp}（耗时 {secs}s）"
    return f"✅ 完成时间：{stamp}"


def _parse_iso(value: str | None):
    from datetime import datetime

    if not value or not str(value).strip():
        return None
    try:
        return datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None


def _atomic_write_json(dest: Path, data: dict[str, Any]) -> None:
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


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid outbox json: {path}")
    return data


@dataclass
class ConsumeStats:
    consumed_count: int = 0
    sent_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "consumed_count": self.consumed_count,
            "sent_count": self.sent_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "details": list(self.details),
        }


class OutboxConsumer:
    """Consume Worker outbox notify events via a FeishuClient (mock or real)."""

    def __init__(
        self,
        jobs_root: Path | str | None = None,
        *,
        client: FeishuClient | None = None,
    ) -> None:
        self.jobs_root = Path(jobs_root) if jobs_root else default_jobs_root()
        self.outbox_dir = self.jobs_root / "outbox"
        self.sent_dir = self.outbox_dir / "sent"
        self.skipped_dir = self.outbox_dir / "skipped"
        self.client: FeishuClient = client or MockFeishuClient()
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.sent_dir.mkdir(parents=True, exist_ok=True)
        self.skipped_dir.mkdir(parents=True, exist_ok=True)

    def pending_paths(self) -> list[Path]:
        if not self.outbox_dir.is_dir():
            return []
        files = [
            p
            for p in self.outbox_dir.glob("*.notify.json")
            if p.is_file() and ".sending." not in p.name
        ]
        return sorted(files, key=lambda p: p.stat().st_mtime)

    def _sending_path(self, job_id: str) -> Path:
        return self.outbox_dir / f"{job_id}.sending.json"

    def _sent_path(self, job_id: str) -> Path:
        return self.sent_dir / f"{job_id}.notify.json"

    def _skipped_path(self, job_id: str) -> Path:
        return self.skipped_dir / f"{job_id}.notify.json"

    def _already_terminal(self, job_id: str) -> bool:
        return self._sent_path(job_id).is_file() or self._skipped_path(job_id).is_file()

    def _claim(self, src: Path, job_id: str) -> Path | None:
        dest = self._sending_path(job_id)
        if dest.exists():
            LOG.info("event=claim_skip job_id=%s reason=sending_exists", job_id)
            return None
        try:
            os.replace(str(src), str(dest))
        except OSError as exc:
            LOG.warning("event=claim_failed job_id=%s error=%s", job_id, exc)
            return None
        return dest

    def _mark_sent(self, sending: Path, data: dict[str, Any]) -> Path:
        job_id = str(data.get("job_id") or sending.stem.replace(".sending", ""))
        data = dict(data)
        data["notify_status"] = NotifyStatus.SENT
        data["updated_at"] = utc_now_iso()
        data.pop("error", None)
        data.pop("skip_reason", None)
        dest = self._sent_path(job_id)
        _atomic_write_json(dest, data)
        try:
            sending.unlink(missing_ok=True)  # type: ignore[call-arg]
        except TypeError:
            if sending.exists():
                sending.unlink()
        except OSError:
            pass
        return dest

    def _mark_skipped(self, sending: Path, data: dict[str, Any], reason: str) -> Path:
        job_id = str(data.get("job_id") or "")
        data = dict(data)
        data["notify_status"] = "skipped"
        data["skip_reason"] = reason
        data["updated_at"] = utc_now_iso()
        dest = self._skipped_path(job_id)
        _atomic_write_json(dest, data)
        try:
            sending.unlink(missing_ok=True)  # type: ignore[call-arg]
        except TypeError:
            if sending.exists():
                sending.unlink()
        except OSError:
            pass
        return dest

    def _release_pending(self, sending: Path, data: dict[str, Any], error: str) -> Path:
        """Return to pending notify.json after failure (retry later)."""
        job_id = str(data.get("job_id") or "")
        data = dict(data)
        data["notify_status"] = NotifyStatus.PENDING
        data["retry_count"] = int(data.get("retry_count") or 0) + 1
        data["error"] = error[:300]
        data["updated_at"] = utc_now_iso()
        dest = self.outbox_dir / f"{job_id}.notify.json"
        _atomic_write_json(dest, data)
        try:
            if sending.exists() and sending.resolve() != dest.resolve():
                sending.unlink()
        except OSError:
            pass
        return dest

    def process_event_file(self, path: Path) -> dict[str, Any]:
        """Process one ``*.notify.json`` path. Returns a detail dict."""
        data = _read_json(path)
        job_id = str(data.get("job_id") or path.stem.replace(".notify", ""))
        detail: dict[str, Any] = {"job_id": job_id, "source": str(path)}

        status = str(data.get("notify_status") or NotifyStatus.PENDING).lower()
        if status == NotifyStatus.SENT or self._already_terminal(job_id):
            detail["result"] = "skip_already_sent"
            return detail

        if status == "skipped":
            detail["result"] = "skip_already_skipped"
            return detail

        if status not in (NotifyStatus.PENDING, "failed", ""):
            detail["result"] = f"skip_status_{status}"
            return detail

        claimed = self._claim(path, job_id)
        if claimed is None:
            detail["result"] = "claim_failed"
            return detail

        data = _read_json(claimed)
        data["notify_status"] = "sending"
        data["updated_at"] = utc_now_iso()
        _atomic_write_json(claimed, data)

        chat_id = data.get("feishu_chat_id") or data.get("chat_id")
        if not chat_id or not str(chat_id).strip():
            sid = str(data.get("hermes_session_id") or "").strip()
            if sid.startswith("oc_") or sid.startswith("ou_"):
                chat_id = sid
        if not chat_id or not str(chat_id).strip():
            self._mark_skipped(claimed, data, "missing_chat_id")
            detail["result"] = "skipped"
            detail["skip_reason"] = "missing_chat_id"
            return detail

        chat_id = str(chat_id).strip()
        # Only Feishu oc_/ou_ ids are deliverable for real sends; opaque keys skip.
        if not (chat_id.startswith("oc_") or chat_id.startswith("ou_")):
            self._mark_skipped(claimed, data, "unsupported_receive_id")
            detail["result"] = "skipped"
            detail["skip_reason"] = "unsupported_receive_id"
            return detail

        output = data.get("output_path") or data.get("file_path")
        if not output or not Path(str(output)).is_file():
            self._release_pending(claimed, data, "missing_output_file")
            detail["result"] = "failed"
            detail["error"] = "missing_output_file"
            return detail

        text = format_cover_notify_text(
            song=data.get("song"),
            voice_id=data.get("voice_id") or data.get("voice"),
            job_id=job_id,
            finished_at=data.get("finished_at"),
            started_at=data.get("started_at"),
            pitch=data.get("pitch"),
        )
        try:
            self.client.send_message(chat_id, text)
            self.client.upload_file(chat_id, str(output))
        except Exception as exc:
            LOG.exception("event=send_failed job_id=%s", job_id)
            self._release_pending(claimed, data, str(exc))
            detail["result"] = "failed"
            detail["error"] = str(exc)[:200]
            return detail

        self._mark_sent(claimed, data)
        detail["result"] = "sent"
        detail["chat_id"] = chat_id
        detail["output_path"] = str(output)
        return detail

    def run_once(self) -> ConsumeStats:
        stats = ConsumeStats()
        for path in self.pending_paths():
            stats.consumed_count += 1
            detail = self.process_event_file(path)
            stats.details.append(detail)
            result = detail.get("result")
            if result == "sent":
                stats.sent_count += 1
            elif result in ("skipped", "skip_already_sent", "skip_already_skipped") or str(
                result
            ).startswith("skip_"):
                stats.skipped_count += 1
            elif result == "failed" or result == "claim_failed":
                stats.failed_count += 1
            else:
                stats.skipped_count += 1
        return stats


def consume_once(
    jobs_root: Path | str | None = None,
    *,
    client: FeishuClient | None = None,
) -> ConsumeStats:
    return OutboxConsumer(jobs_root, client=client).run_once()
