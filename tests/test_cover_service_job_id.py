"""CoverService.run forwards optional job_id to Adapter."""

from __future__ import annotations

from unittest.mock import MagicMock

from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.domain.result import CoverResult
from aivoice_studio.cover.service.cover_service import CoverService


def _request() -> CoverRequest:
    return CoverRequest(input_audio=r"D:\songs\a.mp3", voice_id="example_voice", pitch=0)


def test_run_forwards_job_id_to_adapter():
    adapter = MagicMock()
    adapter.run.return_value = CoverResult(success=True, job_id="abc123def456")
    service = CoverService(adapter=adapter)
    service.run(_request(), job_id="abc123def456")
    kwargs = adapter.run.call_args.kwargs
    assert kwargs.get("job_id") == "abc123def456"


def test_run_without_job_id_passes_none():
    adapter = MagicMock()
    adapter.run.return_value = CoverResult(success=True, job_id="generated0001")
    service = CoverService(adapter=adapter)
    service.run(_request())
    assert adapter.run.call_args.kwargs.get("job_id") is None
