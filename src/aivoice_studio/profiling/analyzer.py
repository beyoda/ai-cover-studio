"""Auto-analysis of profiling data → issues / bottlenecks (observe only)."""

from __future__ import annotations

from typing import Any


def analyze(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Return list of issue dicts: {severity, category, title, detail}."""
    issues: list[dict[str, str]] = []
    stages = payload.get("stages", {})
    timeline = payload.get("timeline", [])
    commands = payload.get("commands", [])
    samples = payload.get("metrics", {}).get("samples", [])
    disk = payload.get("disk", {})

    # --- slowest module ---
    stage_durs = {
        name: data.get("duration_s", 0.0)
        for name, data in stages.items()
        if name != "Total" and isinstance(data, dict)
    }
    if stage_durs:
        slowest = max(stage_durs, key=stage_durs.get)
        total = stages.get("Total", {}).get("duration_s") or sum(stage_durs.values()) or 1.0
        pct = 100.0 * stage_durs[slowest] / total
        issues.append({
            "severity": "info",
            "category": "bottleneck",
            "title": f"最耗时模块: {slowest}",
            "detail": (
                f"{slowest} 耗时 {stage_durs[slowest]:.2f}s，约占 Total 的 {pct:.1f}%。"
                f" 各阶段: " + ", ".join(f"{k}={v:.2f}s" for k, v in sorted(
                    stage_durs.items(), key=lambda x: -x[1]
                ))
            ),
        })

    # --- GPU idle while stage supposedly GPU-bound ---
    gpu_stages = {"UVR", "SVC"}
    for stage_name in gpu_stages:
        stage_samples = [s for s in samples if s.get("stage") == stage_name]
        utils = [s["gpu_util"] for s in stage_samples if s.get("gpu_util") is not None]
        if len(utils) >= 4:
            avg = sum(utils) / len(utils)
            low_frac = sum(1 for u in utils if u < 15) / len(utils)
            if avg < 25 or low_frac > 0.5:
                issues.append({
                    "severity": "warning",
                    "category": "gpu_idle",
                    "title": f"{stage_name} 阶段 GPU 可能空闲等待",
                    "detail": (
                        f"{stage_name} 期间 GPU Util 均值 {avg:.1f}%，"
                        f"低于 15% 的采样占比 {low_frac*100:.0f}% "
                        f"（样本数 {len(utils)}）。可能存在 CPU 预处理、模型加载或 IO 等待。"
                    ),
                })

    # --- CPU bottleneck ---
    cpu_vals = [s["cpu_percent"] for s in samples if s.get("cpu_percent") is not None]
    gpu_vals = [s["gpu_util"] for s in samples if s.get("gpu_util") is not None]
    if cpu_vals and gpu_vals:
        avg_cpu = sum(cpu_vals) / len(cpu_vals)
        avg_gpu = sum(gpu_vals) / len(gpu_vals)
        if avg_cpu > 80 and avg_gpu < 40:
            issues.append({
                "severity": "warning",
                "category": "cpu_bottleneck",
                "title": "CPU 可能成为瓶颈",
                "detail": (
                    f"全程 CPU 均值 {avg_cpu:.1f}% 偏高，同时 GPU Util 均值仅 {avg_gpu:.1f}%。"
                    " 可能卡在 CPU 侧预处理 / Python 编排 / 音频读写。"
                ),
            })

    # --- IO bottleneck ---
    total_read = disk.get("total_read_bytes_est", 0) or 0
    total_write = disk.get("total_write_bytes_est", 0) or 0
    total_s = stages.get("Total", {}).get("duration_s") or 0
    if total_s > 0 and (total_read + total_write) > 0:
        mb_s = (total_read + total_write) / (1024 * 1024) / total_s
        # Soft heuristic: if lots of bytes and slow stages with low GPU
        if mb_s > 20:
            issues.append({
                "severity": "info",
                "category": "io",
                "title": "磁盘吞吐较高",
                "detail": (
                    f"估算读写合计约 {(total_read+total_write)/(1024**2):.1f} MB，"
                    f"平均 ~{mb_s:.1f} MB/s。需结合低 GPU 利用率判断是否 IO 瓶颈。"
                ),
            })

    # Process IO from last sample
    if samples:
        last = samples[-1]
        proc_r = last.get("disk_read_mb")
        proc_w = last.get("disk_write_mb")
        if proc_r is not None and proc_w is not None and total_s > 5:
            if (proc_r + proc_w) / total_s > 30 and (gpu_vals and sum(gpu_vals)/len(gpu_vals) < 35):
                issues.append({
                    "severity": "warning",
                    "category": "io_bottleneck",
                    "title": "IO 可能成为瓶颈",
                    "detail": (
                        f"进程累计读 {proc_r:.1f} MB / 写 {proc_w:.1f} MB，"
                        f"同时 GPU 利用率偏低，怀疑磁盘或大量中间文件拖慢流水线。"
                    ),
                })

    # --- duplicate file paths / repeated IO ---
    all_paths: list[str] = []
    for stage_name, files in disk.get("stages", {}).items():
        for role in ("inputs", "outputs", "intermediates"):
            for f in files.get(role, []):
                all_paths.append(f.get("path", ""))
    from collections import Counter
    counts = Counter(p for p in all_paths if p)
    dupes = {p: c for p, c in counts.items() if c >= 3}
    if dupes:
        top = sorted(dupes.items(), key=lambda x: -x[1])[:5]
        issues.append({
            "severity": "warning",
            "category": "duplicate_io",
            "title": "存在重复文件路径引用",
            "detail": "同一路径在多阶段反复出现: " + "; ".join(
                f"{p}×{c}" for p, c in top
            ),
        })

    # --- repeated ffmpeg ---
    ffmpeg_cmds = [c for c in commands if c.get("tool") == "ffmpeg"]
    if len(ffmpeg_cmds) >= 2:
        issues.append({
            "severity": "info",
            "category": "repeated_ffmpeg",
            "title": f"检测到 {len(ffmpeg_cmds)} 次 ffmpeg 调用",
            "detail": (
                "当前流水线可能对 VocalFX / Mixer / Export 分别调用 ffmpeg。"
                "若效果与导出可合并，存在减少进程启动与重复解码的空间（本阶段仅记录，不优化）。"
            ),
        })

    # --- model load / SVC cold start ---
    svc_cmds = [c for c in commands if c.get("tool") in {"so-vits-svc", "python"}]
    svc_stage = stages.get("SVC", {})
    if svc_cmds and svc_stage.get("duration_s", 0) > 0:
        # Look at early GPU samples during SVC — low util then spike suggests load
        svc_samples = [s for s in samples if s.get("stage") == "SVC"]
        if len(svc_samples) >= 6:
            first = svc_samples[: max(3, len(svc_samples) // 5)]
            rest = svc_samples[len(first):]
            u0 = [s["gpu_util"] for s in first if s.get("gpu_util") is not None]
            u1 = [s["gpu_util"] for s in rest if s.get("gpu_util") is not None]
            if u0 and u1:
                avg0, avg1 = sum(u0) / len(u0), sum(u1) / len(u1)
                if avg0 < 15 and avg1 > avg0 + 20:
                    issues.append({
                        "severity": "warning",
                        "category": "model_load",
                        "title": "SVC 前段疑似重复/冷启动模型加载",
                        "detail": (
                            f"SVC 前段 GPU Util 均值 {avg0:.1f}%，后段 {avg1:.1f}%。"
                            " 每次 cover 若重新拉起 so-vits-svc 进程，模型会重复加载。"
                        ),
                    })

    # --- cache opportunities ---
    cache_hints: list[str] = []
    if stages.get("UVR", {}).get("duration_s", 0) > 5:
        cache_hints.append("同一输入歌曲的 UVR 人声/伴奏可按文件哈希缓存")
    if len(ffmpeg_cmds) >= 2:
        cache_hints.append("无 VocalFX（pitch=0 且混响关闭）时可跳过中间 wav 落盘")
    if svc_cmds:
        cache_hints.append("常驻 SVC 推理服务可避免每次子进程冷启动加载模型")
    if cache_hints:
        issues.append({
            "severity": "info",
            "category": "cache_opportunity",
            "title": "存在可缓存/复用步骤（观察结论）",
            "detail": "；".join(cache_hints),
        })

    # --- timeline empty / failed session ---
    if not timeline:
        issues.append({
            "severity": "error",
            "category": "session",
            "title": "未采集到有效 Timeline",
            "detail": "Pipeline 可能未跑完，或 profiling 未成功绑定。",
        })

    success = payload.get("job", {}).get("success")
    if success is False:
        issues.append({
            "severity": "error",
            "category": "job_failed",
            "title": "本次翻唱失败",
            "detail": str(payload.get("job", {}).get("error") or "unknown error"),
        })

    return issues
