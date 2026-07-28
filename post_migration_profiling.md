# Post-Migration Profiling（P2.5）

> 日期：2026-07-26  
> 目的：验证 **GUI → CoverService** 迁移后，性能特征与迁移前一致（无代码修改、无优化）  
> 入口：`CoverService.run` → `PipelineAdapter` → `Pipeline.run`（与迁移后 GUI 相同路径）

---

## 1. 测试环境

| 项 | 值 |
|----|-----|
| 歌曲 | `<repo-root>\test_songs\示例歌手 - 示例曲目.mp3`（8.30 MB） |
| 模型 | `G_16000` |
| Pitch / Reverb | `0` / `关闭` |
| Job ID | `124d42a42f8b` |
| 墙钟 | 2026-07-26 20:57:58 → 21:00:27（约 **148.4 s**） |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU（Driver 560.94，8 GB） |
| UVR 环境 | `.venv` Python 3.12；`torch 2.12.1+cpu`；`onnxruntime 1.28.0`（仅 CPU EP） |
| SVC 环境 | `tools/so-vits-svc/workenv` Python 3.8；`torch 1.13.1+cu117`（CUDA） |
| 调用链 | CoverService → PipelineAdapter → Pipeline（**未改 Pipeline**） |

### 是否仍为 CPU 推理（UVR）？

**是。** `commands.log`：

```text
PyTorch Version: 2.12.1+cpu
ONNX Runtime CPU package installed with version: 1.28.0
No hardware acceleration could be configured, running in CPU mode
```

SVC 仍为独立 workenv 的 **CUDA** 推理（与迁移前相同）。

---

## 2. 完整时间线

| 用户阶段名 | Profiling Stage | 开始 (s) | 结束 (s) | 单阶段耗时 (s) | 占比 |
|------------|-----------------|----------|----------|----------------|------|
| prepare | Prepare | 0.030 | 0.031 | **0.001** | 0.0% |
| audio separation | UVR | 0.032 | 108.935 | **108.903** | 73.5% |
| SVC | SVC | 108.937 | 145.952 | **37.015** | 25.0% |
| mixing | Mixer（含 VocalFX≈0） | 145.954 | 146.125 | **0.170** | 0.1% |
| export | Export | 146.127 | 148.198 | **2.070** | 1.4% |
| **Total** | Total | 0.000 | 148.200 | **148.200** | 100% |

外部命令耗时（`commands.log`）：

| 工具 | 阶段 | 耗时 (s) | Exit |
|------|------|----------|------|
| audio-separator | UVR | 108.900 | 0 |
| so-vits-svc | SVC | 37.000 | 0 |
| ffmpeg | Mixer | 0.165 | 0 |
| ffmpeg | Export | 2.068 | 0 |

产物：

- `outputs/124d42a42f8b/cover.wav`（≈36.6 MB）
- `outputs/124d42a42f8b/cover.mp3`（≈8.3 MB）

---

## 3. 资源使用

采样：1 s 间隔，共 135 点（`metrics.csv` / `profiling.json`）。

| 阶段 | CPU 均值 % | GPU Util avg/max % | 显存均值 MB | 进程 RSS 均值 MB |
|------|------------|---------------------|-------------|------------------|
| UVR | 12.7 | 17.4 / 65.0 | 1002.8 | 21.7 |
| SVC | 3.6 | 34.8 / 100.0 | 2613.0 | 21.5 |
| Mixer | 4.2 | 1.0 / 1.0 | 1004.0 | 21.2 |
| Export | 5.1 | 3.0 / 5.0 | 1007.0 | 22.0 |

峰值：

- Peak Python RSS：**22.0 MB**（编排进程；重活在子进程）
- Peak GPU Memory：**4379 MB**（主要在 SVC）

解读：

- UVR 阶段 GPU 利用率偏低 + 日志确认 **CPU 模式** → 分离仍吃 CPU
- SVC 阶段 GPU 可打满 → 与迁移前一致（CUDA so-vits-svc）

---

## 4. 与迁移前结果对比

迁移前基线（2026-07-26 约 18:14，**直连 Pipeline**，job `e49d3ec8f4e6`）：

| 指标 | 迁移前（直连 Pipeline） | 迁移后（CoverService） | Δ |
|------|-------------------------|------------------------|---|
| 输入 | `uploads/input_*.mp3` 7.10 MB | `test_songs/示例歌手 - 示例曲目.mp3` 8.30 MB | 输入体积不同 |
| Total | 116.4 s | 148.2 s | +31.8 s |
| UVR | 89.7 s（77%） | 108.9 s（74%） | +19.2 s |
| SVC | 24.7 s（21%） | 37.0 s（25%） | +12.3 s |
| Mixer | 0.16 s | 0.17 s | ≈0 |
| Export | 1.80 s | 2.07 s | +0.27 s |
| Prepare / 编排开销 | ≈0 | **0.001 s** | 可忽略 |
| UVR 推理后端 | CPU（ORT/torch+cpu） | CPU（相同日志） | 一致 |
| SVC 后端 | CUDA cu117 | CUDA cu117 | 一致 |
| 瓶颈 | UVR | UVR | 一致 |
| CoverService 额外业务 | — | 无（仅转发 Adapter） | — |

### 结论（性能一致性）

1. **架构开销可忽略**：Prepare ≈ 1 ms；进度/结果仍走同一 `Pipeline.run`。  
2. **墙钟变长主要来自 UVR/SVC 子进程时间**，不是 CoverService 编排层。可能因素：输入文件体积不同（7.1→8.3 MB）、机器负载/热状态、自然抖动。  
3. **性能画像形状一致**：UVR 占主导（~74–77%）→ SVC 次之 → Mix/Export 极短；UVR 仍为 CPU，SVC 仍用 GPU。  
4. **迁移未改变瓶颈结构**；未见 CoverService 引入新的固定开销量级。

---

## 5. 瓶颈分析（观察 only）

1. **UVR（~74%）** — 最大瓶颈；`audio-separator` 仍在 **CPU** 跑 MDX ONNX。  
2. **SVC（~25%）** — 次瓶颈；含 so-vits-svc 子进程冷启动 + CUDA 推理。  
3. **Mixer / Export** — ffmpeg，秒级以下到约 2 s，非主因。  
4. **VocalFX** — pitch=0 / 混响关闭，基本空操作。  
5. **CoverService / Adapter** — 不构成可测量瓶颈。

本阶段**不做** GPU / Worker / Cache / Hermes 优化。

---

## 6. 原始产物索引

| 文件 | 用途 |
|------|------|
| `profiling_report.md` | 本次自动报告 |
| `profiling.json` / `metrics.csv` | 细粒度采样 |
| `commands.log` | 外部命令与 CPU-mode 证据 |
| `issues.md` | 自动问题清单 |
| `outputs/124d42a42f8b/cover.mp3` | 输出 |

---

**P2.5 完成。未改代码。等待下一阶段指令。**
