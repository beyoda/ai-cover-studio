from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

from aivoice_studio.models.results import UVRResult
from aivoice_studio.modules.uvr.config import UVRConfig
from aivoice_studio.utils.paths import project_root
from aivoice_studio.utils.process import ProcessError, run_command, split_command_template


class UVRService:
    def __init__(self, config: UVRConfig, logger: logging.Logger | None = None) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("aivoice_studio")

    @staticmethod
    def _split_command(template: str, **kwargs: str) -> list[str]:
        """Build argument list from template, replacing {placeholders} with values.

        Values may contain spaces (e.g. ``C:\\Program Files\\...`` or a song file
        under ``My Music``); see :func:`split_command_template`.
        """
        return split_command_template(template, **kwargs)

    def _build_command(self, input_path: Path, output_dir: Path) -> list[str]:
        """Expand the configured template.

        ``{python}`` is the interpreter running AIVOICE, so ``config/uvr.yaml``
        can stay free of machine-specific absolute paths. The command runs with
        the repository root as its working directory, so relative script and
        model-directory paths resolve consistently.
        """
        return self._split_command(
            self.config.command,
            python=sys.executable,
            input=str(input_path),
            output_dir=str(output_dir),
            model_name=self.config.model_name,
        )

    def separate(self, input_path: Path, output_dir: Path) -> UVRResult:
        # Resolve caller-supplied paths against the current working directory
        # before switching the child process to the repository root.
        input_path = Path(input_path).resolve()
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        if not input_path.exists():
            return UVRResult(success=False, error=f"Input audio not found: {input_path}")
        if self.config.mock_mode:
            vocal = output_dir / "mock_Vocals.wav"
            inst = output_dir / "mock_Instrumental.wav"
            shutil.copy2(input_path, vocal)
            shutil.copy2(input_path, inst)
            return UVRResult(success=True, vocal_path=vocal, instrumental_path=inst)
        command = self._build_command(input_path, output_dir)
        try:
            run_command(command, cwd=project_root(), logger=self.logger)
        except ProcessError as exc:
            return UVRResult(success=False, error=str(exc))
        vocal = next(output_dir.glob(self.config.vocal_glob), None)
        inst = next(output_dir.glob(self.config.instrumental_glob), None)
        if not vocal or not inst:
            return UVRResult(success=False, error="UVR output files were not found")
        return UVRResult(success=True, vocal_path=vocal, instrumental_path=inst)
