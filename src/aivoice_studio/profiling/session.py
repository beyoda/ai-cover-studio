"""Profiling session: stage timing + metrics + report emission."""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from aivoice_studio.profiling.analyzer import analyze
from aivoice_studio.profiling.command_log import CommandLog, bind_command_log
from aivoice_studio.profiling.disk_tracker import (
    StageFiles,
    diff_trees,
    file_size,
    fmt_bytes,
    make_ref,
    snapshot_tree,
)
from aivoice_studio.profiling.sampler import MetricsSampler
from aivoice_studio.utils.paths import project_root


@dataclass
class StageTiming:
    name: str
    start_s: float = 0.0
    end_s: float = 0.0
    duration_s: float = 0.0
    wall_start: str = ""
    wall_end: str = ""


@dataclass
class ProfilerState:
    active: bool = False
    t0: float = 0.0
    job_meta: dict[str, Any] = field(default_factory=dict)
    stages: dict[str, StageTiming] = field(default_factory=dict)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    stage_files: dict[str, StageFiles] = field(default_factory=dict)
    watch_roots: list[Path] = field(default_factory=list)
    tree_before_stage: dict[str, int] = field(default_factory=dict)
    total_read_bytes: int = 0
    total_write_bytes: int = 0
    result: dict[str, Any] = field(default_factory=dict)


