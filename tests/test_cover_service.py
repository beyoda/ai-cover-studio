"""Contract tests for CoverService (thin forwarder; no GUI dependency)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from aivoice_studio.cover.domain.progress import ProgressEvent
from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.domain.result import CoverResult
from aivoice_studio.cover.domain.stage import Stage
from aivoice_studio.cover.service.cover_service import CoverService


def _request() -> CoverRequest:
    return CoverRequest(
        input_audio=r"D:\songs\demo.mp3",
        model_name="G_16000",
        pitch=1,
        reverb="关闭",
    )


class TestCoverServiceForwardsToAdapter:
    def test_run_delegates_request_and_returns_adapter_result(self):
        adapter = MagicMock()
        expected = CoverResult(
            success=True,
            job_id="svcjob000001",
            wav_path=r"D:\out\cover.wav",
            mp3_path=r"D:\out\cover.mp3",
            model_name="G_16000",
            pitch=1,
            reverb="关闭",
        )
        adapter.run.return_value = expected
        service = CoverService(adapter=adapter)

        result = service.run(_request())

        assert result is expected
        adapter.run.assert_called_once()
        args, kwargs = adapter.run.call_args
        assert isinstance(args[0], CoverRequest)
        assert args[0].input_audio == r"D:\songs\demo.mp3"
        assert args[0].model_name == "G_16000"
        assert kwargs.get("on_progress") is None

    def test_progress_callback_forwarded_unchanged(self):
        adapter = MagicMock()
        adapter.run.return_value = CoverResult(success=True, job_id="x")
        service = CoverService(adapter=adapter)
        cb = MagicMock()

        service.run(_request(), on_progress=cb)

        _, kwargs = adapter.run.call_args
        assert kwargs["on_progress"] is cb

    def test_adapter_failure_result_not_reinterpreted(self):
        adapter = MagicMock()
        adapter.run.return_value = CoverResult(
            success=False,
            job_id="fail1",
            error="UVR failed",
        )
        service = CoverService(adapter=adapter)

        result = service.run(_request())

        assert result.success is False
        assert result.error == "UVR failed"

    def test_adapter_exception_propagates(self):
        adapter = MagicMock()
        adapter.run.side_effect = RuntimeError("adapter boom")
        service = CoverService(adapter=adapter)

        try:
            service.run(_request())
            raised = False
        except RuntimeError as exc:
            raised = True
            assert "adapter boom" in str(exc)
        assert raised

    def test_no_extra_business_logic_on_success_fields(self):
        """Service must not alter paths or invent fields."""
        adapter = MagicMock()
        adapter.run.return_value = CoverResult(
            success=True,
            job_id="keep",
            wav_path=str(Path("w.wav")),
            mp3_path=str(Path("m.mp3")),
            error=None,
        )
        service = CoverService(adapter=adapter)
        result = service.run(_request())
        assert result.job_id == "keep"
        assert result.wav_path.endswith("w.wav")
        assert result.mp3_path.endswith("m.mp3")
        assert result.error is None


class TestCoverServiceProgressEventShape:
    def test_callback_receives_progress_event_instances_when_adapter_emits(self):
        events: list[ProgressEvent] = []

        class _Adapter:
            def run(self, request, *, job_id=None, on_progress=None, mock_mode=None):
                if on_progress:
                    on_progress(
                        ProgressEvent(
                            job_id="j1",
                            stage=Stage.UVR,
                            percent=10,
                            message="Separating",
                            elapsed_s=0.1,
                        )
                    )
                return CoverResult(success=True, job_id="j1")

        service = CoverService(adapter=_Adapter())  # type: ignore[arg-type]
        service.run(_request(), on_progress=events.append)
        assert len(events) == 1
        assert events[0].stage == Stage.UVR
        assert events[0].percent == 10
