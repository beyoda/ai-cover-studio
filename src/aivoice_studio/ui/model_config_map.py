"""Model → config auto-mapping for so-vits-svc models."""

from __future__ import annotations

import json
from pathlib import Path


class ModelConfigMap:
    """Auto-detects .pth models and finds the best matching config.

    Each model in the models directory needs a corresponding config file.
    The mapping logic:
    1. If {model_name}.json exists, use it
    2. Otherwise scan all .json files and pick one with compatible speech_encoder
    3. For models trained with vec768l12 (768-dim input), prefer configs with "vec768l12"
    4. Fall back to first available .json
    """

    def __init__(self, models_dir: str | Path) -> None:
        self.models_dir = Path(models_dir)
        self._cache: dict[str, Path] = {}

    def list_models(self) -> list[str]:
        """Return sorted list of available model names (.pth stems)."""
        if not self.models_dir.exists():
            return []
        return sorted(
            p.stem for p in self.models_dir.glob("*.pth") if p.is_file()
        )

    def get_config(self, model_name: str) -> Path:
        """Find the best config for a given model name.

        Returns the config path, raises FileNotFoundError if none found.
        """
        if model_name in self._cache:
            return self._cache[model_name]

        # Priority 1: exact match
        exact = self.models_dir / f"{model_name}.json"
        if exact.exists():
            self._cache[model_name] = exact
            return exact

        # Priority 2: scan all .json files, prefer vec768l12 (current models use this)
        configs = sorted(self.models_dir.glob("*.json"))
        if not configs:
            raise FileNotFoundError(
                f"No config file found for model '{model_name}' in {self.models_dir}"
            )

        # Prefer configs with vec768l12 encoder (768-dim, matches G_16000/G_27200)
        vec768_configs = []
        hubertsoft_configs = []
        for cfg in configs:
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
                encoder = data.get("model", {}).get("speech_encoder", "")
                if "vec768" in encoder:
                    vec768_configs.append(cfg)
                elif "hubert" in encoder.lower():
                    hubertsoft_configs.append(cfg)
            except (json.JSONDecodeError, KeyError):
                pass

        # vec768l12 models (G_16000, G_27200) need vec768 config
        chosen = vec768_configs[0] if vec768_configs else (
            hubertsoft_configs[0] if hubertsoft_configs else configs[0]
        )
        self._cache[model_name] = chosen
        return chosen

    def get_model_config(self, model_name: str) -> tuple[Path, Path]:
        """Return (model_path, config_path) for a model."""
        model_path = self.models_dir / f"{model_name}.pth"
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")
        config_path = self.get_config(model_name)
        return model_path, config_path
