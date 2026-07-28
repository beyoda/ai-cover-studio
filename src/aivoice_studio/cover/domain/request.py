"""Inbound cover request DTO (Cover Skill / Cover Service)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CoverRequest:
    input_audio: str
    model_name: str | None = None
    voice_id: str | None = None
    pitch: int = 0
    reverb: str = "关闭"
    f0_method: str = "rmvpe"
    export_mp3: bool = True
    accompaniment: str = ""
    workdir: str | None = None
    output_dir: str | None = None
    client: str = "unknown"
    request_id: str | None = None
