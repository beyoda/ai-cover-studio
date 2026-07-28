"""Write profiling_report.md / profiling.json / commands.log / issues.md / metrics.csv."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from aivoice_studio.profiling.command_log import CommandLog
from aivoice_studio.profiling.disk_tracker import fmt_bytes


def write_all_reports(output_dir: Path, payload: dict[str, Any], commands: CommandLog) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "profiling.json"
    md_path = output_dir / "profiling_report.md"
    issues_path = output_dir / "issues.md"
    cmd_path = output_dir / "commands.log"
    csv_path = output_dir / "metrics.csv"

    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    commands.write_log(cmd_path)
    issues_path.write_text(_render_issues(payload), encoding="utf-8")
    md_path.write_text(_render_report(payload), encoding="utf-8")
    _write_metrics_csv(csv_path, payload)
    return md_path


def _write_metrics_csv(path: Path, payload: dict[str, Any]) -> None:
    samples = (payload.get("metrics") or {}).get("samples") or []
    fields = [
        "Timestamp",
        "Elapsed_s",
        "Stage",
        "GPU Util",
        "GPU Memory",
        "GPU Temp",
        "GPU Power",
        "GPU Clock",
        "CPU Usage",
        "Process CPU",
        "Thread Count",
        "CPU Freq",
        "RAM",
        "Disk Read",
        "Disk Write",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for s in samples:
            writer.writerow({
                "Timestamp": s.get("timestamp", ""),
                "Elapsed_s": s.get("t", ""),
                "Stage": s.get("stage", ""),
                "GPU Util": s.get("gpu_util", ""),
                "GPU Memory": s.get("gpu_mem_used_mb", ""),
                "GPU Temp": s.get("gpu_temp_c", ""),
                "GPU Power": s.get("gpu_power_w", ""),
                "GPU Clock": s.get("gpu_clock_mhz", ""),
                "CPU Usage": s.get("cpu_percent", ""),
                "Process CPU": s.get("process_cpu_percent", ""),
                "Thread Count": s.get("thread_count", ""),
                "CPU Freq": s.get("cpu_freq_mhz", ""),
                "RAM": s.get("rss_mb", ""),
                "Disk Read": s.get("disk_read_mb", ""),
                "Disk Write": s.get("disk_write_mb", ""),
            })


def _render_issues(payload: dict[str, Any]) -> str:
    lines = [
        "# Profiling Issues",
        "",
        "> 本文件仅记录观察结论，**不包含修复或优化**。",
        "",
        f"生成时间: {payload.get('generated_at', '')}",
        "",
    ]
    issues = payload.get("analysis") or []
    if not issues:
        lines.append("未发现自动规则命中的问题。")
        lines.append("")
        return "\n".join(lines)

    for i, issue in enumerate(issues, 1):
        lines.append(f"## {i}. [{issue.get('severity', '?').upper()}] {issue.get('title', '')}")
        lines.append("")
        lines.append(f"- 类别: `{issue.get('category', '')}`")
        lines.append(f"- 详情: {issue.get('detail', '')}")
        lines.append("")
    return "\n".join(lines)


def _avg(vals: list[float]) -> float | None:
    return sum(vals) / len(vals) if vals else None


def _stage_metric_summary(samples: list[dict], stage: str) -> dict[str, Any]:
    subset = [s for s in samples if s.get("stage") == stage]
    def col(key: str) -> list[float]:
        return [float(s[key]) for s in subset if s.get(key) is not None]

    return {
        "n": len(subset),
        "gpu_util_avg": _avg(col("gpu_util")),
        "gpu_util_max": max(col("gpu_util")) if col("gpu_util") else None,
        "gpu_mem_avg_mb": _avg(col("gpu_mem_used_mb")),
        "gpu_temp_avg": _avg(col("gpu_temp_c")),
        "gpu_power_avg": _avg(col("gpu_power_w")),
        "gpu_clock_avg": _avg(col("gpu_clock_mhz")),
        "cpu_avg": _avg(col("cpu_percent")),
        "rss_avg_mb": _avg(col("rss_mb")),
    }


def _fmt_opt(v: float | None, unit: str = "", digits: int = 1) -> str:
    if v is None:
        return "n/a"
    return f"{v:.{digits}f}{unit}"


def _render_report(payload: dict[str, Any]) -> str:
    job = payload.get("job") or {}
    stages = payload.get("stages") or {}
    timeline = payload.get("timeline") or []
    metrics = payload.get("metrics") or {}
    samples = metrics.get("samples") or []
    disk = payload.get("disk") or {}
    memory = payload.get("memory") or {}
    commands = payload.get("commands") or []
    analysis = payload.get("analysis") or []

    lines: list[str] = []
    lines.append("# AI Cover Studio — Profiling Report")
    lines.append("")
    lines.append(f"- Generated: `{payload.get('generated_at', '')}`")
    lines.append(f"- Input: `{job.get('input_audio', '')}`")
    lines.append(f"- Model: `{job.get('model_name', '')}`")
    lines.append(f"- Pitch / Reverb: `{job.get('pitch', '')}` / `{job.get('reverb', '')}`")
    lines.append(f"- Job ID: `{job.get('job_id', '')}`")
    lines.append(f"- Success: `{job.get('success', '')}`")
    if job.get("error"):
        lines.append(f"- Error: `{job.get('error')}`")
    lines.append(f"- WAV: `{job.get('wav_path', '')}`")
    lines.append(f"- MP3: `{job.get('mp3_path', '')}`")
    lines.append("")

    # Call chain
    lines.append("## Call Chain")
    lines.append("")
    lines.append("```")
    lines.append("Input → UVR → SVC → VocalFX → Mixer → Export")
    lines.append("```")
    lines.append("")

    # Timeline table
    lines.append("## Timeline")
    lines.append("")
    lines.append("| Stage | Start (s) | End (s) | Duration (s) | % of Total |")
    lines.append("|-------|-----------|---------|--------------|------------|")
    total_s = (stages.get("Total") or {}).get("duration_s") or 0.0
    order = ["Prepare", "UVR", "SVC", "VocalFX", "Mixer", "Export", "Total"]
    shown = set()
    for name in order:
        st = stages.get(name)
        if not st:
            continue
        shown.add(name)
        dur = st.get("duration_s") or 0.0
        pct = f"{100.0 * dur / total_s:.1f}%" if total_s and name != "Total" else ("100%" if name == "Total" else "n/a")
        lines.append(
            f"| {name} | {st.get('start_s', 0):.3f} | {st.get('end_s', 0):.3f} | "
            f"{dur:.3f} | {pct} |"
        )
    for name, st in stages.items():
        if name in shown:
            continue
        dur = st.get("duration_s") or 0.0
        pct = f"{100.0 * dur / total_s:.1f}%" if total_s else "n/a"
        lines.append(
            f"| {name} | {st.get('start_s', 0):.3f} | {st.get('end_s', 0):.3f} | "
            f"{dur:.3f} | {pct} |"
        )
    lines.append("")

    # ASCII timeline
    lines.append("### Timeline (text)")
    lines.append("")
    lines.append("```")
    for ev in timeline:
        if ev.get("stage") == "Total":
            continue
        lines.append(
            f"{ev.get('start_s', 0):8.3f}s .. {ev.get('end_s', 0):8.3f}s  "
            f"[{ev.get('duration_s', 0):7.3f}s]  {ev.get('stage')}"
        )
    if total_s:
        lines.append(f"{'TOTAL':>8}                          [{total_s:7.3f}s]")
    lines.append("```")
    lines.append("")

    # Per-stage resources
    lines.append("## Per-Stage Resource Snapshot")
    lines.append("")
    lines.append(
        "| Stage | GPU Util avg/max | GPU Mem avg | GPU Temp | GPU Power | "
        "GPU Clock | CPU avg | RSS avg |"
    )
    lines.append(
        "|-------|------------------|------------|----------|-----------|"
        "-----------|---------|---------|"
    )
    for name in order:
        if name == "Total" or name not in stages:
            continue
        s = _stage_metric_summary(samples, name)
        lines.append(
            "| {stage} | {gavg}/{gmax} | {gmem} | {temp} | {pwr} | {clk} | {cpu} | {rss} |".format(
                stage=name,
                gavg=_fmt_opt(s["gpu_util_avg"], "%"),
                gmax=_fmt_opt(s["gpu_util_max"], "%"),
                gmem=_fmt_opt(s["gpu_mem_avg_mb"], " MB"),
                temp=_fmt_opt(s["gpu_temp_avg"], " C"),
                pwr=_fmt_opt(s["gpu_power_avg"], " W"),
                clk=_fmt_opt(s["gpu_clock_avg"], " MHz"),
                cpu=_fmt_opt(s["cpu_avg"], "%"),
                rss=_fmt_opt(s["rss_avg_mb"], " MB"),
            )
        )
    lines.append("")

    # Memory peaks
    lines.append("## Memory")
    lines.append("")
    lines.append(f"- Peak Python RSS: **{_fmt_opt(memory.get('peak_rss_mb'), ' MB')}**")
    lines.append(f"- Final RSS: {_fmt_opt(memory.get('final_rss_mb'), ' MB')}")
    lines.append(f"- Peak GPU Memory: **{_fmt_opt(memory.get('peak_gpu_mem_mb'), ' MB')}**")
    lines.append(f"- Sampler samples: {metrics.get('sample_count', 0)} (interval {metrics.get('interval_s')}s)")
    lines.append(f"- nvidia-smi ok: `{metrics.get('nvidia_smi_ok')}`")
    lines.append(f"- psutil ok: `{metrics.get('psutil_ok')}`")
    lines.append("")

    # Disk
    lines.append("## Disk IO")
    lines.append("")
    lines.append(f"- Estimated stage input bytes (sum): **{disk.get('total_read_human', 'n/a')}**")
    lines.append(f"- Estimated stage output/new bytes (sum): **{disk.get('total_write_human', 'n/a')}**")
    lines.append(f"- Process read (psutil): {disk.get('process_read_mb')} MB")
    lines.append(f"- Process write (psutil): {disk.get('process_write_mb')} MB")
    lines.append("")
    for stage_name in order:
        files = (disk.get("stages") or {}).get(stage_name)
        if not files:
            continue
        lines.append(f"### {stage_name}")
        lines.append("")
        for role, label in (("inputs", "Inputs"), ("outputs", "Outputs"), ("intermediates", "Intermediates")):
            items = files.get(role) or []
            if not items:
                continue
            lines.append(f"**{label}**")
            lines.append("")
            for it in items:
                lines.append(
                    f"- `{it.get('path')}` ({fmt_bytes(it.get('size_bytes'))})"
                )
            lines.append("")
        lines.append(
            f"- bytes_in={fmt_bytes(files.get('bytes_in'))}, "
            f"bytes_out={fmt_bytes(files.get('bytes_out'))}"
        )
        lines.append("")

    # Commands summary
    lines.append("## External Commands")
    lines.append("")
    lines.append(f"Total captured commands: **{len(commands)}** (see `commands.log`)")
    lines.append("")
    if commands:
        lines.append("| # | Tool | Stage | Duration (s) | Exit |")
        lines.append("|---|------|-------|--------------|------|")
        for c in commands:
            lines.append(
                f"| {c.get('index')} | {c.get('tool')} | {c.get('stage')} | "
                f"{c.get('duration_s')} | {c.get('exit_code')} |"
            )
        lines.append("")

    # Analysis
    lines.append("## Auto Analysis")
    lines.append("")
    if not analysis:
        lines.append("无自动分析命中项。")
    else:
        for issue in analysis:
            lines.append(
                f"- **[{issue.get('severity')}]** {issue.get('title')}: {issue.get('detail')}"
            )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "详细采样见 `profiling.json` / `metrics.csv`；"
        "问题清单见 `issues.md`；命令原文见 `commands.log`。"
    )
    lines.append("")
    return "\n".join(lines)
