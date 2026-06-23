"""Persistent history for generated covers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from aivoice_studio.utils.paths import project_root

MAX_ENTRIES = 20


@dataclass(slots=True)
class HistoryEntry:
    song_name: str
    model_name: str
    pitch: int
    output_dir: str
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


class HistoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or project_root() / "history.json"
        self._entries: list[HistoryEntry] = []

    def load(self) -> list[HistoryEntry]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._entries = [HistoryEntry(**item) for item in data[-MAX_ENTRIES:]]
        except (json.JSONDecodeError, TypeError):
            self._entries = []
        return self._entries

    def add(self, song_name: str, model_name: str, pitch: int, output_dir: str) -> None:
        self._entries.append(
            HistoryEntry(
                song_name=song_name,
                model_name=model_name,
                pitch=pitch,
                output_dir=output_dir,
            )
        )
        if len(self._entries) > MAX_ENTRIES:
            self._entries = self._entries[-MAX_ENTRIES:]
        self._save()

    def all(self) -> list[HistoryEntry]:
        return list(self._entries)

    def _save(self) -> None:
        data = [
            {
                "song_name": e.song_name,
                "model_name": e.model_name,
                "pitch": e.pitch,
                "output_dir": e.output_dir,
                "timestamp": e.timestamp,
            }
            for e in self._entries
        ]
        self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
