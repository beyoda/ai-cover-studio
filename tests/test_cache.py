"""UVR cache unit tests (filesystem L1 only)."""

from __future__ import annotations

import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

from aivoice_studio.cover.adapter.pipeline_adapter import PipelineAdapter
from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.uvr_cache import UvrCache
from aivoice_studio.core.context import JobContext as PipelineJobContext
from aivoice_studio.models.results import JobResult


def _make_wav(path: Path, frames: int = 1000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(b"\x00\x00" * frames)


def test_cache_miss_then_put_then_hit(tmp_path: Path):
    audio = tmp_path / "song.wav"
    _make_wav(audio)
    vocal = tmp_path / "src_Vocals.wav"
    inst = tmp_path / "src_Instrumental.wav"
    _make_wav(vocal, 500)
    _make_wav(inst, 500)

    cache = UvrCache(root=tmp_path / "uvr_cache", model_name="UVR_MDXNET_Main.onnx")
    assert cache.get(audio) is None

    key = cache.put(audio, vocal, inst)
    assert key
    hit = cache.get(audio)
    assert hit is not None
    assert hit.key == key
    assert hit.vocal_path.is_file()
    assert hit.instrumental_path.is_file()
    assert hit.vocal_path.name == "vocals.wav"
    assert hit.instrumental_path.name == "instrumental.wav"


def test_cache_disabled_never_hits(tmp_path: Path):
    audio = tmp_path / "song.wav"
    _make_wav(audio)
    vocal = tmp_path / "v.wav"
    inst = tmp_path / "i.wav"
    _make_wav(vocal)
    _make_wav(inst)
    cache = UvrCache(root=tmp_path / "c", enabled=False)
    assert cache.put(audio, vocal, inst) is None
    assert cache.get(audio) is None


def test_cache_key_differs_by_model_name(tmp_path: Path):
    audio = tmp_path / "song.wav"
    _make_wav(audio)
    a = UvrCache(root=tmp_path / "c1", model_name="model_a.onnx")
    b = UvrCache(root=tmp_path / "c2", model_name="model_b.onnx")
    assert a.cache_key(audio) != b.cache_key(audio)


def test_adapter_cache_hit_sets_skip_uvr(tmp_path: Path):
    audio = tmp_path / "song.wav"
    _make_wav(audio)
    vocal = tmp_path / "Vocals.wav"
    inst = tmp_path / "Instrumental.wav"
    _make_wav(vocal)
    _make_wav(inst)

    cache = UvrCache(root=tmp_path / "uvr_cache", model_name="UVR_MDXNET_Main.onnx")
    cache.put(audio, vocal, inst)

    captured: dict = {}
    pipeline = MagicMock()
    pipeline.run.side_effect = lambda job: (
        captured.setdefault("job", job),
        JobResult(success=True, wav_path=tmp_path / "out.wav"),
    )[1]

    adapter = PipelineAdapter(uvr_cache=cache)
    req = CoverRequest(
        input_audio=str(audio),
        model_name="G_16000",
        workdir=str(tmp_path / "workdir"),
        output_dir=str(tmp_path / "outputs"),
    )
    hit_flag: list[bool] = []
    with patch(
        "aivoice_studio.cover.adapter.pipeline_adapter.build_pipeline",
        return_value=(
            pipeline,
            {
                "runtime": {"workdir": "workdir", "output_dir": "outputs", "uvr_cache": True},
                "uvr": {"model_name": "UVR_MDXNET_Main.onnx"},
            },
        ),
    ):
        result = adapter.run(req, job_id="cachehit0001", uvr_cache_hit_out=hit_flag)

    assert result.success is True
    assert hit_flag == [True]
    job: PipelineJobContext = captured["job"]
    assert job.skip_uvr is True
    assert Path(job.cached_vocal).is_file()
    assert Path(job.cached_instrumental).is_file()


def test_adapter_stores_uvr_stems_after_miss(tmp_path: Path):
    audio = tmp_path / "song.wav"
    _make_wav(audio)
    workdir = tmp_path / "workdir"
    job_uvr = workdir / "storemiss0001" / "uvr"
    job_uvr.mkdir(parents=True)
    _make_wav(job_uvr / "track_Vocals.wav")
    _make_wav(job_uvr / "track_Instrumental.wav")

    cache = UvrCache(root=tmp_path / "uvr_cache", model_name="UVR_MDXNET_Main.onnx")
    assert cache.get(audio) is None

    pipeline = MagicMock()
    pipeline.run.return_value = JobResult(success=True, wav_path=tmp_path / "out.wav")

    adapter = PipelineAdapter(uvr_cache=cache)
    req = CoverRequest(
        input_audio=str(audio),
        model_name="G_16000",
        workdir=str(workdir),
        output_dir=str(tmp_path / "outputs"),
    )
    with patch(
        "aivoice_studio.cover.adapter.pipeline_adapter.build_pipeline",
        return_value=(
            pipeline,
            {
                "runtime": {"workdir": "workdir", "output_dir": "outputs"},
                "uvr": {"model_name": "UVR_MDXNET_Main.onnx"},
            },
        ),
    ):
        adapter.run(req, job_id="storemiss0001")

    hit = cache.get(audio)
    assert hit is not None
    assert hit.vocal_path.is_file()
