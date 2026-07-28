"""Music source layer — resolve queries to local AudioAsset paths.

Pipeline / UVR / SVC never import this package; only Skill / adapters do.
"""

from __future__ import annotations

from aivoice_studio.cover.music_source.base import MusicSource
from aivoice_studio.cover.music_source.gdstudio import (
    GDStudioSource,
    MusicSourceChoiceNeeded,
    SongCandidate,
)
from aivoice_studio.cover.music_source.local import LocalFileSource
from aivoice_studio.cover.music_source.resolve import resolve_to_audio_asset, search_songs
from aivoice_studio.cover.music_source.types import AudioAsset, MusicSourceError

__all__ = [
    "AudioAsset",
    "GDStudioSource",
    "LocalFileSource",
    "MusicSource",
    "MusicSourceChoiceNeeded",
    "MusicSourceError",
    "SongCandidate",
    "resolve_to_audio_asset",
    "search_songs",
]
