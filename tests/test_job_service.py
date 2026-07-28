"""Job API tests: submit / status / result (in-memory, no Redis/DB)."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from aivoice_studio.cover.domain.job_record import JobStatus
from aivoice_studio.cover.domain.progress import ProgressEvent
from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.domain.result import CoverResult
from aivoice_studio.cover.domain.stage import Stage
from aivoice_studio.cover.service.cover_service import (
    CoverService,
    JobNotFound,
    ResultNotReady,
)


def _request(**overrides) -> CoverRequest:
    base = dict(
        input_audio=r"D:\songs\demo.mp3",
        model_name="G_16000",
        pitch=0,
        client="test",
    )
    base.update(overrides)
    return CoverRequest(**base)


def _wait_terminal(service: CoverService, job_id: str, timeout: float = 5.0) -> JobStatus:
    deadline = time.time() + timeout
    while time.time() < deadline:
        view = service.status(job_id)
        if view.status.terminal:
            return view.status
        time.sleep(0.02)
    raise TimeoutError(f"job {job_id} did not finish within {timeout}s")


class _SlowOkAdapter:
    def run(self, request, *, job_id=None, on_progress=None, mock_mode=None, uvr_cache_hit_out=None):
        if uvr_cache_hit_out is not None:
            uvr_cache_hit_out.clear()
            uvr_cache_hit_out.append(False)
        time.sleep(0.08)
        if on_progress:
            on_progress(
                ProgressEvent(
                    job_id=job_id or "j",
                    stage=Stage.UVR,
                    percent=10,
                    message="Separating",
                    elapsed_s=0.01,
                )
            )
            on_progress(
                ProgressEvent(
                    job_id=job_id or "j",
                    stage=Stage.DONE,
                    percent=100,
                    message="Done",
                    elapsed_s=0.08,
                )
            )
        return CoverResult(
            success=True,
            job_id=job_id or "j",
            wav_path=r"D:\out\cover.wav",
            mp3_path=r"D:\out\cover.mp3",
            model_name=request.model_name,
            pitch=request.pitch,
        )


class _FailAdapter:
    def run(self, request, *, job_id=None, on_progress=None, mock_mode=None, uvr_cache_hit_out=None):
        if uvr_cache_hit_out is not None:
            uvr_cache_hit_out.clear()
            uvr_cache_hit_out.append(False)
        return CoverResult(success=False, job_id=job_id or "j", error="UVR failed")


class _RaiseAdapter:
    def run(self, request, *, job_id=None, on_progress=None, mock_mode=None, uvr_cache_hit_out=None):
        raise RuntimeError("pipeline boom")


def test_submit_returns_job_id():
    service = CoverService(adapter=_SlowOkAdapter())  # type: ignore[arg-type]
    try:
        job_id = service.submit(_request())
        assert isinstance(job_id, str)
        assert len(job_id) == 12
        view = service.status(job_id)
        assert view.job_id == job_id
        assert view.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.COMPLETED}
    finally:
        service.shutdown(wait=True)


def test_status_transitions_to_completed():
    service = CoverService(adapter=_SlowOkAdapter())  # type: ignore[arg-type]
    try:
        job_id = service.submit(_request())
        seen: list[str] = []
        deadline = time.time() + 5.0
        while time.time() < deadline:
            st = service.status(job_id).status
            if not seen or seen[-1] != st.value:
                seen.append(st.value)
            if st.terminal:
                break
            time.sleep(0.01)
        assert JobStatus.COMPLETED.value in seen
        assert service.status(job_id).status == JobStatus.COMPLETED
        assert service.status(job_id).stage == Stage.DONE
    finally:
        service.shutdown(wait=True)


def test_result_after_completed():
    service = CoverService(adapter=_SlowOkAdapter())  # type: ignore[arg-type]
    try:
        job_id = service.submit(_request())
        assert _wait_terminal(service, job_id) == JobStatus.COMPLETED
        result = service.result(job_id)
        assert result.success is True
        assert result.job_id == job_id
        assert result.wav_path and result.wav_path.endswith("cover.wav")
        assert result.mp3_path and result.mp3_path.endswith("cover.mp3")
    finally:
        service.shutdown(wait=True)


def test_result_not_ready_while_running():
    gate = {"go": False}

    class _BlockedAdapter:
        def run(self, request, *, job_id=None, on_progress=None, mock_mode=None, uvr_cache_hit_out=None):
            while not gate["go"]:
                time.sleep(0.01)
            return CoverResult(success=True, job_id=job_id or "j")

    service = CoverService(adapter=_BlockedAdapter())  # type: ignore[arg-type]
    try:
        job_id = service.submit(_request())
        deadline = time.time() + 2.0
        while time.time() < deadline and service.status(job_id).status == JobStatus.QUEUED:
            time.sleep(0.01)
        with pytest.raises(ResultNotReady):
            service.result(job_id)
    finally:
        gate["go"] = True
        service.shutdown(wait=True)


def test_error_failed_status_and_result():
    service = CoverService(adapter=_FailAdapter())  # type: ignore[arg-type]
    try:
        job_id = service.submit(_request())
        assert _wait_terminal(service, job_id) == JobStatus.FAILED
        view = service.status(job_id)
        assert view.error_message == "UVR failed"
        assert view.stage == Stage.FAILED
        result = service.result(job_id)
        assert result.success is False
        assert result.error == "UVR failed"
    finally:
        service.shutdown(wait=True)


def test_error_exception_becomes_failed():
    service = CoverService(adapter=_RaiseAdapter())  # type: ignore[arg-type]
    try:
        job_id = service.submit(_request())
        assert _wait_terminal(service, job_id) == JobStatus.FAILED
        result = service.result(job_id)
        assert result.success is False
        assert "pipeline boom" in (result.error or "")
    finally:
        service.shutdown(wait=True)


def test_unknown_job_raises():
    service = CoverService(adapter=MagicMock())
    try:
        with pytest.raises(JobNotFound):
            service.status("missingjob01")
        with pytest.raises(JobNotFound):
            service.result("missingjob01")
    finally:
        service.shutdown(wait=False)


def test_sync_run_still_works():
    """GUI path: CoverService.run unchanged."""
    adapter = MagicMock()
    adapter.run.return_value = CoverResult(success=True, job_id="sync")
    service = CoverService(adapter=adapter)
    try:
        result = service.run(_request())
        assert result.success is True
        adapter.run.assert_called_once()
    finally:
        service.shutdown(wait=False)
