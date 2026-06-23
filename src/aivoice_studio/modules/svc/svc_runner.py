from __future__ import annotations

import logging
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from aivoice_studio.models.results import SVCResult
from aivoice_studio.modules.svc.model_manager import ModelManager
from aivoice_studio.utils.paths import resolve_path
from aivoice_studio.utils.process import ProcessError, run_command


@dataclass(slots=True)
class SVCConfig:
    python: str
    project_dir: str
    inference_script: str
    command: str
    models_dir: str
    mock_mode: bool = True
    mode: str = "standard"
    model_path: str = ""
    config_path: str = ""
    speaker: str = ""
    output_format: str = "wav"


class SVCService:
    def __init__(self, config: SVCConfig, logger: logging.Logger | None = None) -> None:
        self.config = config
        self.logger = logger or logging.getLogger("aivoice_studio")
        self.models = ModelManager(config.models_dir)

    def infer(
        self,
        input_wav: Path,
        model_name: str,
        output_dir: Path,
        pitch: int = 0,
        f0_method: str = "rmvpe",
    ) -> SVCResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        if not input_wav.exists():
            return SVCResult(success=False, error=f"Vocal file not found: {input_wav}")

        output_path = output_dir / f"svc_{input_wav.stem}.wav"
        if self.config.mock_mode:
            shutil.copy2(input_wav, output_path)
            return SVCResult(success=True, output_path=output_path)

        if self.config.mode == "so-vits-svc":
            return self._infer_so_vits_svc(input_wav, model_name, output_path, pitch, f0_method)
        return self._infer_standard(input_wav, model_name, output_dir, pitch, f0_method)

    def _infer_standard(
        self,
        input_wav: Path,
        model_name: str,
        output_dir: Path,
        pitch: int,
        f0_method: str,
    ) -> SVCResult:
        model = self.models.get_model(model_name)
        project_dir = resolve_path(self.config.project_dir)
        script = self._resolve_in_project(project_dir, self.config.inference_script)
        command = self._split_command(
            self.config.command,
            python=str(self.config.python),
            script=str(script),
            model_path=str(model.model_path),
            config_path=str(model.config_path),
            input_wav=str(input_wav),
            output_dir=str(output_dir),
            pitch=str(pitch),
            f0_method=f0_method,
        )
        try:
            run_command(command, cwd=project_dir, logger=self.logger)
        except ProcessError as exc:
            return SVCResult(success=False, error=str(exc))
        produced = next(output_dir.glob("*.wav"), None)
        if not produced:
            return SVCResult(success=False, error="SVC output file was not found")
        return SVCResult(success=True, output_path=produced)

    def _infer_so_vits_svc(
        self,
        input_wav: Path,
        model_name: str,
        output_path: Path,
        pitch: int,
        f0_method: str,
    ) -> SVCResult:
        project_dir = resolve_path(self.config.project_dir)
        raw_dir = project_dir / "raw"
        results_dir = project_dir / "results"
        raw_dir.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(parents=True, exist_ok=True)

        raw_name = f"aivoice_{input_wav.stem}_{uuid.uuid4().hex[:8]}.wav"
        raw_path = raw_dir / raw_name
        shutil.copy2(input_wav, raw_path)

        model_path = self._configured_model_path(project_dir, model_name)
        config_path = self._configured_config_path(project_dir, model_name)
        script = self._resolve_in_project(project_dir, self.config.inference_script)
        speaker = self.config.speaker or model_name
        output_format = self.config.output_format or "wav"

        command = self._split_command(
            self.config.command,
            python=str(self._resolve_in_project(project_dir, self.config.python)),
            script=str(script),
            model_path=str(model_path),
            config_path=str(config_path),
            input_name=raw_name,
            input_wav=str(raw_path),
            pitch=str(pitch),
            speaker=speaker,
            f0_method=f0_method,
            output_format=output_format,
        )
        started = time.time()
        try:
            run_command(command, cwd=project_dir, logger=self.logger)
        except ProcessError as exc:
            return SVCResult(success=False, error=str(exc))

        candidates = [
            path for path in results_dir.glob(f"{raw_name}_*.{output_format}")
            if path.stat().st_mtime >= started - 1
        ]
        if not candidates:
            return SVCResult(success=False, error=f"SVC output file was not found in {results_dir}")
        produced = max(candidates, key=lambda path: path.stat().st_mtime)
        shutil.copy2(produced, output_path)
        return SVCResult(success=True, output_path=output_path)

    def _configured_model_path(self, project_dir: Path, model_name: str) -> Path:
        if self.config.model_path:
            return self._resolve_in_project(project_dir, self.config.model_path)
        return self.models.get_model(model_name).model_path

    def _configured_config_path(self, project_dir: Path, model_name: str) -> Path:
        if self.config.config_path:
            return self._resolve_in_project(project_dir, self.config.config_path)
        return self.models.get_model(model_name).config_path

    @staticmethod
    def _resolve_in_project(project_dir: Path, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return project_dir / path

    @staticmethod
    def _split_command(template: str, **kwargs: str) -> list[str]:
        """Build argument list from template, replacing {placeholders} with values."""
        result: list[str] = []
        for token in template.split():
            token = token.format(**kwargs)
            result.append(token)
        return result
