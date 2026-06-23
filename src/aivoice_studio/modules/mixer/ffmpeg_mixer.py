from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from aivoice_studio.models.results import MixResult
from aivoice_studio.utils.process import ProcessError, run_command


@dataclass(slots=True)
class MixConfig:
    ffmpeg_path: str = "ffmpeg"
    sample_rate: int = 44100
    bitrate: str = "320k"
    normalize: bool = True
    vocal_volume: float = 1.0
    instrumental_volume: float = 0.9
    mock_mode: bool = True


class Mixer:
    def __init__(self, config: MixConfig, logger: logging.Logger | None = None) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("aivoice_studio")

    def mix(self, vocal: Path, instrumental: Path, output_dir: Path) -> MixResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        if not vocal.exists() or not instrumental.exists():
            return MixResult(success=False, error="Mix input files are missing")
        output = output_dir / "cover.wav"
        if self.config.mock_mode:
            shutil.copy2(vocal, output)
            return MixResult(success=True, wav_path=output)
        command = [
            self.config.ffmpeg_path,
            "-y",
            "-i", str(vocal),
            "-i", str(instrumental),
            "-filter_complex",
            f"[0:a]aformat=channel_layouts=stereo,volume={self.config.vocal_volume}[v];"
            f"[1:a]volume={self.config.instrumental_volume}[i];"
            f"[v][i]amix=inputs=2:duration=longest",
            "-ar", str(self.config.sample_rate),
            str(output),
        ]
        try:
            run_command(command, logger=self.logger)
        except ProcessError as exc:
            return MixResult(success=False, error=str(exc))
        return MixResult(success=True, wav_path=output)
