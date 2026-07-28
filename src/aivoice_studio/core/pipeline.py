from __future__ import annotations

import logging
import shutil
from pathlib import Path

from aivoice_studio.core.context import JobContext
from aivoice_studio.core.job_manager import JobManager
from aivoice_studio.core.state import JobState
from aivoice_studio.models.results import JobResult, UVRResult
from aivoice_studio.modules.mixer.exporter import Exporter
from aivoice_studio.modules.mixer.ffmpeg_mixer import Mixer
from aivoice_studio.modules.mixer.vocal_effects import VocalEffectsProcessor
from aivoice_studio.modules.svc.svc_runner import SVCService
from aivoice_studio.modules.uvr.separator import UVRService


class Pipeline:
    def __init__(
        self,
        uvr: UVRService,
        svc: SVCService,
        mixer: Mixer,
        exporter: Exporter,
        vocal_fx: VocalEffectsProcessor,
        job_manager: JobManager | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.uvr = uvr
        self.svc = svc
        self.mixer = mixer
        self.exporter = exporter
        self.vocal_fx = vocal_fx
        self.job_manager = job_manager or JobManager()
        self.logger = logger or logging.getLogger("aivoice_studio")

    def run(self, job: JobContext) -> JobResult:
        # --- profiling (observe-only; does not alter business logic) ---
        from aivoice_studio.profiling import get_profiler

        prof = get_profiler()
        result: JobResult | None = None
        prof.begin_session(
            {
                "input_audio": str(job.input_audio),
                "model_name": job.model_name,
                "pitch": job.pitch,
                "reverb": job.reverb,
                "f0_method": job.f0_method,
                "job_id": job.job_id,
                "workdir": str(job.job_workdir),
                "output_dir": str(job.job_output_dir),
                "accompaniment": job.accompaniment,
                "export_mp3": job.export_mp3,
                "started_at": None,
            },
            watch_roots=[job.job_workdir, job.job_output_dir],
        )
        try:
            result = self._run_profiled(job, prof)
            return result
        finally:
            meta = {
                "success": bool(result.success) if result else False,
                "error": (result.error if result else "profiling session ended without result"),
                "wav_path": str(result.wav_path) if result and result.wav_path else "",
                "mp3_path": str(result.mp3_path) if result and result.mp3_path else "",
            }
            try:
                out = prof.end_session(meta)
                if out:
                    self.logger.info("Profiling report written: %s", out)
            except Exception:
                self.logger.exception("Failed to finalize profiling session")

    def _run_profiled(self, job: JobContext, prof) -> JobResult:
        try:
            with prof.stage("Prepare", inputs=[job.input_audio]):
                job.job_workdir.mkdir(parents=True, exist_ok=True)
                job.job_output_dir.mkdir(parents=True, exist_ok=True)
                prof.set_watch_roots([job.job_workdir, job.job_output_dir])

            self.job_manager.update(JobState.UVR, 10, "Separating vocal and instrumental")
            with prof.stage("UVR", inputs=[job.input_audio]):
                if job.skip_uvr and job.cached_vocal and job.cached_instrumental:
                    vocal = Path(job.cached_vocal)
                    instrumental = Path(job.cached_instrumental)
                    if not vocal.is_file() or not instrumental.is_file():
                        return self._fail("UVR cache paths missing")
                    uvr_out = job.job_workdir / "uvr"
                    uvr_out.mkdir(parents=True, exist_ok=True)
                    vocal_dst = uvr_out / vocal.name
                    inst_dst = uvr_out / instrumental.name
                    shutil.copy2(vocal, vocal_dst)
                    shutil.copy2(instrumental, inst_dst)
                    uvr_result = UVRResult(
                        success=True, vocal_path=vocal_dst, instrumental_path=inst_dst
                    )
                    self.logger.info("UVR skipped (cache hit)")
                else:
                    uvr_result = self.uvr.separate(job.input_audio, job.job_workdir / "uvr")
                prof.note_outputs("UVR", [
                    uvr_result.vocal_path if uvr_result else None,
                    uvr_result.instrumental_path if uvr_result else None,
                ])
            if not uvr_result.success or not uvr_result.vocal_path or not uvr_result.instrumental_path:
                return self._fail(uvr_result.error or "UVR failed")

            self.job_manager.update(JobState.SVC, 45, "Running SVC inference")
            with prof.stage("SVC", inputs=[uvr_result.vocal_path]):
                svc_result = self.svc.infer(
                    input_wav=uvr_result.vocal_path,
                    model_name=job.model_name,
                    output_dir=job.job_workdir / "svc",
                    pitch=job.pitch,
                    f0_method=job.f0_method,
                )
                prof.note_outputs("SVC", [svc_result.output_path if svc_result else None])
            if not svc_result.success or not svc_result.output_path:
                return self._fail(svc_result.error or "SVC failed")

            # vocal effects (pitch + reverb) — skip update when no effects
            self.vocal_fx.config.pitch = job.pitch
            self.vocal_fx.config.reverb = job.reverb
            if job.pitch != 0 or job.reverb != "关闭":
                self.job_manager.update(JobState.MIXING, 65, "Applying vocal effects")
            with prof.stage("VocalFX", inputs=[svc_result.output_path]):
                processed_vocal = self.vocal_fx.process(
                    svc_result.output_path, job.job_workdir / "fx"
                )
                prof.note_outputs("VocalFX", [processed_vocal])

            instrumental = Path(job.accompaniment) if job.accompaniment else uvr_result.instrumental_path
            self.job_manager.update(JobState.MIXING, 75, "Mixing generated vocal with instrumental")
            with prof.stage("Mixer", inputs=[processed_vocal, instrumental]):
                mix_result = self.mixer.mix(
                    vocal=processed_vocal,
                    instrumental=instrumental,
                    output_dir=job.job_output_dir,
                )
                prof.note_outputs("Mixer", [mix_result.wav_path if mix_result else None])
            if not mix_result.success or not mix_result.wav_path:
                return self._fail(mix_result.error or "Mixing failed")

            mp3_path = None
            if job.export_mp3:
                self.job_manager.update(JobState.EXPORTING, 90, "Exporting MP3")
                with prof.stage("Export", inputs=[mix_result.wav_path]):
                    export_result = self.exporter.to_mp3(mix_result.wav_path)
                    prof.note_outputs("Export", [
                        export_result.output_path if export_result else None,
                    ])
                if not export_result.success or not export_result.output_path:
                    return self._fail(export_result.error or "MP3 export failed")
                mp3_path = export_result.output_path
            self.job_manager.update(JobState.DONE, 100, "Done")
            return JobResult(success=True, wav_path=mix_result.wav_path, mp3_path=mp3_path)
        except Exception as exc:
            self.logger.exception("Pipeline crashed")
            return self._fail(str(exc))

    def _fail(self, error: str) -> JobResult:
        self.job_manager.update(JobState.FAILED, 100, error)
        self.logger.error(error)
        return JobResult(success=False, error=error)
