"""Music source DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class MusicSourceError(RuntimeError):
    """Raised when a music source cannot resolve an audio asset."""


@dataclass(slots=True)
class AudioAsset:
    path: str
    title: str = ""
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "title": self.title,
            "source": self.source,
            "metadata": dict(self.metadata),
        }
