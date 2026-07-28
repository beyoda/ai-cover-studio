"""Tests for GUI ↔ Cover bridge helpers (no Qt required)."""

from __future__ import annotations

from pathlib import Path

from aivoice_studio.cover.domain.progress import ProgressEvent
from aivoice_studio.cover.domain.stage import Stage
from aivoice_studio.ui.cover_bridge import apply_stage_elapsed, worker_params_to_cover_request


def test_worker_params_to_cover_request_fields():
    req = worker_params_to_cover_request(
        input_audio=Path(r"D:\songs\a.mp3"),
        model_name="G_16000",
        pitch=3,
        reverb="现场",
        accompaniment=r"D:\songs\i.wav",
        f0_method="rmvpe",
        export_mp3=True,
    )
    assert req.input_audio == r"D:\songs\a.mp3"
    assert req.model_name == "G_16000"
    assert req.pitch == 3
    assert req.reverb == "现场"
    assert req.accompaniment == r"D:\songs\i.wav"
    assert req.client == "gui"


def test_apply_stage_elapsed_resets_on_stage_change():
    e1 = ProgressEvent(job_id="j", stage=Stage.UVR, percent=10, message="a", elapsed_s=1.0)
    stage, pct, msg, elapsed, last, t0 = apply_stage_elapsed(
        e1, last_stage="", stage_t0=100.0, now=110.0
    )
    assert stage == "uvr"
    assert pct == 10
    assert msg == "a"
    assert last == "uvr"
    assert t0 == 110.0
    assert elapsed == 0.0

    e2 = ProgressEvent(job_id="j", stage=Stage.UVR, percent=20, message="b", elapsed_s=9.0)
    stage, pct, msg, elapsed, last, t0 = apply_stage_elapsed(
        e2, last_stage=last, stage_t0=t0, now=115.0
    )
    assert stage == "uvr"
    assert elapsed == 5.0
    assert last == "uvr"
    assert t0 == 110.0

    e3 = ProgressEvent(job_id="j", stage=Stage.SVC, percent=45, message="c", elapsed_s=20.0)
    stage, pct, msg, elapsed, last, t0 = apply_stage_elapsed(
        e3, last_stage=last, stage_t0=t0, now=120.0
    )
    assert stage == "svc"
    assert elapsed == 0.0
    assert last == "svc"
    assert t0 == 120.0
