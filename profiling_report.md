# AI Cover Studio — Profiling Report

- Generated: `2026-07-28T10:19:24.251+08:00`
- Input: `<repo-root>\workdir\music_source\gdstudio\a4d1df9f39310ce8\source.mp3`
- Model: `G_16000`
- Pitch / Reverb: `-1` / `关闭`
- Job ID: `ce5f760bb771`
- Success: `True`
- WAV: `<repo-root>\outputs\ce5f760bb771\cover.wav`
- MP3: `<repo-root>\outputs\ce5f760bb771\cover.mp3`

## Call Chain

```
Input → UVR → SVC → VocalFX → Mixer → Export
```

## Timeline

| Stage | Start (s) | End (s) | Duration (s) | % of Total |
|-------|-----------|---------|--------------|------------|
| Prepare | 0.030 | 0.031 | 0.001 | 0.0% |
| UVR | 0.034 | 0.071 | 0.037 | 0.1% |
| SVC | 0.075 | 29.747 | 29.673 | 90.1% |
| VocalFX | 29.752 | 30.029 | 0.277 | 0.8% |
| Mixer | 30.033 | 30.215 | 0.182 | 0.6% |
| Export | 30.219 | 32.936 | 2.717 | 8.2% |
| Total | 0.000 | 32.940 | 32.940 | 100% |

### Timeline (text)

```
   0.030s ..    0.031s  [  0.001s]  Prepare
   0.034s ..    0.071s  [  0.037s]  UVR
   0.075s ..   29.747s  [ 29.673s]  SVC
  29.752s ..   30.029s  [  0.277s]  VocalFX
  30.033s ..   30.215s  [  0.182s]  Mixer
  30.219s ..   32.936s  [  2.717s]  Export
   TOTAL                          [ 32.940s]
```

## Per-Stage Resource Snapshot

| Stage | GPU Util avg/max | GPU Mem avg | GPU Temp | GPU Power | GPU Clock | CPU avg | RSS avg |
|-------|------------------|------------|----------|-----------|-----------|---------|---------|
| Prepare | n/a/n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| UVR | n/a/n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| SVC | 42.6%/100.0% | 2856.7 MB | 55.2 C | 32.6 W | 2081.5 MHz | 6.4% | 24.5 MB |
| VocalFX | n/a/n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| Mixer | n/a/n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| Export | 0.3%/1.0% | 1197.0 MB | 53.3 C | 9.6 W | 330.0 MHz | 5.1% | 24.0 MB |

## Memory

- Peak Python RSS: **24.6 MB**
- Final RSS: 24.0 MB
- Peak GPU Memory: **4004.0 MB**
- Sampler samples: 29 (interval 1.0s)
- nvidia-smi ok: `True`
- psutil ok: `True`

## Disk IO

- Estimated stage input bytes (sum): **204.02 MB**
- Estimated stage output/new bytes (sum): **193.63 MB**
- Process read (psutil): 184.447 MB
- Process write (psutil): 160.343 MB

### Prepare

**Inputs**

- `<repo-root>\workdir\music_source\gdstudio\a4d1df9f39310ce8\source.mp3` (10.39 MB)

- bytes_in=10.39 MB, bytes_out=0 B

### UVR

**Inputs**

- `<repo-root>\workdir\music_source\gdstudio\a4d1df9f39310ce8\source.mp3` (10.39 MB)

**Outputs**

- `<repo-root>\workdir\ce5f760bb771\uvr\vocals.wav` (45.81 MB)
- `<repo-root>\workdir\ce5f760bb771\uvr\instrumental.wav` (45.81 MB)

- bytes_in=10.39 MB, bytes_out=91.62 MB

### SVC

**Inputs**

- `<repo-root>\workdir\ce5f760bb771\uvr\vocals.wav` (45.81 MB)

**Outputs**

- `<repo-root>\workdir\ce5f760bb771\svc\svc_vocals.wav` (22.90 MB)

- bytes_in=45.81 MB, bytes_out=22.90 MB

### VocalFX

**Inputs**

- `<repo-root>\workdir\ce5f760bb771\svc\svc_vocals.wav` (22.90 MB)

**Outputs**

- `<repo-root>\workdir\ce5f760bb771\fx\fx_pitch_svc_vocals.wav` (22.90 MB)

- bytes_in=22.90 MB, bytes_out=22.90 MB

### Mixer

**Inputs**

- `<repo-root>\workdir\ce5f760bb771\fx\fx_pitch_svc_vocals.wav` (22.90 MB)
- `<repo-root>\workdir\ce5f760bb771\uvr\instrumental.wav` (45.81 MB)

**Outputs**

- `<repo-root>\outputs\ce5f760bb771\cover.wav` (45.81 MB)

- bytes_in=68.71 MB, bytes_out=45.81 MB

### Export

**Inputs**

- `<repo-root>\outputs\ce5f760bb771\cover.wav` (45.81 MB)

**Outputs**

- `<repo-root>\outputs\ce5f760bb771\cover.mp3` (10.39 MB)

- bytes_in=45.81 MB, bytes_out=10.39 MB

## External Commands

Total captured commands: **4** (see `commands.log`)

| # | Tool | Stage | Duration (s) | Exit |
|---|------|-------|--------------|------|
| 1 | so-vits-svc | SVC | 29.649 | 0 |
| 2 | ffmpeg | VocalFX | 0.274 | 0 |
| 3 | ffmpeg | Mixer | 0.178 | 0 |
| 4 | ffmpeg | Export | 2.714 | 0 |

## Auto Analysis

- **[info]** 最耗时模块: SVC: SVC 耗时 29.67s，约占 Total 的 90.1%。 各阶段: SVC=29.67s, Export=2.72s, VocalFX=0.28s, Mixer=0.18s, UVR=0.04s, Prepare=0.00s
- **[info]** 检测到 3 次 ffmpeg 调用: 当前流水线可能对 VocalFX / Mixer / Export 分别调用 ffmpeg。若效果与导出可合并，存在减少进程启动与重复解码的空间（本阶段仅记录，不优化）。
- **[warning]** SVC 前段疑似重复/冷启动模型加载: SVC 前段 GPU Util 均值 4.4%，后段 51.7%。 每次 cover 若重新拉起 so-vits-svc 进程，模型会重复加载。
- **[info]** 存在可缓存/复用步骤（观察结论）: 无 VocalFX（pitch=0 且混响关闭）时可跳过中间 wav 落盘；常驻 SVC 推理服务可避免每次子进程冷启动加载模型

---

详细采样见 `profiling.json` / `metrics.csv`；问题清单见 `issues.md`；命令原文见 `commands.log`。
