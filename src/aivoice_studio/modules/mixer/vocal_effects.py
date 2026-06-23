"""Apply pitch shift and reverb to vocals via ffmpeg."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from aivoice_studio.utils.process import ProcessError, run_command

REVERB_PRESETS = {
    "关闭": "",
    "录音棚": "aecho=0.5:0.3:100:0.3",
    "现场": "aecho=0.6:0.4:150:0.4",
    "大教堂": "aecho=0.7:0.5:200:0.5",
}


@dataclass(slots=True)
class VocalFXConfig:
    ffmpeg_path: str = "ffmpeg"
    pitch: int = 0
    reverb: str = "关闭"
    mock_mode: bool = True


class VocalEffectsProcessor:
    """Apply pitch shift / reverb to a vocal file before mixing."""

    def __init__(self, config: VocalFXConfig, logger: logging.Logger | None = None) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("aivoice_studio")

    def process(self, vocal_path: Path, output_dir: Path) -> Path:
        """Return path to processed vocal (or original if no effects)."""
        has_pitch = self.config.pitch != 0
        has_reverb = bool(REVERB_PRESETS.get(self.config.reverb, ""))

        if not has_pitch and not has_reverb:
            return vocal_path  # no-op, skip entirely

        output_dir.mkdir(parents=True, exist_ok=True)
        current = vocal_path

        if has_pitch:
            current = self._pitch_shift(current, output_dir)

        if has_reverb:
            current = self._reverb(current, output_dir, REVERB_PRESETS[self.config.reverb])

        return current

    def _pitch_shift(self, input_path: Path, output_dir: Path) -> Path:
        """Shift pitch by N semitones. Uses asetrate for pitch + atempo to keep speed."""
        output = output_dir / f"fx_pitch_{input_path.stem}.wav"
        if self.config.mock_mode:
            import shutil
            shutil.copy2(input_path, output)
            return output

        semitones = self.config.pitch
        # asetrate changes pitch+speed → atempo compensates speed → aresample fixes rate
        factor = 2 ** (semitones / 12)
        rate = int(44100 * factor)
        tempo = 2 ** (-semitones / 12)  # compensate speed

        command = [
            self.config.ffmpeg_path, "-y",
            "-i", str(input_path),
            "-af", f"asetrate={rate},atempo={tempo:.6f},aresample=44100",
            str(output),
        ]
        try:
            run_command(command, logger=self.logger)
        except ProcessError as e:
            self.logger.warning("Pitch shift failed, using original: %s", e)
            return input_path
        return output

    def _reverb(self, input_path: Path, output_dir: Path, filter_str: str) -> Path:
        """Apply reverb via aecho filter."""
        output = output_dir / f"fx_reverb_{input_path.stem}.wav"
        if self.config.mock_mode:
            import shutil
            shutil.copy2(input_path, output)
            return output

        command = [
            self.config.ffmpeg_path, "-y",
            "-i", str(input_path),
            "-af", filter_str,
            str(output),
        ]
        try:
            run_command(command, logger=self.logger)
        except ProcessError as e:
            self.logger.warning("Reverb failed, using original: %s", e)
            return input_path
        return output
