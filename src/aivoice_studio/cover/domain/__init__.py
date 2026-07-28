"""Domain DTOs for the Cover layer."""

from aivoice_studio.cover.domain.job import JobContext
from aivoice_studio.cover.domain.progress import ProgressEvent
from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.domain.result import CoverResult
from aivoice_studio.cover.domain.stage import Stage

__all__ = [
    "CoverRequest",
    "CoverResult",
    "JobContext",
    "ProgressEvent",
    "Stage",
]
