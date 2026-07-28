"""GUI cover entry integration (no Qt window): mirrors PipelineWorker → CoverService."""

from __future__ import annotations

import wave
from pathlib import Path
from unittest.mock import MagicMock

from aivoice_studio.cover.adapter.pipeline_adapter import PipelineAdapter
from aivoice_studio.cover.domain.result import CoverResult
from aivoice_studio.cover.service.cover_service import CoverService
from aivoice_studio.ui.cover_bridge import apply_stage_elapsed, worker_params_to_cover_request
from aivoice_studio.ui.main_window import _friendly_error


def _make_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(b"\x00\x00" * 2205)


class _GuiLikeCoverService(CoverService):
    """CoverService used by tests; forces mock_mode like a headless GUI smoke run."""

    def run(self, request, *, on_progress=None):
        return self._adapter.run(request, on_progress=on_progress, mock_mode=True)


def _run_gui_entry_like_worker(
    *,
    input_audio: Path,
    model_name: str = "demo",
    pitch: int = 0,
    reverb: str = "关闭",
    accompaniment: str = "",
    on_progress=None,
    service: CoverService | None = None,
) -> CoverResult:
    """Same composition as PipelineWorker.run after P2 (sans QThread signals)."""
    request = worker_params_to_cover_request(
        input_audio=input_audio,
        model_name=model_name,
        pitch=pitch,
        reverb=reverb,
        accompaniment=accompaniment,
        f0_method="rmvpe",
        export_mp3=True,
    )
    svc = service or _GuiLikeCoverService(adapter=PipelineAdapter())
    return svc.run(request, on_progress=on_progress)


def test_gui_entry_mock_cover_success(tmp_path: Path):
    audio = tmp_path / "in.wav"
    _make_wav(audio)
    events: list[str] = []
    last_stage = ""
    stage_t0 = 0.0

    def on_progress(event):
        nonlocal last_stage, stage_t0
        import time

        stage, _pct, _msg, _elapsed, last_stage, stage_t0 = apply_stage_elapsed(
            event, last_stage=last_stage, stage_t0=stage_t0, now=time.time()
        )
        events.append(stage)

    result = _run_gui_entry_like_worker(input_audio=audio, on_progress=on_progress)

    assert result.success is True
    assert result.mp3_path and Path(result.mp3_path).exists()
    assert result.wav_path and Path(result.wav_path).exists()
    assert "uvr" in events
    assert "svc" in events
    assert "done" in events


def test_gui_entry_failure_maps_to_friendly_error():
    adapter = MagicMock()
    adapter.run.return_value = CoverResult(
        success=False, job_id="x", error="UVR output files were not found"
    )
    service = CoverService(adapter=adapter)
    result = _run_gui_entry_like_worker(
        input_audio=Path(r"D:\missing\a.mp3"),
        service=service,
    )
    assert result.success is False
    friendly = _friendly_error(result.error or "未知错误")
    assert isinstance(friendly, str) and len(friendly) > 0


def test_gui_entry_exception_propagates_for_worker_handlers():
    adapter = MagicMock()
    adapter.run.side_effect = FileNotFoundError("Model not found: x.pth")
    service = CoverService(adapter=adapter)
    try:
        _run_gui_entry_like_worker(input_audio=Path("a.mp3"), service=service)
        raised = False
    except FileNotFoundError:
        raised = True
    assert raised
