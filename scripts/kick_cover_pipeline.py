#!/usr/bin/env python3
"""On-demand cover pipeline: worker --drain then notifier --once --real.

If jobs/worker.lock is held by a live process, exit 0 (that worker will pick up
queued jobs; a later kick after it exits can drain + notify).
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
# Honour the same queue-root override as ``aivoice_studio.worker.queue`` so the
# lock check below inspects the queue the worker will actually use.
_jobs_override = (os.environ.get("AIVOICE_JOBS_DIR") or "").strip()
JOBS = Path(_jobs_override) if _jobs_override else ROOT / "jobs"
LOCK_PATH = JOBS / "worker.lock"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
HERMES_ENV = Path(os.environ.get("LOCALAPPDATA") or "") / "hermes" / ".env"

LOG = logging.getLogger("aivoice.kick")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def lock_held_by_live_worker() -> bool:
    if not LOCK_PATH.is_file():
        return False
    try:
        raw = LOCK_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        # On Windows an exclusive byte-lock often makes read fail — treat as held.
        return True
    if not raw:
        return False
    try:
        data = json.loads(raw)
        pid = int(data.get("pid") or 0)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    return _pid_alive(pid)


def _load_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _python() -> str:
    return str(PY) if PY.is_file() else sys.executable


def _env_for_child() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    # Prefer Hermes Feishu credentials when not already set in this process.
    hermes = _load_dotenv(HERMES_ENV)
    for key in ("FEISHU_APP_ID", "FEISHU_APP_SECRET", "FEISHU_DOMAIN", "FEISHU_BASE_URL"):
        if not env.get(key) and hermes.get(key):
            env[key] = hermes[key]
    return env


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if lock_held_by_live_worker():
        LOG.info("event=skip reason=worker_lock_held path=%s", LOCK_PATH)
        print("kick=skip reason=worker_lock_held", flush=True)
        return 0

    py = _python()
    env = _env_for_child()
    worker_cmd = [py, "-m", "aivoice_studio.worker", "--drain"]
    LOG.info("event=worker_start cmd=%s", " ".join(worker_cmd))
    print("kick=worker_drain start", flush=True)
    worker = subprocess.run(worker_cmd, cwd=str(ROOT), env=env)
    LOG.info("event=worker_done returncode=%s", worker.returncode)
    print(f"kick=worker_drain done code={worker.returncode}", flush=True)

    notifier_cmd = [py, "-m", "aivoice_studio.notifier", "--once", "--real"]
    LOG.info("event=notifier_start cmd=%s", " ".join(notifier_cmd))
    print("kick=notifier start", flush=True)
    try:
        notifier = subprocess.run(notifier_cmd, cwd=str(ROOT), env=env)
    except Exception as exc:
        LOG.warning("event=notifier_failed error=%s", exc)
        print(f"kick=notifier failed error={exc}", flush=True)
        return 0 if worker.returncode == 0 else int(worker.returncode or 1)

    LOG.info("event=notifier_done returncode=%s", notifier.returncode)
    print(f"kick=notifier done code={notifier.returncode}", flush=True)
    # Worker outcome matters most; missing Feishu creds should not fail enqueue kick.
    if worker.returncode != 0:
        return int(worker.returncode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
