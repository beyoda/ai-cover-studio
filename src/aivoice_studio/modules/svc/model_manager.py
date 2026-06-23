from dataclasses import dataclass
from pathlib import Path

from aivoice_studio.utils.paths import resolve_path


@dataclass(slots=True)
class SVCModel:
    name: str
    model_path: Path
    config_path: Path


class ModelManager:
    def __init__(self, models_dir: str | Path) -> None:
        self.models_dir = resolve_path(models_dir)

    def list_models(self) -> list[str]:
        """Auto-detect all available .pth models."""
        if not self.models_dir.exists():
            return []
        names: list[str] = []
        for p in sorted(self.models_dir.glob("*.pth")):
            if p.is_file():
                names.append(p.stem)
        return names

    def get_model(self, name: str) -> SVCModel:
        """Get model + best-matching config for a given model name."""
        model_path = self.models_dir / f"{name}.pth"
        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        config_path = self._find_config(name)
        return SVCModel(name=name, model_path=model_path, config_path=config_path)

    def _find_config(self, model_name: str) -> Path:
        """Find the best config for a model.

        Priority:
        1. {model_name}.json (exact match)
        2. config1.json (vec768l12, the encoder used by current models)
        3. config.json (generic fallback)
        4. First available .json
        """
        exact = self.models_dir / f"{model_name}.json"
        if exact.exists():
            return exact

        # Prefer config1.json — both G_16000 and G_27200 use vec768l12
        preferred = self.models_dir / "config1.json"
        if preferred.exists():
            return preferred

        generic = self.models_dir / "config.json"
        if generic.exists():
            return generic

        # Last resort: any .json
        configs = sorted(self.models_dir.glob("*.json"))
        if configs:
            return configs[0]

        raise FileNotFoundError(f"No config file found for model {model_name}")
