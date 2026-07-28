"""Notifier mock consumer tests (no Feishu network)."""

from __future__ import annotations

import json
from pathlib import Path

from aivoice_studio.notifier.feishu_client import MockFeishuClient
from aivoice_studio.notifier.outbox_consumer import OutboxConsumer
from aivoice_studio.worker.models import NotifyStatus


def _write_pending(
    outbox: Path,
    *,
    job_id: str,
    chat_id: str | None,
    output_path: Path,
    song: str = "clip30",
    voice_id: str = "example_voice_b",
) -> Path:
    outbox.mkdir(parents=True, exist_ok=True)
    path = outbox / f"{job_id}.notify.json"
    payload = {
        "job_id": job_id,
        "status": "completed",
        "notify_status": NotifyStatus.PENDING,
        "output_path": str(output_path),
        "song": song,
        "voice_id": voice_id,
        "hermes_session_id": "test-sess",
        "feishu_chat_id": chat_id,
        "retry_count": 0,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_pending_consumes_to_sent(tmp_path: Path):
    jobs = tmp_path / "jobs"
    outbox = jobs / "outbox"
    mp3 = tmp_path / "cover.mp3"
    mp3.write_bytes(b"ID3mock" * 20)
    job_id = "aaaaaaaaaaaa"
    _write_pending(outbox, job_id=job_id, chat_id="oc_test_chat", output_path=mp3)

    client = MockFeishuClient()
    stats = OutboxConsumer(jobs, client=client).run_once()

    assert stats.sent_count == 1
    assert client.message_called is True
    assert client.upload_called is True
    assert client.calls[0].chat_id == "oc_test_chat"
    assert "clip30" in (client.calls[0].text or "")
    assert client.calls[1].file_path == str(mp3)

    sent = outbox / "sent" / f"{job_id}.notify.json"
    assert sent.is_file()
    body = json.loads(sent.read_text(encoding="utf-8"))
    assert body["notify_status"] == NotifyStatus.SENT
    assert not (outbox / f"{job_id}.notify.json").exists()
    assert not (outbox / f"{job_id}.sending.json").exists()


def test_sent_is_idempotent(tmp_path: Path):
    jobs = tmp_path / "jobs"
    outbox = jobs / "outbox"
    mp3 = tmp_path / "cover.mp3"
    mp3.write_bytes(b"ID3x")
    job_id = "bbbbbbbbbbbb"
    _write_pending(outbox, job_id=job_id, chat_id="oc_test_chat", output_path=mp3)

    client = MockFeishuClient()
    c = OutboxConsumer(jobs, client=client)
    first = c.run_once()
    assert first.sent_count == 1
    n_calls = len(client.calls)

    # Re-drop a pending file mimicking Worker rewrite — consumer must skip via sent/
    _write_pending(outbox, job_id=job_id, chat_id="oc_test_chat", output_path=mp3)
    second = c.run_once()
    assert second.sent_count == 0
    assert second.skipped_count >= 1
    assert len(client.calls) == n_calls  # no duplicate send


def test_missing_chat_id_skipped(tmp_path: Path):
    jobs = tmp_path / "jobs"
    outbox = jobs / "outbox"
    mp3 = tmp_path / "cover.mp3"
    mp3.write_bytes(b"ID3x")
    job_id = "cccccccccccc"
    _write_pending(outbox, job_id=job_id, chat_id=None, output_path=mp3)

    client = MockFeishuClient()
    stats = OutboxConsumer(jobs, client=client).run_once()

    assert stats.skipped_count == 1
    assert stats.sent_count == 0
    assert client.message_called is False
    assert client.upload_called is False
    skipped = outbox / "skipped" / f"{job_id}.notify.json"
    assert skipped.is_file()
    body = json.loads(skipped.read_text(encoding="utf-8"))
    assert body["notify_status"] == "skipped"
    assert body["skip_reason"] == "missing_chat_id"
