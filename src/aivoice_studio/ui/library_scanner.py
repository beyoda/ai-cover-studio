"""Scan outputs/ directory and manage per-cover metadata."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from aivoice_studio.utils.paths import project_root


@dataclass(slots=True)
class CoverMeta:
    folder: str          # e.g. "76d83149eea5"
    song: str            # song name
    artist: str          # artist (from filename or metadata)
    model: str           # e.g. "G_16000"
    pitch: int = 0
    reverb: str = "关闭"
    created: str = ""    # ISO timestamp

    @property
    def mp3_path(self) -> Path:
        return project_root() / "outputs" / self.folder / "cover.mp3"

    @property
    def wav_path(self) -> Path:
        return project_root() / "outputs" / self.folder / "cover.wav"


class LibraryScanner:
    """Scan outputs/ for covers and manage metadata."""

    def __init__(self) -> None:
        self.outputs_dir = project_root() / "outputs"

    def scan(self) -> list[CoverMeta]:
        """Return all covers sorted by time (newest first)."""
        results: list[CoverMeta] = []
        if not self.outputs_dir.exists():
            return results

        for folder in sorted(self.outputs_dir.iterdir(), reverse=True):
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            mp3 = folder / "cover.mp3"
            if not mp3.exists():
                continue

            # try metadata.json first
            meta_file = folder / "metadata.json"
            if meta_file.exists():
                try:
                    data = json.loads(meta_file.read_text(encoding="utf-8"))
                    results.append(CoverMeta(
                        folder=folder.name,
                        song=data.get("song", folder.name),
                        artist=data.get("artist", ""),
                        model=data.get("model", ""),
                        pitch=data.get("pitch", 0),
                        reverb=data.get("reverb", "关闭"),
                        created=data.get("created", ""),
                    ))
                    continue
                except (json.JSONDecodeError, KeyError):
                    pass

            # fallback: use folder name + file timestamp
            mtime = mp3.stat().st_mtime
            created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
            results.append(CoverMeta(
                folder=folder.name,
                song=f"翻唱作品（{folder.name[:6]}…）",
                artist="",
                model="",
                created=created,
            ))

        return results

    @staticmethod
    def write_metadata(
        folder: str, song: str, artist: str = "",
        model: str = "", pitch: int = 0, reverb: str = "关闭",
    ) -> None:
        """Write metadata.json into an output folder."""
        out_dir = project_root() / "outputs" / folder
        out_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "song": song,
            "artist": artist,
            "model": model,
            "pitch": pitch,
            "reverb": reverb,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        (out_dir / "metadata.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
