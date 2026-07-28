"""Local filesystem music source."""

from __future__ import annotations

from pathlib import Path

from aivoice_studio.cover.music_source.types import AudioAsset, MusicSourceError
from aivoice_studio.utils.paths import project_root

AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma", ".mp4"}


def find_local_audio(query: str) -> Path | None:
    """Resolve a path or bare filename against cwd / project / test_songs."""
    raw = (query or "").strip().strip('"').strip("'")
    if not raw:
        return None
    path = Path(raw).expanduser()
    candidates: list[Path] = [path]
    if not path.is_absolute():
        root = project_root()
        candidates.extend(
            [
                Path.cwd() / path,
                root / path,
                root / "test_songs" / path.name,
                root / "test_songs" / path,
            ]
        )
    seen: set[str] = set()
    for cand in candidates:
        try:
            key = str(cand.resolve()) if cand.exists() else str(cand)
        except OSError:
            key = str(cand)
        if key in seen:
            continue
        seen.add(key)
        if cand.is_file():
            return cand.resolve()
    return None


class LocalFileSource:
    name = "local"

    def resolve(self, query: str) -> AudioAsset:
        raw = (query or "").strip().strip('"').strip("'")
        if not raw:
            raise MusicSourceError("local source: empty path")
        found = find_local_audio(raw)
        if found is None:
            raise MusicSourceError(f"local source: file not found: {raw}")
        if found.suffix.lower() not in AUDIO_SUFFIXES:
            raise MusicSourceError("local source: unsupported audio format")
        return AudioAsset(
            path=str(found),
            title=found.stem,
            source="local",
            metadata={"original_query": raw},
        )
