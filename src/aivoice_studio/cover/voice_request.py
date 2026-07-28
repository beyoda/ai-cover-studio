"""Build CoverRequest from voice_id via Voice Registry."""

from __future__ import annotations

from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.voice_registry import VoiceAsset, VoiceRegistry, get_voice_registry


def resolve_voice_asset(
    voice_id: str,
    *,
    registry: VoiceRegistry | None = None,
) -> VoiceAsset:
    reg = registry or get_voice_registry()
    return reg.resolve(voice_id)


def build_cover_request_for_voice(
    *,
    input_audio: str,
    voice_id: str,
    pitch: int = 0,
    reverb: str = "关闭",
    f0_method: str = "rmvpe",
    export_mp3: bool = True,
    accompaniment: str = "",
    client: str = "hermes",
    request_id: str | None = None,
    workdir: str | None = None,
    output_dir: str | None = None,
    registry: VoiceRegistry | None = None,
) -> tuple[CoverRequest, VoiceAsset]:
    """Construct CoverRequest with voice_id; model_name filled from asset."""
    asset = resolve_voice_asset(voice_id, registry=registry)
    request = CoverRequest(
        input_audio=input_audio,
        voice_id=asset.voice_id,
        model_name=asset.model_name,
        pitch=pitch,
        reverb=reverb,
        f0_method=f0_method,
        export_mp3=export_mp3,
        accompaniment=accompaniment or "",
        workdir=workdir,
        output_dir=output_dir,
        client=client,
        request_id=request_id,
    )
    return request, asset
