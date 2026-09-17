"""Voice Registry unit tests.

Every test here builds a synthetic registry in ``tmp_path``. No test depends on
a specific voice, on celebrity voice models, or on files that only exist on the
maintainer's machine, so the suite passes on a fresh clone.

The shipped ``config/voices.json`` is validated structurally (see
``test_shipped_registry_*``) rather than for a particular voice.
"""

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

ROOT = Path(__file__).resolve().parents[1]
SHIPPED_REGISTRY = ROOT / "config" / "voices.json"


def _touch(models_dir: Path, name: str) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / name).write_bytes(b"")


@pytest.fixture()
def models_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "logs"
    _touch(directory, "G_10000.pth")
    _touch(directory, "config.json")
    _touch(directory, "G_20000.pth")
    _touch(directory, "config_b.json")
    return directory


@pytest.fixture()
def registry(models_dir: Path) -> VoiceRegistry:
    return VoiceRegistry.from_dict(
        {
            "models_dir": str(models_dir),
            "default_voice_id": "alpha",
            "voices": {
                "alpha": {
                    "display_name": "Alpha",
                    "description": "Synthetic voice A",
                    "checkpoint": "G_10000.pth",
                    "config": "config.json",
                    "enabled": True,
                    "metadata": {"language": "zh", "style": "pop"},
                    "aliases": ["al", "Alpha Voice"],
                },
                "beta": {
                    "display_name": "Beta",
                    "description": "Synthetic voice B",
                    "checkpoint": "G_20000.pth",
                    "config": "config_b.json",
                    "enabled": False,
                },
            },
        }
    )


# --- Registry parsing --------------------------------------------------------


def test_default_voice_id_is_exposed(registry: VoiceRegistry) -> None:
    assert registry.default_voice_id == "alpha"


def test_enabled_only_listing_excludes_disabled_voices(registry: VoiceRegistry) -> None:
    assert [a.voice_id for a in registry.list_voices()] == ["alpha"]
    assert [a.voice_id for a in registry.list_voices(enabled_only=False)] == ["alpha", "beta"]


def test_voice_asset_exposes_checkpoint_stem_as_model_name(registry: VoiceRegistry) -> None:
    asset = registry.get_voice("alpha")
    assert asset.model_name == "G_10000"
    assert asset.name == asset.display_name == "Alpha"
    assert asset.metadata["style"] == "pop"
    assert asset.description == "Synthetic voice A"


def test_aliases_include_id_checkpoint_stem_and_display_name(registry: VoiceRegistry) -> None:
    asset = registry.get_voice("alpha")
    assert set(asset.aliases) == {"alpha", "G_10000", "Alpha", "al", "Alpha Voice"}


@pytest.mark.parametrize("ref", ["alpha", "Alpha", "al", "Alpha Voice", "G_10000"])
def test_resolve_accepts_id_alias_display_name_and_checkpoint_stem(
    registry: VoiceRegistry, ref: str
) -> None:
    assert registry.resolve(ref).voice_id == "alpha"


def test_resolve_matches_display_name_inside_a_longer_phrase(registry: VoiceRegistry) -> None:
    assert registry.resolve("please use Alpha Voice for this").voice_id == "alpha"


def test_disabled_voice_is_not_resolvable(registry: VoiceRegistry) -> None:
    assert registry.validate_voice("beta") is False
    with pytest.raises(VoiceRegistryError, match="unknown voice"):
        registry.get_voice("beta")
    with pytest.raises(VoiceRegistryError, match="unknown voice"):
        registry.resolve("beta")


def test_unknown_reference_raises_registry_error(registry: VoiceRegistry) -> None:
    assert registry.validate_voice("nope") is False
    with pytest.raises(VoiceRegistryError, match="unknown voice"):
        registry.get_voice("nope")
    with pytest.raises(VoiceRegistryError, match="unknown voice"):
        registry.resolve("")


# --- Path resolution ---------------------------------------------------------


def test_require_paths_resolves_relative_to_models_dir(
    registry: VoiceRegistry, models_dir: Path
) -> None:
    ckpt, cfg = registry.require_paths(registry.get_voice("alpha"))
    assert ckpt == models_dir / "G_10000.pth"
    assert cfg == models_dir / "config.json"
    assert ckpt.is_file() and cfg.is_file()


def test_require_paths_raises_when_checkpoint_is_absent(registry: VoiceRegistry) -> None:
    _touch(registry.models_dir, "G_30000.pth")
    asset = VoiceRegistry.from_dict(
        {
            "models_dir": str(registry.models_dir),
            "voices": {
                "ghost": {
                    "display_name": "Ghost",
                    "checkpoint": "G_99999.pth",
                    "config": "config.json",
                }
            },
        }
    ).get_voice("ghost")
    with pytest.raises(FileNotFoundError, match="checkpoint missing"):
        registry.require_paths(asset)


def test_absolute_paths_bypass_models_dir(models_dir: Path) -> None:
    outside = models_dir.parent / "elsewhere.pth"
    _touch(models_dir.parent, "elsewhere.pth")
    reg = VoiceRegistry.from_dict(
        {
            "models_dir": str(models_dir),
            "voices": {
                "abs": {
                    "display_name": "Abs",
                    "checkpoint": str(outside),
                    "config": "config.json",
                }
            },
        }
    )
    ckpt, cfg = reg.resolve_paths(reg.get_voice("abs"))
    assert ckpt == outside
    assert cfg == models_dir / "config.json"


