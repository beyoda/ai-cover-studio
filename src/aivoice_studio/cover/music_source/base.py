"""MusicSource protocol."""

from __future__ import annotations

from typing import Protocol

from aivoice_studio.cover.music_source.types import AudioAsset


class MusicSource(Protocol):
    """Resolve a user query into a local AudioAsset."""

    name: str

    def resolve(self, query: str) -> AudioAsset:
        """Return a local audio file asset for ``query``.

        Raises ``MusicSourceError`` on failure.
        """
        ...
