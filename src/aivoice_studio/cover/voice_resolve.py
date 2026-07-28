"""Resolve CoverRequest voice_id / model_name against Voice Registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.voice_registry import (
    VoiceAsset,
    VoiceRegistry,
    VoiceRegistryError,
    get_voice_registry,
)


@dataclass(slots=True, frozen=True)
class ResolvedVoice:
    model_name: str
    voice_id: str | None
    asset: VoiceAsset | None
    checkpoint_path: Path | None
    config_path: Path | None


def resolve_request_voice(
    request: CoverRequest,
    *,
    registry: VoiceRegistry | None = None,
) -> ResolvedVoice:
    """Prefer ``voice_id``; else resolve ``model_name`` via Registry aliases.

    If only a legacy ``model_name`` is set and it is not in the Registry,
    returns paths=None so SVC falls back to ModelManager (compat).
    """
    reg = registry or get_voice_registry()

    if request.voice_id:
        try:
            asset = reg.resolve(str(request.voice_id))
        except VoiceRegistryError as exc:
            raise VoiceRegistryError("unknown voice") from exc
        ckpt, cfg = reg.require_paths(asset)
        return ResolvedVoice(
            model_name=asset.model_name,
            voice_id=asset.voice_id,
            asset=asset,
            checkpoint_path=ckpt,
            config_path=cfg,
        )

    if request.model_name:
        try:
            asset = reg.resolve(str(request.model_name))
        except VoiceRegistryError:
            return ResolvedVoice(
                model_name=str(request.model_name),
                voice_id=None,
                asset=None,
                checkpoint_path=None,
                config_path=None,
            )
        ckpt, cfg = reg.require_paths(asset)
        return ResolvedVoice(
            model_name=asset.model_name,
            voice_id=asset.voice_id,
            asset=asset,
            checkpoint_path=ckpt,
            config_path=cfg,
        )

    raise ValueError("CoverRequest requires voice_id or model_name")
