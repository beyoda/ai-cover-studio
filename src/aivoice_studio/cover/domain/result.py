"""Outbound cover result DTO."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CoverResult:
    success: bool
    job_id: str
    wav_path: str | None = None
    mp3_path: str | None = None
    error: str | None = None
    model_name: str | None = None
    pitch: int | None = None
    reverb: str | None = None
    stages_timing: dict[str, float] | None = field(default=None)
