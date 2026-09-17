"""Music Source layer tests (LocalFile / GDStudio search-choice / Skill params).

Voice-related assertions use a synthetic registry in ``tmp_path`` so the suite
does not depend on any particular voice, on celebrity models, or on files that
only exist on the maintainer's machine.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

import aivoice_studio.cover.voice_registry as voice_registry_module
from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.music_source import (
    AudioAsset,
    GDStudioSource,
    LocalFileSource,
    MusicSourceChoiceNeeded,
    MusicSourceError,
    SongCandidate,
    resolve_to_audio_asset,
)
from aivoice_studio.cover.voice_registry import VoiceRegistry, get_voice_registry
from aivoice_studio.cover.voice_request import build_cover_request_for_voice

ROOT = Path(__file__).resolve().parents[1]
PARAM_PARSE = ROOT / "hermes_skill" / "media" / "aivoice-cover" / "scripts" / "param_parse.py"


def _load_param_parse():
    spec = importlib.util.spec_from_file_location("aivoice_param_parse", PARAM_PARSE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    spec.loader.exec_module(mod)
    return mod


def _synthetic_registry(models_dir: Path) -> VoiceRegistry:
    """One enabled voice named ``alpha`` with a vec768l12 config."""
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / "G_10000.pth").write_bytes(b"")
    (models_dir / "config.json").write_text(
        json.dumps({"model": {"speech_encoder": "vec768l12", "ssl_dim": 768}}),
        encoding="utf-8",
    )
    return VoiceRegistry.from_dict(
        {
            "models_dir": str(models_dir),
            "default_voice_id": "alpha",
            "voices": {
                "alpha": {
                    "display_name": "Alpha Voice",
                    "description": "Synthetic voice",
                    "checkpoint": "G_10000.pth",
                    "config": "config.json",
                    "enabled": True,
                    "aliases": ["alpha"],
                }
            },
        }
    )


@pytest.fixture(autouse=True)
def _reload_registry():
    get_voice_registry(reload=True)
    yield
    get_voice_registry(reload=True)


@pytest.fixture
def sample_mp3(tmp_path: Path) -> Path:
    real = ROOT / "test_songs"
    if real.is_dir():
        for p in real.rglob("*.mp3"):
            return p
    fake = tmp_path / "song.mp3"
    fake.write_bytes(b"ID3\x00fake-audio")
    return fake


def test_local_file_resolve(sample_mp3: Path):
    asset = LocalFileSource().resolve(str(sample_mp3))
    assert isinstance(asset, AudioAsset)
    assert Path(asset.path).is_file()
    assert asset.source == "local"
    assert asset.title

    via = resolve_to_audio_asset(input_path=str(sample_mp3))
    assert Path(via.path).resolve() == Path(sample_mp3).resolve()
    assert via.source == "local"


def test_source_song_name_needs_choice(monkeypatch):
    def fake_search(self, query, *, count=8, pages=1):
        return [
            SongCandidate(track_id="1885536903", name="回马枪", artist="张晓棠"),
            SongCandidate(track_id="1885534230", name="回马枪 (DJ版)", artist="张晓棠"),
        ]

    monkeypatch.setattr(GDStudioSource, "search", fake_search)

    with pytest.raises(MusicSourceChoiceNeeded) as ei:
        resolve_to_audio_asset(source="回马枪")
    assert len(ei.value.candidates) == 2
    assert ei.value.candidates[0].track_id == "1885536903"

    with pytest.raises(MusicSourceChoiceNeeded):
        GDStudioSource().resolve("回马枪")

    with pytest.raises(MusicSourceError, match="file not found"):
        resolve_to_audio_asset(input_path=r"D:\not_exist_aivoice_song.mp3")


def test_expand_search_queries_tanglingshan():
    from aivoice_studio.cover.music_source.gdstudio import expand_search_queries

    variants = expand_search_queries("示例歌手 - 示例曲目")
    assert "示例歌手 示例曲目" in variants
    assert "示例曲目" in variants
    assert "示例歌手" in variants
    assert any("ExampleArtist" in v for v in variants)


def test_search_variants_prefer_gareth(monkeypatch):
    calls: list[str] = []

    def fake_once(self, query, *, count=8, pages=1):
        calls.append(query)
        if query in ("示例歌手 - 示例曲目", "示例歌手的示例曲目"):
            return []
        if query == "示例歌手":
            return [
                SongCandidate(track_id="1", name="颜色", artist="ExampleArtist"),
                SongCandidate(track_id="2", name="示例曲目", artist="ExampleArtist"),
            ]
        if query == "示例曲目":
            return [
                SongCandidate(track_id="2", name="示例曲目", artist="ExampleArtist"),
                SongCandidate(track_id="9", name="示例曲目", artist="其他人"),
            ]
        return []

    monkeypatch.setattr(GDStudioSource, "_search_once", fake_once)
    rows = GDStudioSource().search("示例歌手 - 示例曲目", count=8)
    assert rows
    assert rows[0].artist == "ExampleArtist"
    assert rows[0].name == "示例曲目"
    assert "示例歌手 - 示例曲目" in calls


def test_track_id_resolve(monkeypatch, tmp_path: Path):
    fake = tmp_path / "dl.mp3"
    fake.write_bytes(b"ID3fake")

    def fake_resolve_track(self, track_id, *, title="", br="320"):
        return AudioAsset(
            path=str(fake),
            title=title or "回马枪",
            source="gdstudio",
            metadata={"track_id": track_id},
        )

    monkeypatch.setattr(GDStudioSource, "resolve_track", fake_resolve_track)
    asset = resolve_to_audio_asset(source="回马枪", track_id="1885536903")
    assert asset.metadata["track_id"] == "1885536903"
    assert Path(asset.path).is_file()


def test_voice_id_plus_source_combo(
    sample_mp3: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _synthetic_registry(tmp_path / "logs")
    monkeypatch.setattr(
        voice_registry_module, "_DEFAULT_REGISTRY", registry, raising=False
    )

    pp = _load_param_parse()
    parsed = pp.parse_source_and_voice("用Alpha Voice声音翻唱晴天")
    assert parsed.get("voice_id") == "alpha"
    assert parsed.get("source") == "晴天"
    assert parsed.get("source_query") == "晴天"

    multi = pp.extract_cover_params_from_utterances(["用Alpha Voice声音翻唱晴天"])
    assert multi["voice_id"] == "alpha"
    assert multi["source"] == "晴天"

    audio = resolve_to_audio_asset(source=str(sample_mp3))
    req, asset = build_cover_request_for_voice(
        input_audio=audio.path,
        voice_id=multi["voice_id"],
        registry=registry,
    )
    assert isinstance(req, CoverRequest)
    assert asset.voice_id == "alpha"
    assert Path(req.input_audio).is_file()


def test_legacy_input_path_still_works(sample_mp3: Path):
    asset = resolve_to_audio_asset(input_path=str(sample_mp3))
    assert asset.source == "local"
    req = CoverRequest(input_audio=asset.path, voice_id="example_voice", pitch=0)
    assert Path(req.input_audio).is_file()
    assert req.voice_id == "example_voice"

    dual = resolve_to_audio_asset(input_path=str(sample_mp3), source="晴天")
    assert Path(dual.path).resolve() == Path(sample_mp3).resolve()


def test_registered_voice_binds_the_config_declared_for_it(tmp_path: Path) -> None:
    """The registry must hand SVC the exact checkpoint/config pair declared, not a guess."""
    registry = _synthetic_registry(tmp_path / "logs")
    asset = registry.get_voice("alpha")
    ckpt, cfg_path = registry.require_paths(asset)
    assert ckpt.name == "G_10000.pth"
    assert cfg_path.name == "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["model"]["speech_encoder"] == "vec768l12"
    assert cfg["model"]["ssl_dim"] == 768
