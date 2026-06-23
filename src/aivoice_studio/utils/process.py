from __future__ import annotations

import logging
import subprocess
from pathlib import Path


class ProcessError(RuntimeError):
    pass


def run_command(command: str | list[str], cwd: Path | None = None, logger: logging.Logger | None = None) -> str:
    """Run a command and return its output. Supports both string shell commands and argument lists."""
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
        )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != 0:
        raise ProcessError(output or f"Command failed with code {completed.returncode}")
    return output
