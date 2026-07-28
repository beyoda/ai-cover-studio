from __future__ import annotations

import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


class ProcessError(RuntimeError):
    pass


# Vars that leak the parent interpreter (e.g. Hermes gateway venv) into
# UVR / so-vits-svc / ffmpeg child processes and break site-packages isolation.
_SCRUB_ENV_KEYS = (
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONSTARTUP",
    "PYTHONUSERBASE",
    "VIRTUAL_ENV",
    "__PYVENV_LAUNCHER__",
    "CONDA_PREFIX",
    "CONDA_DEFAULT_ENV",
    "CONDA_PYTHON_EXE",
    "CONDA_SHLVL",
    "CONDA_PROMPT_MODIFIER",
)


def scrubbed_subprocess_env(
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """Copy ``base`` (default: os.environ) with parent-Python contamination removed.

    Hermes Gateway / terminal tools often set PYTHONPATH to their own
    ``site-packages``. When CoverService then launches
    ``tools/so-vits-svc/workenv/python.exe``, that child incorrectly imports
    Hermes ``typing_extensions`` and crashes in librosa/joblib/cloudpickle.
    """
    env = dict(base if base is not None else os.environ)
    for key in _SCRUB_ENV_KEYS:
        env.pop(key, None)
    # Prefer the child interpreter's stdlib/site over user site packages.
    env["PYTHONNOUSERSITE"] = "1"
    return env


def run_command(command: str | list[str], cwd: Path | None = None, logger: logging.Logger | None = None) -> str:
    """Run a command and return its output. Supports both string shell commands and argument lists."""
    # Profiling hook (observe-only): record command timing / stdout / stderr when a session is active.
    try:
        from aivoice_studio.profiling.command_log import record_command
    except Exception:  # pragma: no cover - profiling optional
        record_command = None  # type: ignore[assignment]

    start_perf = time.perf_counter()
    start_wall = datetime.now(timezone.utc).astimezone()
    child_env = scrubbed_subprocess_env()

    if isinstance(command, list):
        # Argument list mode — no shell, safer for paths with Unicode characters
        if logger:
            logger.info("Running command: %s", subprocess.list2cmdline(command))
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            shell=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=child_env,
        )
    else:
        if logger:
            logger.info("Running command: %s", command)
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=child_env,
        )

    end_perf = time.perf_counter()
    end_wall = datetime.now(timezone.utc).astimezone()
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""

    if record_command is not None:
        try:
            record_command(
                command=command,
                cwd=cwd,
                start_perf=start_perf,
                end_perf=end_perf,
                start_wall=start_wall,
                end_wall=end_wall,
                exit_code=int(completed.returncode),
                stdout=stdout,
                stderr=stderr,
            )
        except Exception:
            if logger:
                logger.debug("profiling command capture failed", exc_info=True)

    output = "\n".join(part for part in (stdout, stderr) if part)
    if completed.returncode != 0:
        raise ProcessError(output or f"Command failed with code {completed.returncode}")
    return output
