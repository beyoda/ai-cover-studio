#!/usr/bin/env python3
"""Local outbox consumer simulation — read-only, no Feishu.

Prints notify payload fields for future Feishu Notifier input validation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JOBS = ROOT / "jobs"


def _message_from_payload(data: dict) -> str | None:
    if data.get("message"):
        return str(data["message"])
    # Actual 0.4.2-a schema has song/voice_id instead of pre-rendered message.
    song = data.get("song")
    voice = data.get("voice") or data.get("voice_id")
    if song or voice:
        return f"[derived] song={song!s} voice={voice!s}"
    return None


def consume_one(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    output = data.get("output_path") or data.get("file_path")
    mp3_exists = bool(output) and Path(str(output)).is_file()
    chat_id = data.get("chat_id")
    if chat_id is None:
        chat_id = data.get("feishu_chat_id")
    report = {
        "path": str(path),
        "job_id": data.get("job_id"),
        "status": data.get("status"),
        "notify_status": data.get("notify_status"),
        "message": _message_from_payload(data),
        "output_path": output,
        "chat_id": chat_id,
        "mp3_exists": mp3_exists,
        "schema_keys": sorted(data.keys()),
        "has_message_field": "message" in data,
        "has_metadata_field": "metadata" in data,
        "raw": data,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Local outbox consumer (no Feishu)")
    p.add_argument("--jobs-root", type=Path, default=DEFAULT_JOBS)
    p.add_argument("--job-id", default=None, help="Only this job_id")
    args = p.parse_args(argv)

    outbox = Path(args.jobs_root) / "outbox"
    if not outbox.is_dir():
        print(f"OUTBOX MISSING: {outbox}", file=sys.stderr)
        return 2

    files = sorted(outbox.glob("*.notify.json"))
    # Ignore .notify.sent.json (different pattern) — glob *.notify.json matches
    # both foo.notify.json; sent is *.notify.sent.json which also ends with
    # .notify.json? Wait: "x.notify.sent.json".endswith / glob:
    # Path.glob("*.notify.json") matches "a.notify.json" but NOT "a.notify.sent.json"
    # because * is one path segment... actually on Windows glob *.notify.json
    # might match notify.sent.json if pattern is weird. Check: 
    # "709.notify.sent.json" with pattern "*.notify.json" — in pathlib, * does not
    # match dots the same as shell... pathlib PurePath.match: * matches everything
    # except path sep. So "*.notify.json" means ends with .notify.json, and
    # "x.notify.sent.json" ends with ".sent.json" not ".notify.json". Good.

    if args.job_id:
        files = [f for f in files if f.name.startswith(f"{args.job_id}.")]

    if not files:
        print("OUTBOX EMPTY: no *.notify.json", file=sys.stderr)
        return 1

    ok_any = False
    for path in files:
        report = consume_one(path)
        print("OUTBOX EVENT OK")
        print(f"  job_id={report['job_id']}")
        print(f"  status={report['status']}")
        print(f"  notify_status={report['notify_status']}")
        print(f"  message={report['message']}")
        print(f"  output_path={report['output_path']}")
        print(f"  chat_id={report['chat_id']}")
        print(f"  mp3_exists={report['mp3_exists']}")
        print(f"  schema_keys={report['schema_keys']}")
        print(f"  has_message_field={report['has_message_field']}")
        print(f"  has_metadata_field={report['has_metadata_field']}")
        if report["job_id"] and report["output_path"] is not None:
            ok_any = True
        if args.job_id and not report["mp3_exists"]:
            return 3

    return 0 if ok_any else 1


if __name__ == "__main__":
    raise SystemExit(main())
