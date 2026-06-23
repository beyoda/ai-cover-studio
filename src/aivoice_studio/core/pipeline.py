from __future__ import annotations

import logging
from pathlib import Path

from aivoice_studio.core.context import JobContext
from aivoice_studio.core.job_manager import JobManager
from aivoice_studio.core.state import JobState
from aivoice_studio.models.results import JobResult
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
        try:
            job.job_workdir.mkdir(parents=True, exist_ok=True)
            job.job_output_dir.mkdir(parents=True, exist_ok=True)
            self.job_manager.update(JobState.UVR, 10, "Separating vocal and instrumental")
            uvr_result = self.uvr.separate(job.input_audio, job.job_workdir / "uvr")
            if not uvr_result.success or not uvr_result.vocal_path or not uvr_result.instrumental_path:
                return self._fail(uvr_result.error or "UVR failed")
            self.job_manager.update(JobState.SVC, 45, "Running SVC inference")
            svc_result = self.svc.infer(
                input_wav=uvr_result.vocal_path,
                model_name=job.model_name,
                output_dir=job.job_workdir / "svc",
                pitch=job.pitch,
                f0_method=job.f0_method,
            )
            if not svc_result.success or not svc_result.output_path:
                return self._fail(svc_result.error or "SVC failed")

            # vocal effects (pitch + reverb) — skip update when no effects
            self.vocal_fx.config.pitch = job.pitch
            self.vocal_fx.config.reverb = job.reverb
            if job.pitch != 0 or job.reverb != "关闭":
                self.job_manager.update(JobState.MIXING, 65, "Applying vocal effects")
            processed_vocal = self.vocal_fx.process(
                svc_result.output_path, job.job_workdir / "fx"
            )

            instrumental = Path(job.accompaniment) if job.accompaniment else uvr_result.instrumental_path
            self.job_manager.update(JobState.MIXING, 75, "Mixing generated vocal with instrumental")
            mix_result = self.mixer.mix(
                vocal=processed_vocal,
                instrumental=instrumental,
                output_dir=job.job_output_dir,
            )
            if not mix_result.success or not mix_result.wav_path:
                return self._fail(mix_result.error or "Mixing failed")
            mp3_path = None
            if job.export_mp3:
                self.job_manager.update(JobState.EXPORTING, 90, "Exporting MP3")
                export_result = self.exporter.to_mp3(mix_result.wav_path)
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
