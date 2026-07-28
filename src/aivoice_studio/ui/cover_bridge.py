"""Pure helpers bridging GUI worker params ↔ Cover DTOs (no Pipeline calls)."""

from __future__ import annotations

from pathlib import Path

from aivoice_studio.cover.domain.progress import ProgressEvent
from aivoice_studio.cover.domain.request import CoverRequest


def worker_params_to_cover_request(
    *,
    input_audio: Path | str,
    model_name: str,
    pitch: int,
    reverb: str = "关闭",
    accompaniment: str = "",
    f0_method: str = "rmvpe",
    export_mp3: bool = True,
) -> CoverRequest:
    """Map PipelineWorker fields (+ config-derived defaults) to CoverRequest."""
    return CoverRequest(
        input_audio=str(input_audio),
        model_name=model_name,
        pitch=pitch,
        reverb=reverb,
        accompaniment=accompaniment or "",
        f0_method=f0_method,
        export_mp3=export_mp3,
        client="gui",
    )


def apply_stage_elapsed(
    event: ProgressEvent,
    *,
    last_stage: str,
    stage_t0: float,
    now: float,
) -> tuple[str, int, str, float, str, float]:
    """Preserve GUI stage-local elapsed timing semantics.

    Returns:
        stage, percent, message, elapsed_s, new_last_stage, new_stage_t0
    """
    stage = event.stage.value if hasattr(event.stage, "value") else str(event.stage)
    new_stage_t0 = stage_t0
    new_last = last_stage
    if stage != last_stage:
        new_stage_t0 = now
        new_last = stage
    elapsed = now - new_stage_t0
    return stage, int(event.percent), str(event.message), elapsed, new_last, new_stage_t0
