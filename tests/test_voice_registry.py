"""Voice Registry unit tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aivoice_studio.cover.voice_registry import (
    VoiceRegistry,
    VoiceRegistryError,
    get_voice,
    get_voice_registry,
    list_voices,
    validate_voice,
)
from aivoice_studio.cover.voice_request import build_cover_request_for_voice


def test_load_project_voices_json():
    reg = get_voice_registry(reload=True)
    assert reg.default_voice_id == "example_voice"
    ids = {a.voice_id for a in list_voices()}
    assert ids == {"example_voice", "example_voice_b"}


def test_get_voice_and_aliases():
    reg = get_voice_registry(reload=True)
    assert get_voice("example_voice").checkpoint.endswith("G_27200.pth")
    for ref in ("example_voice", "ExampleVoice", "示例歌手", "G_27200"):
        asset = reg.resolve(ref)
        assert asset.voice_id == "example_voice"
        assert asset.display_name == "示例歌手"
        assert asset.config.endswith("config1.json")


def test_resolve_cos():
    reg = get_voice_registry(reload=True)
    asset = reg.resolve("example_voice_b")
    assert asset.model_name == "G_16000"
    assert asset.metadata.get("style") == "pop"


def test_require_paths_exist():
    reg = get_voice_registry(reload=True)
    ckpt, cfg = reg.require_paths(get_voice("example_voice"))
    assert ckpt.is_file() and cfg.is_file()


def test_unknown_voice_message():
    with pytest.raises(VoiceRegistryError, match="unknown voice"):
        get_voice("missing")
    assert validate_voice("missing") is False


def test_build_cover_request_for_voice():
    req, asset = build_cover_request_for_voice(
        input_audio=r"D:\songs\a.mp3",
        voice_id="example_voice",
        pitch=2,
        client="test",
    )
    assert req.voice_id == "example_voice"
    assert req.model_name == "G_27200"
    assert asset.display_name == "示例歌手"


def test_from_dict_alias_conflict(tmp_path: Path):
    data = {
        "models_dir": str(tmp_path),
        "voices": {
            "a": {
                "display_name": "A",
                "checkpoint": "A.pth",
                "config": "a.json",
                "aliases": ["shared"],
            },
            "b": {
                "display_name": "B",
                "checkpoint": "B.pth",
                "config": "b.json",
                "aliases": ["shared"],
            },
        },
    }
    with pytest.raises(ValueError, match="conflicts"):
        VoiceRegistry.from_dict(data)


def test_voices_json_schema():
    path = Path(__file__).resolve().parents[1] / "config" / "voices.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["voices"]["example_voice"]["display_name"] == "示例歌手"
    assert "metadata" in data["voices"]["example_voice"]
    assert data["voices"]["example_voice_b"]["checkpoint"] == "G_16000.pth"
