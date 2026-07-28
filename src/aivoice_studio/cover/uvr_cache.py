"""Minimal UVR stem cache (filesystem only)."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from aivoice_studio.utils.paths import project_root, resolve_path


@dataclass(slots=True)
class UvrCacheHit:
    vocal_path: Path
    instrumental_path: Path
    key: str


class UvrCache:
    """Cache UVR vocals + instrumental by content hash + model name."""

    def __init__(
        self,
        root: Path | str | None = None,
        *,
        enabled: bool = True,
        model_name: str = "UVR_MDXNET_Main.onnx",
    ) -> None:
        self.enabled = enabled
        self.model_name = model_name
        base = Path(root) if root else project_root() / "cache" / "uvr"
        self.root = base if base.is_absolute() else resolve_path(base)

    def cache_key(self, input_audio: Path) -> str:
        digest = hashlib.sha256()
        with Path(input_audio).open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"|")
        digest.update(self.model_name.encode("utf-8"))
        digest.update(b"|v1")
        return digest.hexdigest()

    def _dir(self, key: str) -> Path:
        return self.root / key

    def get(self, input_audio: Path) -> UvrCacheHit | None:
        if not self.enabled:
            return None
        path = Path(input_audio)
        if not path.is_file():
            return None
        key = self.cache_key(path)
        folder = self._dir(key)
        vocal = folder / "vocals.wav"
        instrumental = folder / "instrumental.wav"
        meta = folder / "meta.json"
        if vocal.is_file() and instrumental.is_file() and meta.is_file():
            return UvrCacheHit(vocal_path=vocal, instrumental_path=instrumental, key=key)
        return None

    def put(self, input_audio: Path, vocal: Path, instrumental: Path) -> str | None:
        if not self.enabled:
            return None
        if not Path(vocal).is_file() or not Path(instrumental).is_file():
            return None
        key = self.cache_key(Path(input_audio))
        folder = self._dir(key)
        folder.mkdir(parents=True, exist_ok=True)
        dst_v = folder / "vocals.wav"
        dst_i = folder / "instrumental.wav"
        shutil.copy2(vocal, dst_v)
        shutil.copy2(instrumental, dst_i)
        meta = {
            "key": key,
            "model_name": self.model_name,
            "source": str(Path(input_audio).resolve()),
            "version": "v1",
        }
        (folder / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return key
