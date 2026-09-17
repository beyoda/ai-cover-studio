"""Subprocess env isolation (Hermes PYTHONPATH must not leak into SVC workenv)."""

from __future__ import annotations

import os

from aivoice_studio.utils.process import scrubbed_subprocess_env


def test_scrubbed_subprocess_env_drops_pythonpath_and_venv():
    base = {
        "PATH": "C:\\Windows\\System32",
        "PYTHONPATH": r"C:\tools\hermes-agent\venv\Lib\site-packages",
        "VIRTUAL_ENV": r"C:\tools\hermes-agent\venv",
        "PYTHONHOME": r"C:\tools\hermes-agent\venv",
        "FOO": "keep-me",
    }
    cleaned = scrubbed_subprocess_env(base)
    assert "PYTHONPATH" not in cleaned
    assert "VIRTUAL_ENV" not in cleaned
    assert "PYTHONHOME" not in cleaned
    assert cleaned["FOO"] == "keep-me"
    assert cleaned["PATH"] == "C:\\Windows\\System32"
    assert cleaned["PYTHONNOUSERSITE"] == "1"


def test_scrubbed_subprocess_env_defaults_to_os_environ(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", r"C:\poison\site-packages")
    monkeypatch.setenv("VIRTUAL_ENV", r"C:\poison\venv")
    cleaned = scrubbed_subprocess_env()
    assert "PYTHONPATH" not in cleaned
    assert "VIRTUAL_ENV" not in cleaned
    assert cleaned["PYTHONNOUSERSITE"] == "1"
    # Unrelated vars still present
    assert "PATH" in cleaned or "Path" in cleaned or os.name == "nt"
