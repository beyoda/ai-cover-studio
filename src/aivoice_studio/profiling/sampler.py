"""Background system / GPU sampler for profiling sessions."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Sample:
    t: float
    stage: str
    timestamp: str = ""  # wall-clock ISO for metrics.csv
    cpu_percent: float | None = None  # system-wide
    process_cpu_percent: float | None = None  # this Python process
    thread_count: int | None = None
    cpu_freq_mhz: float | None = None
    rss_mb: float | None = None
    gpu_util: float | None = None
    gpu_mem_used_mb: float | None = None
    gpu_mem_total_mb: float | None = None
    gpu_temp_c: float | None = None
    gpu_power_w: float | None = None
    gpu_clock_mhz: float | None = None
    disk_read_mb: float | None = None
    disk_write_mb: float | None = None


@dataclass
class SamplerStats:
    samples: list[Sample] = field(default_factory=list)
    peak_rss_mb: float = 0.0
    peak_gpu_mem_mb: float = 0.0
    nvidia_smi_ok: bool = False
    nvidia_smi_error: str = ""
    psutil_ok: bool = False


class MetricsSampler:
    """Poll CPU / RAM / GPU while a profiling session is active."""

    def __init__(self, interval_s: float = 1.0) -> None:
        self.interval_s = interval_s
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._stage = "Idle"
        self._t0 = 0.0
        self.stats = SamplerStats()
        self._proc = None
        self._io0_read = 0
        self._io0_write = 0
        self._psutil = None

        try:
            import psutil

            self._psutil = psutil
            self.stats.psutil_ok = True
            self._proc = psutil.Process(os.getpid())
            # Prime CPU percent counters
            psutil.cpu_percent(None)
            self._proc.cpu_percent(None)
            io = self._proc.io_counters() if hasattr(self._proc, "io_counters") else None
            if io:
                self._io0_read = io.read_bytes
                self._io0_write = io.write_bytes
        except Exception:
            self.stats.psutil_ok = False

        self.stats.nvidia_smi_ok = shutil.which("nvidia-smi") is not None

    def set_stage(self, stage: str) -> None:
        with self._lock:
            self._stage = stage

    def start(self) -> None:
        self._t0 = time.perf_counter()
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="aivoice-profiler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_s):
            sample = self._take_sample()
            with self._lock:
                self.stats.samples.append(sample)
                if sample.rss_mb is not None:
                    self.stats.peak_rss_mb = max(self.stats.peak_rss_mb, sample.rss_mb)
                if sample.gpu_mem_used_mb is not None:
                    self.stats.peak_gpu_mem_mb = max(
                        self.stats.peak_gpu_mem_mb, sample.gpu_mem_used_mb
                    )

    def _take_sample(self) -> Sample:
        from datetime import datetime, timezone

        with self._lock:
            stage = self._stage
        t = time.perf_counter() - self._t0
        sample = Sample(
            t=round(t, 3),
            stage=stage,
            timestamp=datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds"),
        )

        if self._psutil and self._proc:
            try:
                sample.cpu_percent = float(self._psutil.cpu_percent(None))
                sample.process_cpu_percent = float(self._proc.cpu_percent(None))
                sample.thread_count = int(self._proc.num_threads())
                sample.rss_mb = round(self._proc.memory_info().rss / (1024 * 1024), 2)
                freq = self._psutil.cpu_freq()
                if freq:
                    sample.cpu_freq_mhz = round(float(freq.current), 1)
                if hasattr(self._proc, "io_counters"):
                    io = self._proc.io_counters()
                    sample.disk_read_mb = round((io.read_bytes - self._io0_read) / (1024 * 1024), 3)
                    sample.disk_write_mb = round(
                        (io.write_bytes - self._io0_write) / (1024 * 1024), 3
                    )
            except Exception:
                pass

        gpu = self._query_gpu()
        if gpu:
            sample.gpu_util = gpu.get("util")
            sample.gpu_mem_used_mb = gpu.get("mem_used")
            sample.gpu_mem_total_mb = gpu.get("mem_total")
            sample.gpu_temp_c = gpu.get("temp")
            sample.gpu_power_w = gpu.get("power")
            sample.gpu_clock_mhz = gpu.get("clock")
        return sample

    def _query_gpu(self) -> dict[str, float] | None:
        if not self.stats.nvidia_smi_ok:
            return None
        try:
            out = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=utilization.gpu,memory.used,memory.total,"
                    "temperature.gpu,power.draw,clocks.current.graphics",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=2,
            ).strip()
            if not out:
                return None
            # Multi-GPU: take first line
            line = out.splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 6:
                return None

            def _f(v: str) -> float | None:
                try:
                    if v.upper() in {"N/A", "[N/A]", ""}:
                        return None
                    return float(v)
                except ValueError:
                    return None

            return {
                "util": _f(parts[0]),
                "mem_used": _f(parts[1]),
                "mem_total": _f(parts[2]),
                "temp": _f(parts[3]),
                "power": _f(parts[4]),
                "clock": _f(parts[5]),
            }
        except Exception as exc:
            self.stats.nvidia_smi_error = str(exc)
            return None

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            samples = [asdict(s) for s in self.stats.samples]
            return {
                "interval_s": self.interval_s,
                "sample_count": len(samples),
                "peak_rss_mb": self.stats.peak_rss_mb,
                "peak_gpu_mem_mb": self.stats.peak_gpu_mem_mb,
                "nvidia_smi_ok": self.stats.nvidia_smi_ok,
                "nvidia_smi_error": self.stats.nvidia_smi_error,
                "psutil_ok": self.stats.psutil_ok,
                "samples": samples,
            }
