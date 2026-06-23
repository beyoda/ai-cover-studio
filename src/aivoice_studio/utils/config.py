from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from aivoice_studio.utils.paths import project_root


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class ConfigLoader:
    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or project_root() / "config"

    def load(self) -> dict[str, Any]:
        config: dict[str, Any] = {}
        for name in ("default.yaml", "uvr.yaml", "svc.yaml", "mix.yaml"):
            path = self.config_dir / name
            if path.exists():
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                config = _deep_merge(config, data)
        return config