def test_models_dir_falls_back_to_documented_default() -> None:
    reg = VoiceRegistry.from_dict({"voices": {}})
    assert reg.models_dir.name == "44k"
    assert "so-vits-svc" in str(reg.models_dir)


def test_models_dir_relative_value_is_anchored_at_project_root() -> None:
    reg = VoiceRegistry.from_dict({"models_dir": "tools/so-vits-svc/logs/44k", "voices": {}})
    assert reg.models_dir == ROOT / "tools" / "so-vits-svc" / "logs" / "44k"


# --- Validation --------------------------------------------------------------


def test_alias_conflict_between_two_voices_is_rejected() -> None:
    with pytest.raises(ValueError, match="conflicts"):
        VoiceRegistry.from_dict(
            {
                "voices": {
                    "a": {"display_name": "A", "checkpoint": "A.pth", "config": "a.json", "aliases": ["shared"]},
                    "b": {"display_name": "B", "checkpoint": "B.pth", "config": "b.json", "aliases": ["shared"]},
                }
            }
        )


@pytest.mark.parametrize(
    "entry",
    [
        {"display_name": "No checkpoint", "config": "config.json"},
        {"display_name": "No config", "checkpoint": "G_1.pth"},
        {"display_name": "Bad aliases", "checkpoint": "G_1.pth", "config": "c.json", "aliases": "x"},
        {"display_name": "Bad metadata", "checkpoint": "G_1.pth", "config": "c.json", "metadata": [1]},
    ],
)
def test_invalid_entry_is_rejected(entry: dict) -> None:
    with pytest.raises(ValueError):
        VoiceRegistry.from_dict({"voices": {"broken": entry}})


def test_unknown_default_voice_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="default_voice_id unknown"):
        VoiceRegistry.from_dict(
            {
                "default_voice_id": "missing",
                "voices": {"a": {"display_name": "A", "checkpoint": "A.pth", "config": "a.json"}},
            }
        )


def test_voices_map_must_be_an_object() -> None:
    with pytest.raises(ValueError, match="must be an object map"):
        VoiceRegistry.from_dict({"voices": ["a"]})


def test_to_public_list_is_json_serializable_and_enabled_only(registry: VoiceRegistry) -> None:
    rows = registry.to_public_list()
    assert [row["voice_id"] for row in rows] == ["alpha"]
    assert json.loads(json.dumps(rows)) == rows


# --- Module-level helpers ----------------------------------------------------


def test_module_helpers_report_unknown_voice_on_the_shipped_registry() -> None:
    """A fresh clone has no licensed voice, so lookups must fail cleanly."""
    get_voice_registry(reload=True)
    assert validate_voice("definitely-not-registered") is False
    with pytest.raises(VoiceRegistryError):
        get_voice("definitely-not-registered")
    assert isinstance(list_voices(), list)


# --- Shipped configuration ---------------------------------------------------


def test_shipped_registry_is_valid_json_with_expected_shape() -> None:
    data = json.loads(SHIPPED_REGISTRY.read_text(encoding="utf-8"))
    assert data["version"] == 2
    assert isinstance(data["models_dir"], str) and data["models_dir"]
    assert not Path(data["models_dir"]).is_absolute()
    assert isinstance(data["voices"], dict)


def test_shipped_registry_loads_through_the_real_loader() -> None:
    reg = get_voice_registry(reload=True)
    assert reg.source_path == SHIPPED_REGISTRY
    if reg.default_voice_id is not None:
        assert reg.validate_voice(reg.default_voice_id)


def test_every_enabled_shipped_voice_has_its_files_present() -> None:
    reg = get_voice_registry(reload=True)
    for asset in reg.list_voices(enabled_only=True):
        ckpt, cfg = reg.require_paths(asset)
        assert ckpt.is_file(), f"{asset.voice_id}: missing {ckpt}"
        assert cfg.is_file(), f"{asset.voice_id}: missing {cfg}"


def test_shipped_registry_uses_no_celebrity_or_machine_specific_values() -> None:
    raw = SHIPPED_REGISTRY.read_text(encoding="utf-8")
    # Concatenated so the literal tokens never appear in this file (see the
    # matching note in test_install_consistency.py).
    for forbidden in ("\u9648\u5955\u8fc5", "\u9673\u5955\u8fc5", "ea" + "son", "Ea" + "son", "C:\\", "C:/"):
        assert forbidden not in raw, f"config/voices.json still references {forbidden!r}"


# --- Cover request integration ----------------------------------------------


def test_build_cover_request_for_voice_uses_an_injected_registry(
    registry: VoiceRegistry,
) -> None:
    request, asset = build_cover_request_for_voice(
        input_audio=r"D:\songs\demo.mp3",
        voice_id="alpha",
        pitch=2,
        client="test",
        registry=registry,
    )
    assert request.voice_id == "alpha"
    assert request.model_name == "G_10000"
    assert request.pitch == 2
    assert asset.display_name == "Alpha"


def test_build_cover_request_rejects_an_unknown_voice(registry: VoiceRegistry) -> None:
    with pytest.raises(VoiceRegistryError, match="unknown voice"):
        build_cover_request_for_voice(
            input_audio=r"D:\songs\demo.mp3",
            voice_id="nope",
            registry=registry,
        )
