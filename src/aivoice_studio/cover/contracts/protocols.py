"""Structural contracts (Protocols) for Cover layer wiring."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from aivoice_studio.cover.domain.progress import ProgressEvent
from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.domain.result import CoverResult

ProgressCallback = Callable[[ProgressEvent], None]


class PipelineAdapterProtocol(Protocol):
    def run(
        self,
        request: CoverRequest,
        *,
        job_id: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> CoverResult: ...


class CoverServiceProtocol(Protocol):
    def run(
        self,
        request: CoverRequest,
        *,
        job_id: str | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> CoverResult: ...
