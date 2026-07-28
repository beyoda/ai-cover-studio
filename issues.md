# Profiling Issues

> 本文件仅记录观察结论，**不包含修复或优化**。

生成时间: 2026-07-28T10:19:24.251+08:00

## 1. [INFO] 最耗时模块: SVC

- 类别: `bottleneck`
- 详情: SVC 耗时 29.67s，约占 Total 的 90.1%。 各阶段: SVC=29.67s, Export=2.72s, VocalFX=0.28s, Mixer=0.18s, UVR=0.04s, Prepare=0.00s

## 2. [INFO] 检测到 3 次 ffmpeg 调用

- 类别: `repeated_ffmpeg`
- 详情: 当前流水线可能对 VocalFX / Mixer / Export 分别调用 ffmpeg。若效果与导出可合并，存在减少进程启动与重复解码的空间（本阶段仅记录，不优化）。

## 3. [WARNING] SVC 前段疑似重复/冷启动模型加载

- 类别: `model_load`
- 详情: SVC 前段 GPU Util 均值 4.4%，后段 51.7%。 每次 cover 若重新拉起 so-vits-svc 进程，模型会重复加载。

## 4. [INFO] 存在可缓存/复用步骤（观察结论）

- 类别: `cache_opportunity`
- 详情: 无 VocalFX（pitch=0 且混响关闭）时可跳过中间 wav 落盘；常驻 SVC 推理服务可避免每次子进程冷启动加载模型
