from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from aivoice_studio.models.results import ExportResult
from aivoice_studio.utils.process import ProcessError, run_command


@dataclass(slots=True)
class ExportConfig:
    ffmpeg_path: str = "ffmpeg"
    bitrate: str = "320k"
    mock_mode: bool = True


class Exporter:
    def __init__(self, config: ExportConfig, logger: logging.Logger | None = None) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("aivoice_studio")

    def to_mp3(self, wav_path: Path) -> ExportResult:
        if not wav_path.exists():
            return ExportResult(success=False, error=f"WAV not found: {wav_path}")
        output = wav_path.with_suffix(".mp3")
        if self.config.mock_mode:
            shutil.copy2(wav_path, output)
            return ExportResult(success=True, output_path=output)
        command = [
            self.config.ffmpeg_path,
            "-y",
            "-i", str(wav_path),
            "-b:a", self.config.bitrate,
            str(output),
        ]
        try:
            run_command(command, logger=self.logger)
        except ProcessError as exc:
            return ExportResult(success=False, error=str(exc))
        return ExportResult(success=True, output_path=output)
