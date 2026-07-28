"""Exclusive worker.lock (pid file + non-blocking byte lock on Windows)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


class WorkerLockError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid
            )
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


class WorkerLock:
    """Hold jobs/worker.lock for the lifetime of the Worker process."""

    def __init__(self, lock_path: Path) -> None:
        self.path = Path(lock_path)
        self._fh = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                raw = self.path.read_text(encoding="utf-8").strip()
                if raw:
                    data = json.loads(raw)
                    old_pid = int(data.get("pid") or 0)
                    if old_pid and old_pid != os.getpid() and _pid_alive(old_pid):
                        raise WorkerLockError(
                            f"another worker is running (pid={old_pid}); lock={self.path}"
                        )
            except (json.JSONDecodeError, TypeError, ValueError):
                pass  # empty/corrupt placeholder from ensure_layout — take over

        # Exclusive-ish: open and lock first byte (Windows); fall back to pid file only.
        self._fh = open(self.path, "a+", encoding="utf-8")
        try:
            if sys.platform == "win32":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            self.release()
            raise WorkerLockError(f"cannot acquire worker.lock: {exc}") from exc

        payload = {
            "pid": os.getpid(),
            "created_at": _now_iso(),
            "host": os.environ.get("COMPUTERNAME") or "",
        }
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())

    def release(self) -> None:
        if self._fh is not None:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    try:
                        self._fh.seek(0)
                        msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                self._fh.close()
            finally:
                self._fh = None
        try:
            if self.path.is_file():
                self.path.unlink()
        except OSError:
            pass

    def __enter__(self) -> WorkerLock:
        self.acquire()
        return self

    def __exit__(self, *args: object) -> None:
        self.release()
