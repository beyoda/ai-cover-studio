"""In-memory job store (no Redis / DB)."""

from __future__ import annotations

import threading
from typing import Iterable

from aivoice_studio.cover.domain.job_record import CoverJobRecord


class JobStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, CoverJobRecord] = {}

    def put(self, job: CoverJobRecord) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def get(self, job_id: str) -> CoverJobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job: CoverJobRecord) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def values(self) -> Iterable[CoverJobRecord]:
        with self._lock:
            return list(self._jobs.values())
