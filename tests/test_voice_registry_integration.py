"""Voice Registry integration tests (CoverRequest + Adapter + Skill)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from aivoice_studio.cover.adapter.pipeline_adapter import PipelineAdapter
from aivoice_studio.cover.domain.request import CoverRequest
from aivoice_studio.cover.voice_registry import (
    VoiceRegistryError,
    get_voice,
    get_voice_registry,
    list_voices,
    validate_voice,
)
from aivoice_studio.cover.voice_resolve import resolve_request_voice
from aivoice_studio.models.results import JobResult

ROOT = Path(__file__).resolve().parents[1]
SKILL_SCRIPT = ROOT / "hermes_skill" / "media" / "aivoice-cover" / "scripts" / "aivoice_cover.py"
PY = ROOT / ".venv" / "Scripts" / "python.exe"


@pytest.fixture(autouse=True)
def _reload_registry():
    get_voice_registry(reload=True)
    yield
    get_voice_registry(reload=True)


def test_eason_resolves_correct_checkpoint():
    asset = get_voice("example_voice")
    reg = get_voice_registry()
    ckpt, cfg = reg.require_paths(asset)
    assert asset.display_name == "示例歌手"
    assert ckpt.name == "G_27200.pth"
    assert cfg.name == "config1.json"
    assert ckpt.is_file() and cfg.is_file()
    assert asset.metadata.get("language") == "zh"


def test_cos_resolves_correct_checkpoint():
    asset = get_voice("example_voice_b")
    reg = get_voice_registry()
    ckpt, cfg = reg.require_paths(asset)
    assert asset.display_name == "ExampleVoiceB"
    assert ckpt.name == "G_16000.pth"
    assert cfg.name == "configcos.json"
    assert ckpt.is_file() and cfg.is_file()


def test_unknown_voice_error():
    with pytest.raises(VoiceRegistryError, match="unknown voice"):
        get_voice("nope")
    assert validate_voice("nope") is False
    with pytest.raises(VoiceRegistryError, match="unknown voice"):
        resolve_request_voice(CoverRequest(input_audio="x.mp3", voice_id="nope"))


def test_hermes_skill_reads_registry_list_voices():
    proc = subprocess.run(
        [str(PY), str(SKILL_SCRIPT), "--list-voices"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONIOENCODING": "utf-8"},
        check=False,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    ids = {v["voice_id"] for v in data["voices"]}
    assert ids == {"example_voice", "example_voice_b"}
    by_id = {v["voice_id"]: v for v in data["voices"]}
    assert by_id["example_voice"]["display_name"]
    assert by_id["example_voice_b"]["display_name"]
    # Registry API is source of truth (not a hardcoded skill table)
    api_names = {a.voice_id: a.display_name for a in list_voices()}
    assert api_names["example_voice"] == "示例歌手"
    assert api_names["example_voice_b"] == "ExampleVoiceB"
    assert by_id["example_voice"]["display_name"] == api_names["example_voice"]
    assert by_id["example_voice_b"]["display_name"] == api_names["example_voice_b"]


def test_legacy_model_name_still_resolves_via_registry():
    resolved = resolve_request_voice(
        CoverRequest(input_audio=r"D:\x.mp3", model_name="G_27200")
    )
    assert resolved.voice_id == "example_voice"
    assert resolved.model_name == "G_27200"
    assert resolved.checkpoint_path is not None
    assert resolved.checkpoint_path.name == "G_27200.pth"
    assert resolved.config_path is not None
    assert resolved.config_path.name == "config1.json"


def test_adapter_binds_registry_paths_for_voice_id():
    captured: dict = {}
    pipeline = MagicMock()
    pipeline.svc.config = MagicMock()
    pipeline.svc.config.model_path = ""
    pipeline.svc.config.config_path = ""
    pipeline.run.side_effect = lambda job: (
        captured.setdefault("job", job),
        JobResult(success=True, wav_path=Path("a.wav")),
    )[1]

    adapter = PipelineAdapter()
    req = CoverRequest(
        input_audio=r"D:\songs\demo.mp3",
        voice_id="example_voice",
        workdir=str(ROOT / "workdir"),
        output_dir=str(ROOT / "outputs"),
    )
    with patch(
        "aivoice_studio.cover.adapter.pipeline_adapter.build_pipeline",
        return_value=(
            pipeline,
            {"runtime": {"workdir": "workdir", "output_dir": "outputs", "uvr_cache": False}},
        ),
    ):
        result = adapter.run(req, job_id="voicetest0001", mock_mode=True)

    assert result.success is True
    assert result.model_name == "G_27200"
    assert captured["job"].model_name == "G_27200"
    assert str(pipeline.svc.config.model_path).endswith("G_27200.pth")
    assert str(pipeline.svc.config.config_path).endswith("config1.json")


def test_cover_request_voice_id_priority_over_model_name():
    resolved = resolve_request_voice(
        CoverRequest(
            input_audio=r"D:\x.mp3",
            voice_id="example_voice_b",
            model_name="G_27200",  # should be ignored when voice_id set
        )
    )
    assert resolved.voice_id == "example_voice_b"
    assert resolved.model_name == "G_16000"