class Profiler:
    """Thread-safe profiling coordinator. One active cover session at a time."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state = ProfilerState()
        self._sampler: MetricsSampler | None = None
        self._commands = CommandLog()
        self._output_dir = project_root()
        self.enabled = True

    def _now_wall(self) -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")

    def begin_session(self, job_meta: dict[str, Any], watch_roots: list[Path] | None = None) -> None:
        if not self.enabled:
            return
        with self._lock:
            meta = dict(job_meta)
            meta["started_at"] = self._now_wall()
            self._state = ProfilerState(
                active=True,
                t0=time.perf_counter(),
                job_meta=meta,
                watch_roots=list(watch_roots or []),
            )
            # Seed Total start marker
            self._state.stages["Total"] = StageTiming(
                name="Total", start_s=0.0, wall_start=meta["started_at"]
            )
            self._commands = CommandLog()
            bind_command_log(self._commands)
            self._sampler = MetricsSampler(interval_s=1.0)
            self._sampler.set_stage("Prepare")
            self._commands.set_stage("Prepare")
            self._sampler.start()
            # Marker files so an external waiter can detect start/end
            try:
                root = self._output_dir
                (root / ".profiling_active").write_text(
                    meta.get("started_at", "") + "\n" + str(meta.get("job_id", "")),
                    encoding="utf-8",
                )
                # Clear stale completion marker from a previous run
                done = root / ".profiling_done"
                if done.exists():
                    done.unlink()
            except OSError:
                pass

    def set_watch_roots(self, roots: list[Path]) -> None:
        with self._lock:
            self._state.watch_roots = list(roots)

    def end_session(self, result_meta: dict[str, Any] | None = None) -> Path | None:
        if not self.enabled:
            return None
        with self._lock:
            if not self._state.active:
                return None
            # Close Total
            self._finish_total_locked()
            if result_meta:
                self._state.result = dict(result_meta)
            if self._sampler:
                self._sampler.stop()
            bind_command_log(None)
            out = self._write_reports_locked()
            self._state.active = False
            try:
                active = self._output_dir / ".profiling_active"
                if active.exists():
                    active.unlink()
                (self._output_dir / ".profiling_done").write_text(
                    self._now_wall(), encoding="utf-8"
                )
            except OSError:
                pass
            return out

    def _finish_total_locked(self) -> None:
        if "Total" in self._state.stages and self._state.stages["Total"].end_s:
            return
        elapsed = time.perf_counter() - self._state.t0
        st = self._state.stages.get("Total")
        if st is None:
            st = StageTiming(name="Total", start_s=0.0, wall_start=self._state.job_meta.get("started_at", ""))
            self._state.stages["Total"] = st
        st.end_s = elapsed
        st.duration_s = round(elapsed, 3)
        st.wall_end = self._now_wall()
        self._state.timeline.append({
            "stage": "Total",
            "start_s": 0.0,
            "end_s": st.end_s,
            "duration_s": st.duration_s,
        })

    @contextmanager
    def stage(
        self,
        name: str,
        inputs: list[Path | str | None] | None = None,
        outputs: list[Path | str | None] | None = None,
    ) -> Iterator[None]:
        if not self.enabled or not self._state.active:
            yield
            return

        with self._lock:
            if self._sampler:
                self._sampler.set_stage(name)
            self._commands.set_stage(name)
            start = time.perf_counter() - self._state.t0
            wall_start = self._now_wall()
            self._state.stages[name] = StageTiming(
                name=name, start_s=start, wall_start=wall_start
            )
            # Snapshot trees for intermediate discovery
            tree: dict[str, int] = {}
            for root in self._state.watch_roots:
                tree.update(snapshot_tree(root))
            self._state.tree_before_stage = tree

            sf = StageFiles(stage=name)
            for p in inputs or []:
                ref = make_ref(p, "input")
                if ref:
                    sf.inputs.append(ref)
                    if ref.size_bytes:
                        self._state.total_read_bytes += ref.size_bytes
                        sf.bytes_in += ref.size_bytes
            self._state.stage_files[name] = sf

        try:
            yield
        finally:
            with self._lock:
                end = time.perf_counter() - self._state.t0
                st = self._state.stages.get(name)
                if st:
                    st.end_s = end
                    st.duration_s = round(end - st.start_s, 3)
                    st.wall_end = self._now_wall()
                    self._state.timeline.append({
                        "stage": name,
                        "start_s": round(st.start_s, 3),
                        "end_s": round(st.end_s, 3),
                        "duration_s": st.duration_s,
                    })

                sf = self._state.stage_files.get(name) or StageFiles(stage=name)
                for p in outputs or []:
                    ref = make_ref(p, "output")
                    if ref:
                        sf.outputs.append(ref)
                        if ref.size_bytes:
                            self._state.total_write_bytes += ref.size_bytes
                            sf.bytes_out += ref.size_bytes

                tree_after: dict[str, int] = {}
                for root in self._state.watch_roots:
                    tree_after.update(snapshot_tree(root))
                new_files, written, _ = diff_trees(self._state.tree_before_stage, tree_after)
                # Avoid double-counting known outputs
                out_paths = {o.path for o in sf.outputs}
                for nf in new_files:
                    if nf.path in out_paths:
                        continue
                    sf.intermediates.append(nf)
                # Prefer measured new-file bytes if larger estimate
                if written > sf.bytes_out:
                    # only add delta beyond already counted outputs
                    already = sf.bytes_out
                    extra = max(0, written - already)
                    self._state.total_write_bytes += extra
                    sf.bytes_out = written
                self._state.stage_files[name] = sf

    def note_outputs(self, stage: str, paths: list[Path | str | None]) -> None:
        """Attach outputs discovered after a stage body (when paths only known post-call)."""
        with self._lock:
            sf = self._state.stage_files.get(stage)
            if not sf:
                return
            for p in paths:
                ref = make_ref(p, "output")
                if not ref:
                    continue
                if any(o.path == ref.path for o in sf.outputs):
                    # refresh size
                    for o in sf.outputs:
                        if o.path == ref.path:
                            o.size_bytes = ref.size_bytes
                    continue
                sf.outputs.append(ref)
                if ref.size_bytes:
                    self._state.total_write_bytes += ref.size_bytes
                    sf.bytes_out += ref.size_bytes

    def build_payload(self) -> dict[str, Any]:
        with self._lock:
            metrics = self._sampler.snapshot() if self._sampler else {}
            stages_out: dict[str, Any] = {}
            for name, st in self._state.stages.items():
                stages_out[name] = {
                    "start_s": round(st.start_s, 3),
                    "end_s": round(st.end_s, 3),
                    "duration_s": st.duration_s,
                    "wall_start": st.wall_start,
                    "wall_end": st.wall_end,
                }
            disk_stages = {
                k: {
                    "inputs": [x.__dict__ for x in v.inputs],
                    "outputs": [x.__dict__ for x in v.outputs],
                    "intermediates": [x.__dict__ for x in v.intermediates],
                    "bytes_in": v.bytes_in,
                    "bytes_out": v.bytes_out,
                }
                for k, v in self._state.stage_files.items()
            }
            # Process IO from sampler last sample
            proc_read = proc_write = None
            samples = metrics.get("samples") or []
            if samples:
                proc_read = samples[-1].get("disk_read_mb")
                proc_write = samples[-1].get("disk_write_mb")

            payload: dict[str, Any] = {
                "generated_at": self._now_wall(),
                "job": {
                    **self._state.job_meta,
                    **self._state.result,
                },
                "call_chain": [
                    "Input",
                    "UVR",
                    "SVC",
                    "VocalFX",
                    "Mixer",
                    "Export",
                ],
                "timeline": list(self._state.timeline),
                "stages": stages_out,
                "commands": self._commands.to_list(),
                "metrics": metrics,
                "memory": {
                    "peak_rss_mb": metrics.get("peak_rss_mb"),
                    "peak_gpu_mem_mb": metrics.get("peak_gpu_mem_mb"),
                    "final_rss_mb": samples[-1].get("rss_mb") if samples else None,
                },
                "disk": {
                    "stages": disk_stages,
                    "total_read_bytes_est": self._state.total_read_bytes,
                    "total_write_bytes_est": self._state.total_write_bytes,
                    "total_read_human": fmt_bytes(self._state.total_read_bytes),
                    "total_write_human": fmt_bytes(self._state.total_write_bytes),
                    "process_read_mb": proc_read,
                    "process_write_mb": proc_write,
                },
            }
            payload["analysis"] = analyze(payload)
            return payload

    def _write_reports_locked(self) -> Path:
        from aivoice_studio.profiling.report import write_all_reports

        payload = self.build_payload()
        # release lock? build_payload takes lock - we're already in lock.
        # build_payload acquires lock again via RLock - OK.
        return write_all_reports(self._output_dir, payload, self._commands)


_PROFILER: Profiler | None = None
_PROFILER_LOCK = threading.Lock()


def get_profiler() -> Profiler:
    global _PROFILER
    with _PROFILER_LOCK:
        if _PROFILER is None:
            _PROFILER = Profiler()
        return _PROFILER
