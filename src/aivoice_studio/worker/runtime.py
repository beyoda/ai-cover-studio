"""Worker runtime — claim loop + CoverService execution."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

from aivoice_studio.worker.executor import execute_claimed_job
from aivoice_studio.worker.lock import WorkerLock, WorkerLockError
from aivoice_studio.worker.queue import FileJobQueue, default_jobs_root

LOG = logging.getLogger("aivoice.worker")


class WorkerRuntime:
    """Claim → execute (CoverService.run) → complete/fail → continue.

    Modes:
    - default: resident loop
    - ``--once``: claim and finish at most one job (or idle once) then exit
    - ``--drain``: claim until queue empty then exit
    """

    def __init__(
        self,
        *,
        jobs_root: Path | str | None = None,
        idle_sleep_s: float = 1.5,
        once: bool = False,
        drain: bool = False,
        skip_lock: bool = False,
    ) -> None:
        self.jobs_root = Path(jobs_root) if jobs_root else default_jobs_root()
        self.idle_sleep_s = max(0.2, float(idle_sleep_s))
        self.once = bool(once)
        self.drain = bool(drain)
        self.skip_lock = bool(skip_lock)
        self._stopping = False
        self.queue = FileJobQueue(self.jobs_root)
        self._lock: WorkerLock | None = None

    def request_stop(self, *_args: object) -> None:
        if not self._stopping:
            LOG.info("event=shutdown reason=signal")
        self._stopping = True

    def _setup_signals(self) -> None:
        try:
            signal.signal(signal.SIGINT, self.request_stop)
        except Exception:
            pass
        if hasattr(signal, "SIGTERM"):
            try:
                signal.signal(signal.SIGTERM, self.request_stop)
            except Exception:
                pass

    def run(self) -> int:
        self._setup_signals()
        LOG.info(
            "event=start jobs_root=%s once=%s drain=%s",
            self.jobs_root,
            self.once,
            self.drain,
        )

        if not self.skip_lock:
            self._lock = WorkerLock(self.jobs_root / "worker.lock")
            try:
                self._lock.acquire()
                LOG.info("event=lock acquired pid_file=%s", self.jobs_root / "worker.lock")
            except WorkerLockError as exc:
                LOG.error("event=lock_failed error=%s", exc)
                return 2

        claimed_count = 0
        try:
            while not self._stopping:
                job = self.queue.claim_next_job()
                if job is None:
                    if self.drain:
                        LOG.info("event=exit reason=drain_empty claimed_count=%s", claimed_count)
                        break
                    LOG.debug("event=idle")
                    # Interruptible sleep
                    end = time.time() + self.idle_sleep_s
                    while not self._stopping and time.time() < end:
                        time.sleep(min(0.2, end - time.time()))
                    if self.once:
                        LOG.info("event=exit reason=once_idle")
                        break
                    continue

                claimed_count += 1
                LOG.info(
                    "event=claim job_id=%s status=%s voice_id=%s source=%s",
                    job.job_id,
                    job.status,
                    job.voice_id,
                    job.source,
                )
                print(
                    f"claim job {job.job_id} status={job.status}",
                    flush=True,
                )
                execute_claimed_job(self.queue, job)
                if self.once:
                    LOG.info("event=exit reason=once_done job_id=%s", job.job_id)
                    break
        finally:
            if self._lock is not None:
                self._lock.release()
                LOG.info("event=lock released")
            LOG.info("event=stopped claimed_count=%s", claimed_count)
        return 0


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="AIVOICE cover worker")
    p.add_argument(
        "--jobs-root",
        default=None,
        help="Override jobs/ directory (default: <project>/jobs)",
    )
    p.add_argument("--idle-sleep", type=float, default=1.5, help="Idle poll seconds")
    p.add_argument(
        "--once",
        action="store_true",
        help="Claim and execute at most one job (or idle once) then exit",
    )
    p.add_argument(
        "--drain",
        action="store_true",
        help="Claim and execute until the queue is empty, then exit",
    )
    p.add_argument(
        "--skip-lock",
        action="store_true",
        help="Do not acquire worker.lock (tests only)",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if args.once and args.drain:
        print("error=--once and --drain are mutually exclusive", file=sys.stderr, flush=True)
        return 2
    runtime = WorkerRuntime(
        jobs_root=args.jobs_root,
        idle_sleep_s=args.idle_sleep,
        once=args.once,
        drain=args.drain,
        skip_lock=args.skip_lock,
    )
    return runtime.run()


if __name__ == "__main__":
    raise SystemExit(main())
