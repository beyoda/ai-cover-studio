#!/usr/bin/env python3
"""Shared fixtures for the offline Hermes validation scripts.

Everything here is synthetic and created in a temporary directory:

* no celebrity or private voice model,
* no commercial song,
* no maintainer-specific absolute path.

The synthetic registry is injected through ``AIVOICE_VOICES_CONFIG`` so the
validators can exercise the real registry code path without ever touching the
user's ``config/voices.json``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = Path(__file__).resolve().parent
SRC = ROOT / "src"
COVER = SCRIPTS / "aivoice_cover.py"
SKILL_MD = SCRIPTS.parent / "SKILL.md"

VOICES_ENV = "AIVOICE_VOICES_CONFIG"
SESSIONS_ENV = "AIVOICE_HERMES_SESSIONS_DIR"
JOBS_ENV = "AIVOICE_JOBS_DIR"
# Keep validators offline: never spawn the detached worker/notifier pipeline.
KICK_ENV = "AIVOICE_SKIP_PIPELINE_KICK"

# Two synthetic voices. ``alpha`` is the registry default.
SYNTHETIC_VOICES: dict[str, dict[str, Any]] = {
    "alpha": {
        "display_name": "Alpha",
        "description": "Synthetic voice A (offline validation fixture)",
        "checkpoint": "G_10000.pth",
        "config": "config.json",
        "enabled": True,
        "aliases": ["alpha", "Alpha", "示例音色A"],
        "metadata": {"language": "zh", "style": "pop"},
    },
    "beta": {
        "display_name": "Beta",
        "description": "Synthetic voice B (offline validation fixture)",
        "checkpoint": "G_20000.pth",
        "config": "config_b.json",
        "enabled": True,
        "aliases": ["beta", "Beta", "示例音色B"],
        "metadata": {"language": "zh", "style": "pop"},
    },
}

SYNTHETIC_VOICE_IDS = tuple(sorted(SYNTHETIC_VOICES))


def portable_python() -> str:
    """Repository ``.venv`` interpreter when present, else the running one."""
    candidate = ROOT / ".venv" / "Scripts" / "python.exe"
    if candidate.is_file():
        return str(candidate)
    return sys.executable


def make_synthetic_registry(base: Path) -> Path:
    """Write a temporary voices.json plus the asset files it references."""
    models_dir = Path(base) / "logs"
    models_dir.mkdir(parents=True, exist_ok=True)
    for entry in SYNTHETIC_VOICES.values():
        (models_dir / str(entry["checkpoint"])).write_bytes(b"synthetic-checkpoint")
        (models_dir / str(entry["config"])).write_text(
            json.dumps({"model": {"speech_encoder": "vec768l12", "ssl_dim": 768}}),
            encoding="utf-8",
        )
    # Session store and job queue are redirected into the same temp tree so a
    # validation run never writes into the cloned repository.
    (Path(base) / "hermes_sessions").mkdir(parents=True, exist_ok=True)
    (Path(base) / "jobs").mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "models_dir": str(models_dir),
        "default_voice_id": "alpha",
        "voices": SYNTHETIC_VOICES,
    }
    path = Path(base) / "voices.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def sessions_dir(voices_json: Path) -> Path:
    path = Path(voices_json).parent / "hermes_sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def jobs_dir(voices_json: Path) -> Path:
    path = Path(voices_json).parent / "jobs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def synthetic_audio(base: Path, name: str = "example-track.mp3") -> Path:
    """A tiny file with a real MP3 header so extension checks pass offline."""
    path = Path(base) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    # Minimal ID3v2 header + one silent MPEG frame: enough for path/format checks.
    path.write_bytes(b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" + b"\x00" * 417)
    return path


def activate_registry(voices_json: Path) -> None:
    """Point the *current* process at the synthetic registry."""
    os.environ[VOICES_ENV] = str(voices_json)
    os.environ[SESSIONS_ENV] = str(sessions_dir(voices_json))
    os.environ[JOBS_ENV] = str(jobs_dir(voices_json))
    os.environ[KICK_ENV] = "1"


def skill_env(voices_json: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for a skill subprocess: clean of Hermes/VENV contamination."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in {"PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME"}
    }
    env[VOICES_ENV] = str(voices_json)
    env[SESSIONS_ENV] = str(sessions_dir(voices_json))
    env[JOBS_ENV] = str(jobs_dir(voices_json))
    env[KICK_ENV] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    if extra:
        env.update(extra)
    return env


def run_skill(
    args: list[str],
    *,
    voices_json: Path | None = None,
    timeout: float = 120.0,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``aivoice_cover.py`` with a portable interpreter."""
    env = skill_env(voices_json, extra_env) if voices_json else None
    return subprocess.run(
        [portable_python(), str(COVER), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
        env=env,
        timeout=timeout,
    )


def last_json(stdout: str) -> dict:
    lines = [ln for ln in (stdout or "").splitlines() if ln.strip().startswith("{")]
    if not lines:
        raise AssertionError(f"no JSON object on stdout: {stdout!r}")
    return json.loads(lines[-1])


def temporary_workspace(prefix: str) -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix=prefix)
