"""Voice Asset Registry — unified voice entry (voice_id → checkpoint + config)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aivoice_studio.utils.paths import project_root, resolve_path

# Optional override so test/validation harnesses can point the registry at a
# synthetic voice file instead of the user's real ``config/voices.json``.
# Never set this in normal operation.
VOICES_CONFIG_ENV_VAR = "AIVOICE_VOICES_CONFIG"


class VoiceRegistryError(LookupError):
    """Unknown or invalid voice reference."""

    def __init__(self, message: str = "unknown voice") -> None:
        super().__init__(message)


@dataclass(slots=True, frozen=True)
class VoiceAsset:
    voice_id: str
    display_name: str
    checkpoint: str
    config: str
    description: str = ""
    enabled: bool = True
    aliases: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        """Backward-compatible alias of display_name."""
        return self.display_name

    @property
    def model_name(self) -> str:
        """Checkpoint stem for CoverRequest.model_name compatibility."""
        return Path(self.checkpoint).stem


@dataclass(slots=True)
class VoiceRegistry:
    models_dir: Path
    default_voice_id: str | None
    _by_id: dict[str, VoiceAsset] = field(default_factory=dict)
    _alias_to_id: dict[str, str] = field(default_factory=dict)
    source_path: Path | None = None

    @classmethod
    def load(cls, path: Path | str | None = None) -> VoiceRegistry:
        if path is not None:
            cfg_path = Path(path)
        else:
            override = (os.environ.get(VOICES_CONFIG_ENV_VAR) or "").strip()
            cfg_path = (
                Path(override)
                if override
                else project_root() / "config" / "voices.json"
            )
        if not cfg_path.is_file():
            raise FileNotFoundError(f"voices.json not found: {cfg_path}")
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return cls.from_dict(data, source_path=cfg_path)

    @classmethod
    def from_dict(cls, data: dict, *, source_path: Path | None = None) -> VoiceRegistry:
        models_raw = data.get("models_dir") or "tools/so-vits-svc/logs/44k"
        models_dir = resolve_path(models_raw)
        default_voice_id = data.get("default_voice_id")
        voices_raw = data.get("voices") or {}
        if not isinstance(voices_raw, dict):
            raise ValueError("voices.json: 'voices' must be an object map")

        by_id: dict[str, VoiceAsset] = {}
        alias_to_id: dict[str, str] = {}

        for voice_id, meta in voices_raw.items():
            if not isinstance(meta, dict):
                raise ValueError(f"voices.json: invalid entry for {voice_id!r}")
            vid = str(voice_id).strip()
            checkpoint = str(meta.get("checkpoint") or "").strip()
            config = str(meta.get("config") or "").strip()
            if not vid or not checkpoint or not config:
                raise ValueError(f"voices.json: {vid!r} needs checkpoint + config")
            display = str(
                meta.get("display_name") or meta.get("name") or vid
            ).strip()
            aliases = meta.get("aliases") or []
            if not isinstance(aliases, list):
                raise ValueError(f"voices.json: aliases for {vid!r} must be a list")
            metadata = meta.get("metadata") or {}
            if not isinstance(metadata, dict):
                raise ValueError(f"voices.json: metadata for {vid!r} must be an object")
            alias_set = {
                vid,
                Path(checkpoint).stem,
                display,
                *{str(a).strip() for a in aliases if str(a).strip()},
            }
            asset = VoiceAsset(
                voice_id=vid,
                display_name=display,
                description=str(meta.get("description") or ""),
                checkpoint=checkpoint,
                config=config,
                enabled=bool(meta.get("enabled", True)),
                aliases=tuple(sorted(alias_set)),
                metadata=dict(metadata),
            )
            by_id[vid] = asset
            for alias in alias_set:
                key = _alias_key(alias)
                if key in alias_to_id and alias_to_id[key] != vid:
                    raise ValueError(
                        f"voices.json: alias {alias!r} conflicts between "
                        f"{alias_to_id[key]!r} and {vid!r}"
                    )
                alias_to_id[key] = vid

        if default_voice_id and default_voice_id not in by_id:
            raise ValueError(f"default_voice_id unknown: {default_voice_id!r}")

        return cls(
            models_dir=models_dir,
            default_voice_id=str(default_voice_id) if default_voice_id else None,
            _by_id=by_id,
            _alias_to_id=alias_to_id,
            source_path=source_path,
        )

    # --- Public API ------------------------------------------------------------

    def get_voice(self, voice_id: str) -> VoiceAsset:
        """Exact voice_id lookup."""
        asset = self._by_id.get(str(voice_id).strip())
        if asset is None or not asset.enabled:
            raise VoiceRegistryError("unknown voice")
        return asset

    # Alias used by earlier code / docs
    def get(self, voice_id: str) -> VoiceAsset:
        return self.get_voice(voice_id)

    def list_voices(self, *, enabled_only: bool = True) -> list[VoiceAsset]:
        items = list(self._by_id.values())
        if enabled_only:
            items = [a for a in items if a.enabled]
        return sorted(items, key=lambda a: a.voice_id)

    def list(self, *, enabled_only: bool = True) -> list[VoiceAsset]:
        return self.list_voices(enabled_only=enabled_only)

    def validate_voice(self, voice_id: str) -> bool:
        """Return True if voice_id is registered and enabled; else False."""
        asset = self._by_id.get(str(voice_id).strip())
        return bool(asset and asset.enabled)

    def resolve(self, ref: str) -> VoiceAsset:
        """Resolve voice_id, display_name, alias, or legacy model stem."""
        raw = (ref or "").strip()
        if not raw:
            raise VoiceRegistryError("unknown voice")
        if raw in self._by_id and self._by_id[raw].enabled:
            return self._by_id[raw]
        key = _alias_key(raw)
        vid = self._alias_to_id.get(key)
        if vid and self._by_id[vid].enabled:
            return self._by_id[vid]
        for asset in self._by_id.values():
            if not asset.enabled:
                continue
            if asset.display_name and asset.display_name in raw:
                return asset
            for alias in asset.aliases:
                if alias and alias in raw:
                    return asset
        raise VoiceRegistryError("unknown voice")

    def resolve_paths(self, asset: VoiceAsset) -> tuple[Path, Path]:
        return (
            _join_models(self.models_dir, asset.checkpoint),
            _join_models(self.models_dir, asset.config),
        )

    def require_paths(self, asset: VoiceAsset) -> tuple[Path, Path]:
        ckpt, cfg = self.resolve_paths(asset)
        if not ckpt.is_file():
            raise FileNotFoundError(f"checkpoint missing: {ckpt}")
        if not cfg.is_file():
            raise FileNotFoundError(f"config missing: {cfg}")
        return ckpt, cfg

    def to_public_list(self) -> list[dict[str, Any]]:
        """JSON-serializable voice catalog for Hermes / Skill."""
        rows = []
        for asset in self.list_voices():
            rows.append(
                {
                    "voice_id": asset.voice_id,
                    "display_name": asset.display_name,
                    "description": asset.description,
                    "metadata": dict(asset.metadata),
                }
            )
        return rows


def _alias_key(value: str) -> str:
    return value.strip().casefold()


def _join_models(models_dir: Path, name: str) -> Path:
    path = Path(name)
    if path.is_absolute():
        return path
    return models_dir / path


_DEFAULT_REGISTRY: VoiceRegistry | None = None


def get_voice_registry(*, reload: bool = False) -> VoiceRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None or reload:
        _DEFAULT_REGISTRY = VoiceRegistry.load()
    return _DEFAULT_REGISTRY


def get_voice(voice_id: str) -> VoiceAsset:
    return get_voice_registry().get_voice(voice_id)


def list_voices(*, enabled_only: bool = True) -> list[VoiceAsset]:
    return get_voice_registry().list_voices(enabled_only=enabled_only)


def validate_voice(voice_id: str) -> bool:
    return get_voice_registry().validate_voice(voice_id)
