"""Voice Registry integration tests (CoverRequest -> Adapter -> Hermes skill).

All voice data is synthetic and created in ``tmp_path``: no celebrity voice
model, no local ``.venv``, and no maintainer-specific path is required. The
subprocess test uses ``sys.executable`` so it works from a fresh clone.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import aivoice_studio.cover.voice_registry as voice_registry_module
from aivoice_studio.cover.adapter.pipeline_adapter import PipelineAdapter
from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.voice_registry import VoiceRegistry, VoiceRegistryError
from aivoice_studio.cover.voice_resolve import resolve_request_voice
from aivoice_studio.models.results import JobResult

ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPT = ROOT / "hermes_skill" / "media" / "aivoice-cover" / "scripts" / "aivoice_cover.py"


def _touch(models_dir: Path, name: str) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / name).write_bytes(b"")


def _synthetic_registry(models_dir: Path) -> VoiceRegistry:
    _touch(models_dir, "G_10000.pth")
    _touch(models_dir, "config.json")
    _touch(models_dir, "G_20000.pth")
    _touch(models_dir, "config_b.json")
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
                },
                "beta": {
                    "display_name": "Beta",
                    "description": "Synthetic voice B",
                    "checkpoint": "G_20000.pth",
                    "config": "config_b.json",
                },
            },
        }
    )


@pytest.fixture()
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> VoiceRegistry:
    """Install a synthetic registry as the process-wide default."""
    reg = _synthetic_registry(tmp_path / "logs")
    monkeypatch.setattr(voice_registry_module, "_DEFAULT_REGISTRY", reg, raising=False)
    yield reg
    monkeypatch.setattr(voice_registry_module, "_DEFAULT_REGISTRY", None, raising=False)


# --- Registry resolution -----------------------------------------------------


def test_voice_id_resolves_to_its_checkpoint_and_config(registry: VoiceRegistry) -> None:
    resolved = resolve_request_voice(CoverRequest(input_audio="x.mp3", voice_id="alpha"))
    assert resolved.voice_id == "alpha"
    assert resolved.model_name == "G_10000"
    assert resolved.checkpoint_path is not None
    assert resolved.checkpoint_path.name == "G_10000.pth"
    assert resolved.config_path is not None
    assert resolved.config_path.name == "config.json"


def test_unknown_voice_id_raises_unknown_voice(registry: VoiceRegistry) -> None:
    with pytest.raises(VoiceRegistryError, match="unknown voice"):
        resolve_request_voice(CoverRequest(input_audio="x.mp3", voice_id="nope"))


def test_legacy_model_name_resolves_through_registry_stem(registry: VoiceRegistry) -> None:
    resolved = resolve_request_voice(CoverRequest(input_audio="x.mp3", model_name="G_10000"))
    assert resolved.voice_id == "alpha"
    assert resolved.model_name == "G_10000"
    assert resolved.checkpoint_path is not None
    assert resolved.checkpoint_path.name == "G_10000.pth"


def test_unregistered_model_name_falls_back_to_model_manager(registry: VoiceRegistry) -> None:
    """Legacy behaviour: an unregistered model name still reaches SVC."""
    resolved = resolve_request_voice(CoverRequest(input_audio="x.mp3", model_name="G_77777"))
    assert resolved.voice_id is None
    assert resolved.checkpoint_path is None
    assert resolved.config_path is None


def test_voice_id_takes_priority_over_model_name(registry: VoiceRegistry) -> None:
    resolved = resolve_request_voice(
        CoverRequest(input_audio="x.mp3", voice_id="beta", model_name="G_10000")
    )
    assert resolved.voice_id == "beta"
    assert resolved.model_name == "G_20000"


def test_missing_voice_selector_is_rejected(registry: VoiceRegistry) -> None:
    with pytest.raises(ValueError, match="voice_id or model_name"):
        resolve_request_voice(CoverRequest(input_audio="x.mp3"))


# --- Adapter binding ---------------------------------------------------------


def test_adapter_binds_registry_paths_onto_svc_config(
    registry: VoiceRegistry, tmp_path: Path
) -> None:
    captured: dict = {}
    pipeline = MagicMock()
    pipeline.svc.config = MagicMock()
    pipeline.svc.config.model_path = ""
    pipeline.svc.config.config_path = ""

    def _fake_run(job):
        captured["job"] = job
        return JobResult(success=True, wav_path=Path("a.wav"))

    pipeline.run.side_effect = _fake_run

    adapter = PipelineAdapter()
    request = CoverRequest(
        input_audio=str(tmp_path / "demo.mp3"),
        voice_id="alpha",
        workdir=str(tmp_path / "workdir"),
        output_dir=str(tmp_path / "outputs"),
    )
    with patch(
        "aivoice_studio.cover.adapter.pipeline_adapter.build_pipeline",
        return_value=(
            pipeline,
            {"runtime": {"workdir": "workdir", "output_dir": "outputs", "uvr_cache": False}},
        ),
    ):
        result = adapter.run(request, job_id="voicetest0001", mock_mode=True)

    assert result.success is True
    assert result.model_name == "G_10000"
    assert captured["job"].model_name == "G_10000"
    assert str(pipeline.svc.config.model_path).endswith("G_10000.pth")
    assert str(pipeline.svc.config.config_path).endswith("config.json")


# --- Hermes skill ------------------------------------------------------------


@pytest.mark.skipif(not SKILL_SCRIPT.is_file(), reason="Hermes skill script is not present")
def test_hermes_skill_list_voices_succeeds_on_the_shipped_configuration() -> None:
    """The skill must list the registry without a hardcoded voice table."""
    proc = subprocess.run(
        [sys.executable, str(SKILL_SCRIPT), "--list-voices"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["status"] == "ok"
    assert isinstance(payload["voices"], list)
    assert "pretty" in payload

    shipped = VoiceRegistry.load()
    assert {row["voice_id"] for row in payload["voices"]} == {
        asset.voice_id for asset in shipped.list_voices()
    }


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required to inspect tracked files")
def test_no_third_party_model_or_audio_binary_is_tracked() -> None:
    """Policy guard: the repository distributes code only, never assets."""
    proc = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        check=False,
    )
    if proc.returncode != 0:
        pytest.skip("not a git checkout")
    tracked = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    forbidden_suffixes = (".pth", ".onnx", ".ckpt", ".pt", ".safetensors", ".mp3", ".wav")
    offenders = [path for path in tracked if path.lower().endswith(forbidden_suffixes)]
    assert offenders == [], f"binary model/audio assets must not be tracked: {offenders}"
