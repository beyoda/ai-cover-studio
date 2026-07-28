"""Progress callback payload for Cover Service consumers."""

from __future__ import annotations

from dataclasses import dataclass

from aivoice_studio.cover.domain.stage import Stage


@dataclass(slots=True)
class ProgressEvent:
    job_id: str
    stage: Stage
    percent: int
    message: str
    elapsed_s: float | None = None
