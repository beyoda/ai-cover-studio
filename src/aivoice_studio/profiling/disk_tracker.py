"""Disk / intermediate file tracking for profiling stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def file_size(path: Path | None) -> int | None:
    if path is None:
        return None
    try:
        p = Path(path)
        if p.is_file():
            return p.stat().st_size
    except OSError:
        return None
    return None


def fmt_bytes(n: int | None) -> str:
    if n is None:
        return "n/a"
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    if n < 1024 ** 3:
        return f"{n / (1024 ** 2):.2f} MB"
    return f"{n / (1024 ** 3):.2f} GB"


@dataclass
class FileRef:
    path: str
    size_bytes: int | None
    role: str  # input | output | intermediate

    @property
    def size_human(self) -> str:
        return fmt_bytes(self.size_bytes)


@dataclass
class StageFiles:
    stage: str
    inputs: list[FileRef] = field(default_factory=list)
    outputs: list[FileRef] = field(default_factory=list)
    intermediates: list[FileRef] = field(default_factory=list)
    bytes_in: int = 0
    bytes_out: int = 0
    new_files_snapshot: list[FileRef] = field(default_factory=list)


def snapshot_tree(root: Path) -> dict[str, int]:
    """Map relative path -> size for files under root."""
    result: dict[str, int] = {}
    if not root.exists():
        return result
    for p in root.rglob("*"):
        if p.is_file():
            try:
                result[str(p)] = p.stat().st_size
            except OSError:
                pass
    return result


def diff_trees(before: dict[str, int], after: dict[str, int]) -> tuple[list[FileRef], int, int]:
    """Return (new_or_grown files, bytes_written_est, bytes_read_est_from_inputs_not_used)."""
    new_files: list[FileRef] = []
    written = 0
    for path, size in after.items():
        prev = before.get(path)
        if prev is None:
            new_files.append(FileRef(path=path, size_bytes=size, role="intermediate"))
            written += size
        elif size > prev:
            delta = size - prev
            new_files.append(FileRef(path=path, size_bytes=size, role="intermediate"))
            written += delta
    return new_files, written, 0


def make_ref(path: Path | str | None, role: str) -> FileRef | None:
    if path is None or path == "":
        return None
    p = Path(path)
    return FileRef(path=str(p), size_bytes=file_size(p), role=role)


def to_dict(stage: StageFiles) -> dict[str, Any]:
    return asdict(stage)
