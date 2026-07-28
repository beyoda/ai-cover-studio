"""PipelineAdapter — maps Cover DTOs to Pipeline; Voice Registry + UVR cache."""

from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

from aivoice_studio.cover.contracts.protocols import ProgressCallback
from aivoice_studio.cover.domain.progress import ProgressEvent
from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.domain.result import CoverResult
from aivoice_studio.cover.domain.stage import Stage
from aivoice_studio.cover.uvr_cache import UvrCache
from aivoice_studio.cover.voice_resolve import resolve_request_voice
from aivoice_studio.core.context import JobContext as PipelineJobContext
from aivoice_studio.factory import build_pipeline
from aivoice_studio.utils.paths import resolve_path


class PipelineAdapter:
    """Call the existing Pipeline. Resolves voice_id via Registry when present."""

    def __init__(self, uvr_cache: UvrCache | None = None) -> None:
        self._uvr_cache = uvr_cache

    def run(
        self,
        request: CoverRequest,
        *,
        job_id: str | None = None,
        on_progress: ProgressCallback | None = None,
        mock_mode: bool | None = None,
        uvr_cache_hit_out: list | None = None,
    ) -> CoverResult:
        resolved_job_id = job_id or uuid4().hex[:12]
        started = time.perf_counter()
        voice = resolve_request_voice(request)

        def _callback(state, percent: int, message: str) -> None:
            if on_progress is None:
                return
            on_progress(
                ProgressEvent(
                    job_id=resolved_job_id,
                    stage=Stage.from_value(state),
                    percent=int(percent),
                    message=str(message),
                    elapsed_s=time.perf_counter() - started,
                )
            )

        pipeline, config = build_pipeline(_callback, mock_mode=mock_mode)
        # Bind Registry paths via existing SVCConfig fields (no SVC code change)
        if voice.checkpoint_path is not None and voice.config_path is not None:
            pipeline.svc.config.model_path = str(voice.checkpoint_path)
            pipeline.svc.config.config_path = str(voice.config_path)

        runtime = config.get("runtime", {})
        workdir = resolve_path(request.workdir) if request.workdir else resolve_path(
            runtime.get("workdir", "workdir")
        )
        output_dir = resolve_path(request.output_dir) if request.output_dir else resolve_path(
            runtime.get("output_dir", "outputs")
        )

        cache = self._resolve_cache(config, mock_mode=mock_mode)
        input_path = Path(request.input_audio)
        hit = cache.get(input_path) if cache.enabled else None
        if uvr_cache_hit_out is not None:
            uvr_cache_hit_out.clear()
            uvr_cache_hit_out.append(bool(hit))

        pipeline_job = PipelineJobContext(
            input_audio=input_path,
            model_name=voice.model_name,
            pitch=request.pitch,
            f0_method=request.f0_method,
            workdir=workdir,
            output_dir=output_dir,
            export_mp3=request.export_mp3,
            accompaniment=request.accompaniment or "",
            reverb=request.reverb,
            job_id=resolved_job_id,
            skip_uvr=bool(hit),
            cached_vocal=str(hit.vocal_path) if hit else "",
            cached_instrumental=str(hit.instrumental_path) if hit else "",
        )
        result = pipeline.run(pipeline_job)

        if result.success and not hit and cache.enabled:
            self._store_uvr_stems(cache, input_path, pipeline_job.job_workdir / "uvr")

        return CoverResult(
            success=bool(result.success),
            job_id=resolved_job_id,
            wav_path=str(result.wav_path) if result.wav_path else None,
            mp3_path=str(result.mp3_path) if result.mp3_path else None,
            error=result.error,
            model_name=voice.model_name,
            pitch=request.pitch,
            reverb=request.reverb,
        )

    def _resolve_cache(self, config: dict, *, mock_mode: bool | None) -> UvrCache:
        if self._uvr_cache is not None:
            return self._uvr_cache
        uvr_model = config.get("uvr", {}).get("model_name", "UVR_MDXNET_Main.onnx")
        enabled = bool(config.get("runtime", {}).get("uvr_cache", True))
        if mock_mode is True:
            enabled = False
        return UvrCache(enabled=enabled, model_name=str(uvr_model))

    @staticmethod
    def _store_uvr_stems(cache: UvrCache, input_audio: Path, uvr_dir: Path) -> None:
        if not uvr_dir.is_dir():
            return
        vocals = sorted(uvr_dir.glob("*Vocals*.*"))
        insts = sorted(uvr_dir.glob("*Instrumental*.*"))
        if vocals and insts:
            cache.put(input_audio, vocals[0], insts[0])
