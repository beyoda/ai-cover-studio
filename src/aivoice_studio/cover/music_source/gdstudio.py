"""GDStudio music source — public API search + direct download (no login bypass).

Uses the documented GD音乐台 API (music-api.gdstudio.xyz) with attribution.
Song-name queries return searchable candidates for the user to pick in chat;
they are not auto-downloaded silently.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from aivoice_studio.cover.music_source.types import AudioAsset, MusicSourceError
from aivoice_studio.utils.paths import project_root

_AUDIO_EXT = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac"}
_URL_RE = re.compile(r"^https?://", re.I)
_API_BASE = "https://music-api.gdstudio.xyz/api.php"
_UA = {
    "User-Agent": "AIVOICE-MusicSource/1.0 (+https://music.gdstudio.xyz attribution)",
    "Referer": "https://music.gdstudio.xyz/",
}
# GD / 网易云艺人名常与口语不一致；别名只用于扩写搜索与排序。
_ARTIST_ALIASES: dict[str, list[str]] = {
    "示例歌手": ["ExampleArtist", "ExampleArtist T", "ExampleArtist"],
    "示例歌手": ["ExampleVoice Chan", "ExampleVoice", "example_voice"],
}
_SPLIT_ARTIST_SONG = re.compile(
    r"^(?P<a>.+?)\s*(?:[-–—－]|的)\s*(?P<b>.+)$"
)


def normalize_song_query(query: str) -> str:
    """Strip cover-intent chatter; keep artist/title for search + rank."""
    raw = re.sub(r"\s+", " ", (query or "").strip())
    raw = re.sub(
        r"^(?:请|帮我|给我)?(?:用.+?(?:的|声音))?翻唱\s*",
        "",
        raw,
    )
    raw = re.sub(r"^翻唱\s*", "", raw)
    return raw.strip()


def expand_search_queries(query: str) -> list[str]:
    """Generate GD search variants for spoken titles like「示例歌手 - 示例曲目」."""
    raw = normalize_song_query(query)
    out: list[str] = []

    def add(q: str) -> None:
        q = re.sub(r"\s+", " ", (q or "").strip())
        if q and q not in out:
            out.append(q)

    add(raw)
    add(raw.replace("的", " "))

    m = _SPLIT_ARTIST_SONG.match(raw)
    if m:
        artist, song = m.group("a").strip(), m.group("b").strip()
        add(f"{artist} {song}")
        add(song)
        add(artist)
        for alias in _ARTIST_ALIASES.get(artist, []):
            add(f"{alias} {song}")
            add(alias)
    else:
        for name, aliases in _ARTIST_ALIASES.items():
            if name in raw:
                rest = raw.replace(name, " ").strip()
                add(rest)
                for alias in aliases:
                    add(f"{alias} {rest}".strip())
                    add(alias)
    return out


def _rank_candidates(query: str, rows: list[SongCandidate]) -> list[SongCandidate]:
    tokens = [t for t in re.split(r"[\s\-–—－的]+", query) if t]
    alias_hits: set[str] = set()
    for t in tokens:
        for a in _ARTIST_ALIASES.get(t, []):
            alias_hits.add(a.lower())
        alias_hits.add(t.lower())

    def score(c: SongCandidate) -> tuple[int, int, str]:
        artist_l = (c.artist or "").lower()
        name_l = (c.name or "").lower()
        artist_score = 0
        title_score = 0
        for t in tokens:
            tl = t.lower()
            if tl and tl in artist_l:
                artist_score += 3
            if tl and tl in name_l:
                title_score += 2
        for a in alias_hits:
            if a and a in artist_l:
                artist_score += 4
        return (-(artist_score + title_score), len(c.name), c.track_id)

    return sorted(rows, key=score)


@dataclass(slots=True)
class SongCandidate:
    track_id: str
    name: str
    artist: str
    album: str = ""
    source: str = "netease"
    metadata: dict[str, Any] = field(default_factory=dict)

    def label(self) -> str:
        who = self.artist or "未知艺人"
        return f"{self.name} - {who}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "name": self.name,
            "artist": self.artist,
            "album": self.album,
            "source": self.source,
            "label": self.label(),
            "metadata": dict(self.metadata),
        }


class MusicSourceChoiceNeeded(MusicSourceError):
    """Raised when a song name matches multiple (or any) remote candidates."""

    def __init__(self, query: str, candidates: list[SongCandidate]) -> None:
        self.query = query
        self.candidates = candidates
        lines = [f"{i}. {c.label()} (id={c.track_id})" for i, c in enumerate(candidates, 1)]
        msg = (
            f"music source: song {query!r} needs a choice via GD音乐台 "
            f"(music.gdstudio.xyz). Reply with track_id or index:\n"
            + "\n".join(lines)
        )
        super().__init__(msg)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "choice_needed",
            "query": self.query,
            "provider": "gdstudio",
            "candidates": [c.to_dict() for c in self.candidates],
            "attribution": "GD音乐台 (music.gdstudio.xyz)",
            "message": (
                f"搜「{self.query}」找到 {len(self.candidates)} 首，"
                "请回复序号或 track_id 后再翻唱"
            ),
        }


class GDStudioSource:
    name = "gdstudio"

    def __init__(
        self,
        download_dir: Path | str | None = None,
        *,
        timeout_s: float = 60.0,
        api_base: str = _API_BASE,
        music_source: str = "netease",
    ) -> None:
        base = Path(download_dir) if download_dir else project_root() / "workdir" / "music_source"
        self.download_dir = base
        self.timeout_s = timeout_s
        self.api_base = api_base
        self.music_source = music_source

    def _search_once(self, query: str, *, count: int = 8, pages: int = 1) -> list[SongCandidate]:
        payload = self._api_json(
            {
                "types": "search",
                "source": self.music_source,
                "name": query,
                "count": str(max(1, min(count, 20))),
                "pages": str(max(1, pages)),
            }
        )
        if not isinstance(payload, list):
            raise MusicSourceError("gdstudio: unexpected search response")
        out: list[SongCandidate] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            tid = str(row.get("id") or row.get("url_id") or "").strip()
            name = str(row.get("name") or "").strip()
            if not tid or not name:
                continue
            artists = row.get("artist") or []
            if isinstance(artists, list):
                artist = ",".join(str(a) for a in artists if a)
            else:
                artist = str(artists)
            out.append(
                SongCandidate(
                    track_id=tid,
                    name=name,
                    artist=artist,
                    album=str(row.get("album") or ""),
                    source=str(row.get("source") or self.music_source),
                    metadata={"from": row.get("from") or "music.gdstudio.xyz"},
                )
            )
        return out

    def search(self, query: str, *, count: int = 8, pages: int = 1) -> list[SongCandidate]:
        raw = (query or "").strip()
        if not raw:
            raise MusicSourceError("gdstudio: empty search query")
        rank_key = normalize_song_query(raw) or raw
        # GD 对「艺人 - 歌名」常返回空；换写法并合并去重（少打几次，避免限流）。
        seen: dict[str, SongCandidate] = {}
        variants = expand_search_queries(raw)
        for i, variant in enumerate(variants):
            try:
                rows = self._search_once(variant, count=count, pages=pages)
            except MusicSourceError:
                continue
            for c in rows:
                if c.track_id not in seen:
                    seen[c.track_id] = c
            if len(seen) >= count:
                break
            # 已有结果就别把别名全打一遍（GD 偶发空/限流）
            if seen and i >= 2:
                break
        return _rank_candidates(rank_key, list(seen.values()))[:count]

    def resolve_track(self, track_id: str, *, title: str = "", br: str = "320") -> AudioAsset:
        tid = (track_id or "").strip()
        if not tid:
            raise MusicSourceError("gdstudio: empty track_id")
        payload = self._api_json(
            {
                "types": "url",
                "source": self.music_source,
                "id": tid,
                "br": br,
            }
        )
        if not isinstance(payload, dict):
            raise MusicSourceError("gdstudio: unexpected url response")
        url = str(payload.get("url") or "").strip()
        if not url or not _URL_RE.match(url):
            raise MusicSourceError(
                "gdstudio: no playable url for this track (may be geo/copyright limited)"
            )
        asset = self._download_public_url(url, title_hint=title or tid)
        asset.metadata.update(
            {
                "track_id": tid,
                "br": payload.get("br"),
                "api_from": payload.get("from") or "music.gdstudio.xyz",
                "attribution": "GD音乐台 (music.gdstudio.xyz)",
            }
        )
        if title:
            asset.title = title
        return asset

    def resolve(self, query: str) -> AudioAsset:
        raw = (query or "").strip()
        if not raw:
            raise MusicSourceError("gdstudio: empty query")

        if _URL_RE.match(raw):
            return self._download_public_url(raw)

        # Explicit track id forms: "id:1885536903" / "track:1885536903"
        m = re.match(r"^(?:id|track)[=:]\s*(\d+)\s*$", raw, re.I)
        if m:
            return self.resolve_track(m.group(1))
        if raw.isdigit() and len(raw) >= 6:
            return self.resolve_track(raw)

        # Song name → candidates for chat selection (do not auto-pick)
        candidates = self.search(raw)
        if not candidates:
            raise MusicSourceError(f"gdstudio: no search results for {raw!r}")
        raise MusicSourceChoiceNeeded(raw, candidates)

    def _api_json(self, params: dict[str, str]) -> Any:
        url = f"{self.api_base}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers=_UA, method="GET")
        # Bypass local Clash/system proxies — they break Feishu/GD TLS intermittently.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise MusicSourceError(
                f"gdstudio: API HTTP {exc.code} (no auth bypass attempted)"
            ) from exc
        except urllib.error.URLError as exc:
            raise MusicSourceError(f"gdstudio: API failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise MusicSourceError("gdstudio: API timeout") from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise MusicSourceError("gdstudio: invalid API JSON") from exc

    def _download_public_url(self, url: str, *, title_hint: str = "") -> AudioAsset:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise MusicSourceError("gdstudio: only http(s) URLs are allowed")
        if not parsed.netloc:
            raise MusicSourceError("gdstudio: invalid URL")

        suffix = Path(parsed.path).suffix.lower()
        if suffix not in _AUDIO_EXT:
            suffix = ".mp3"

        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        out_dir = self.download_dir / "gdstudio" / digest
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"source{suffix}"

        title = title_hint or Path(parsed.path).stem or digest
        if out_path.is_file() and out_path.stat().st_size > 0:
            return AudioAsset(
                path=str(out_path.resolve()),
                title=title,
                source="gdstudio",
                metadata={"url": url, "cached": True},
            )

        req = urllib.request.Request(url, headers=_UA, method="GET")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=self.timeout_s) as resp:
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if (
                    "audio" not in ctype
                    and "octet-stream" not in ctype
                    and "mpeg" not in ctype
                    and suffix not in _AUDIO_EXT
                ):
                    raise MusicSourceError(
                        f"gdstudio: refused non-audio content-type: {ctype or 'unknown'}"
                    )
                data = resp.read()
        except urllib.error.HTTPError as exc:
            raise MusicSourceError(
                f"gdstudio: download failed HTTP {exc.code} (no auth bypass attempted)"
            ) from exc
        except urllib.error.URLError as exc:
            raise MusicSourceError(f"gdstudio: download failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise MusicSourceError("gdstudio: download timeout") from exc

        if not data:
            raise MusicSourceError("gdstudio: empty download")

        out_path.write_bytes(data)
        return AudioAsset(
            path=str(out_path.resolve()),
            title=title,
            source="gdstudio",
            metadata={"url": url, "bytes": len(data), "cached": False},
        )
