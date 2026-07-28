"""Resolve Skill/API music inputs to AudioAsset."""

from __future__ import annotations

from pathlib import Path

from aivoice_studio.cover.music_source.gdstudio import (
    GDStudioSource,
    MusicSourceChoiceNeeded,
    SongCandidate,
)
from aivoice_studio.cover.music_source.local import (
    AUDIO_SUFFIXES,
    LocalFileSource,
    find_local_audio,
)
from aivoice_studio.cover.music_source.types import AudioAsset, MusicSourceError


def _looks_like_local_path(query: str) -> bool:
    q = (query or "").strip().strip('"').strip("'")
    if not q or q.lower().startswith(("http://", "https://")):
        return False
    if find_local_audio(q) is not None:
        return True
    path = Path(q)
    if path.suffix.lower() in AUDIO_SUFFIXES:
        return True
    if path.is_absolute():
        return True
    if len(q) >= 2 and q[1] == ":":
        return True
    if "\\" in q or "/" in q:
        return True
    return False


def search_songs(query: str, *, count: int = 8) -> list[SongCandidate]:
    """Search GD音乐台 for ``query`` (public API; attribution required)."""
    return GDStudioSource().search(query, count=count)


def resolve_to_audio_asset(
    *,
    input_path: str | None = None,
    source: str | None = None,
    provider: str | None = None,
    track_id: str | None = None,
) -> AudioAsset:
    """Resolve legacy ``input`` path and/or ``source`` query to AudioAsset.

    Rules:
    - Local audio path → LocalFileSource
    - http(s) URL → GDStudio direct download
    - ``track_id`` (+ optional provider=gdstudio) → GD API url then download
    - Bare song title → GD search, then ``MusicSourceChoiceNeeded`` (user picks in chat)
    """
    local = LocalFileSource()
    gds = GDStudioSource()

    tid = (track_id or "").strip() or None
    if tid:
        title = ""
        for value in (source, input_path):
            if value and str(value).strip() and not str(value).strip().isdigit():
                title = str(value).strip()
                break
        return gds.resolve_track(tid, title=title)

    candidates: list[str] = []
    for value in (input_path, source):
        if value and str(value).strip():
            candidates.append(str(value).strip())
    if not candidates:
        raise MusicSourceError("music source: missing input/source/track_id")

    prov = (provider or "").strip().lower() or None
    query = candidates[0]

    if prov in ("local", "file", "path"):
        return local.resolve(query)
    if prov in ("gdstudio", "gd", "gd_studio"):
        path = Path(query).expanduser()
        if path.is_file():
            return local.resolve(query)
        return gds.resolve(query)

    if Path(query).expanduser().is_file() or _looks_like_local_path(query):
        return local.resolve(query)

    if query.lower().startswith(("http://", "https://")):
        return gds.resolve(query)

    for q in candidates[1:]:
        if Path(q).expanduser().is_file() or _looks_like_local_path(q):
            return local.resolve(q)

    # Song title → search + ask user to choose (Hermes chat)
    try:
        return gds.resolve(query)
    except MusicSourceChoiceNeeded:
        raise
    except MusicSourceError as exc:
        raise MusicSourceError(
            "music source: GD音乐台搜不到 "
            f"{query!r}（{exc}）。请改用 --search 换写法，"
            "或提供本地路径 / 公开 mp3 直链 / track_id"
        ) from exc
