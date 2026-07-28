"""Cover architecture (GUI entry via CoverService since P2).

GUI ``PipelineWorker`` → ``CoverService`` → ``PipelineAdapter`` → Pipeline.
CLI / Flask may still call ``factory.build_pipeline`` directly until later phases.
"""

from aivoice_studio.cover.domain.job import JobContext
from aivoice_studio.cover.domain.job_record import JobStatus, JobStatusView
from aivoice_studio.cover.domain.progress import ProgressEvent
from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.domain.result import CoverResult
from aivoice_studio.cover.domain.stage import Stage
from aivoice_studio.cover.service.cover_service import CoverService, JobNotFound, ResultNotReady
from aivoice_studio.cover.uvr_cache import UvrCache
from aivoice_studio.cover.voice_registry import (
    VoiceAsset,
    VoiceRegistry,
    get_voice,
    get_voice_registry,
    list_voices,
    validate_voice,
)
from aivoice_studio.cover.voice_request import build_cover_request_for_voice

__all__ = [
    "CoverRequest",
    "CoverResult",
    "CoverService",
    "JobContext",
    "JobNotFound",
    "JobStatus",
    "JobStatusView",
    "ProgressEvent",
    "ResultNotReady",
    "Stage",
    "UvrCache",
    "VoiceAsset",
    "VoiceRegistry",
    "build_cover_request_for_voice",
    "get_voice",
    "get_voice_registry",
    "list_voices",
    "validate_voice",
]
