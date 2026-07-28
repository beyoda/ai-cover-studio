"""External command capture for profiling (commands.log)."""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _classify(command: str | list[str]) -> str:
    text = subprocess.list2cmdline(command) if isinstance(command, list) else str(command)
    lower = text.lower()
    if "audio-separator" in lower:
        return "audio-separator"
    if "ffmpeg" in lower:
        return "ffmpeg"
    if "inference_main" in lower or "so-vits-svc" in lower or "sovits" in lower:
        return "so-vits-svc"
    if "python" in lower:
        return "python"
    return "other"


@dataclass
class CommandRecord:
    index: int
    tool: str
    command: str
    cwd: str | None
    start_time: str
    end_time: str
    duration_s: float
    exit_code: int
    stdout: str
    stderr: str
    stage: str = ""
    success: bool = True


@dataclass
class CommandLog:
    records: list[CommandRecord] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _active_stage: str = field(default="Idle", repr=False)

    def set_stage(self, stage: str) -> None:
        with self._lock:
            self._active_stage = stage

    def add(self, record: CommandRecord) -> None:
        with self._lock:
            self.records.append(record)

    def next_index(self) -> int:
        with self._lock:
            return len(self.records) + 1

    def current_stage(self) -> str:
        with self._lock:
            return self._active_stage

    def to_list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(r) for r in self.records]

    def write_log(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        lines.append("# AI Cover Studio — commands.log")
        lines.append(f"# Generated: {datetime.now(timezone.utc).astimezone().isoformat()}")
        lines.append("")
        with self._lock:
            records = list(self.records)
        for r in records:
            lines.append("=" * 72)
            lines.append(f"[{r.index}] tool={r.tool}  stage={r.stage}  exit={r.exit_code}  "
                         f"duration={r.duration_s:.3f}s")
            lines.append(f"start: {r.start_time}")
            lines.append(f"end:   {r.end_time}")
            if r.cwd:
                lines.append(f"cwd:   {r.cwd}")
            lines.append("command:")
            lines.append(r.command)
            lines.append("--- stdout ---")
            lines.append(r.stdout.rstrip() if r.stdout else "(empty)")
            lines.append("--- stderr ---")
            lines.append(r.stderr.rstrip() if r.stderr else "(empty)")
            lines.append("")
        path.write_text("\n".join(lines), encoding="utf-8")


_ACTIVE_LOG: CommandLog | None = None
_ACTIVE_LOCK = threading.Lock()


def bind_command_log(log: CommandLog | None) -> None:
    global _ACTIVE_LOG
    with _ACTIVE_LOCK:
        _ACTIVE_LOG = log


def get_command_log() -> CommandLog | None:
    with _ACTIVE_LOCK:
        return _ACTIVE_LOG


def record_command(
    command: str | list[str],
    cwd: Path | None,
    start_perf: float,
    end_perf: float,
    start_wall: datetime,
    end_wall: datetime,
    exit_code: int,
    stdout: str,
    stderr: str,
) -> None:
    log = get_command_log()
    if log is None:
        return
    cmd_text = subprocess.list2cmdline(command) if isinstance(command, list) else str(command)
    record = CommandRecord(
        index=log.next_index(),
        tool=_classify(command),
        command=cmd_text,
        cwd=str(cwd) if cwd else None,
        start_time=start_wall.isoformat(timespec="milliseconds"),
        end_time=end_wall.isoformat(timespec="milliseconds"),
        duration_s=round(end_perf - start_perf, 3),
        exit_code=exit_code,
        stdout=stdout or "",
        stderr=stderr or "",
        stage=log.current_stage(),
        success=exit_code == 0,
    )
    log.add(record)


# silence unused import warning for time in some analyzers
_ = time
