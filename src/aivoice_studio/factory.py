from aivoice_studio.core.job_manager import JobManager, ProgressCallback
from aivoice_studio.core.pipeline import Pipeline
from aivoice_studio.modules.mixer.exporter import ExportConfig, Exporter
from aivoice_studio.modules.mixer.ffmpeg_mixer import MixConfig, Mixer
from aivoice_studio.modules.mixer.vocal_effects import VocalEffectsProcessor, VocalFXConfig
from aivoice_studio.modules.svc.svc_runner import SVCConfig, SVCService
from aivoice_studio.modules.uvr.config import UVRConfig
from aivoice_studio.modules.uvr.separator import UVRService
from aivoice_studio.utils.config import ConfigLoader
from aivoice_studio.utils.logging import setup_logging


def build_pipeline(callback: ProgressCallback | None = None, mock_mode: bool | None = None) -> tuple[Pipeline, dict]:
    config = ConfigLoader().load()
    if mock_mode is None:
        mock_mode = bool(config.get("runtime", {}).get("mock_mode", True))
    logger = setup_logging(config.get("runtime", {}).get("log_file", "logs/pipeline.log"))
    uvr_cfg = config.get("uvr", {})
    svc_cfg = config.get("svc", {})
    mix_cfg = config.get("mix", {})
    pipeline = Pipeline(
        uvr=UVRService(UVRConfig(
            command=uvr_cfg.get("command", ""),
            model_name=uvr_cfg.get("model_name", ""),
            vocal_glob=uvr_cfg.get("vocal_glob", "*Vocals*.wav"),
            instrumental_glob=uvr_cfg.get("instrumental_glob", "*Instrumental*.wav"),
            mock_mode=mock_mode,
        ), logger=logger),
        svc=SVCService(SVCConfig(
            python=svc_cfg.get("python", "python"),
            project_dir=svc_cfg.get("project_dir", "tools/so-vits-svc"),
            inference_script=svc_cfg.get("inference_script", "inference_main.py"),
            command=svc_cfg.get("command", ""),
            models_dir=svc_cfg.get("models_dir", "models"),
            mock_mode=mock_mode,
            mode=svc_cfg.get("mode", "standard"),
            model_path=svc_cfg.get("model_path", ""),
            config_path=svc_cfg.get("config_path", ""),
            speaker=svc_cfg.get("speaker", ""),
            output_format=svc_cfg.get("output_format", "wav"),
        ), logger=logger),
        mixer=Mixer(MixConfig(
            ffmpeg_path=mix_cfg.get("ffmpeg_path", "ffmpeg"),
            sample_rate=int(mix_cfg.get("sample_rate", 44100)),
            bitrate=mix_cfg.get("bitrate", "320k"),
            normalize=bool(mix_cfg.get("normalize", True)),
            vocal_volume=float(mix_cfg.get("vocal_volume", 1.0)),
            instrumental_volume=float(mix_cfg.get("instrumental_volume", 0.9)),
            mock_mode=mock_mode,
        ), logger=logger),
        exporter=Exporter(ExportConfig(
            ffmpeg_path=mix_cfg.get("ffmpeg_path", "ffmpeg"),
            bitrate=mix_cfg.get("bitrate", "320k"),
            mock_mode=mock_mode,
        ), logger=logger),
        vocal_fx=VocalEffectsProcessor(VocalFXConfig(
            ffmpeg_path=mix_cfg.get("ffmpeg_path", "ffmpeg"),
            mock_mode=mock_mode,
        ), logger=logger),
        job_manager=JobManager(callback),
        logger=logger,
    )
    return pipeline, config
