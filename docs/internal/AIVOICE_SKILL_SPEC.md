# AIVOICE Skill Specification

> Phase: P3 — Hermes Skill Contract（仅设计，无实现）  
> Date: 2026-07-26  
> Binding target: CoverService → PipelineAdapter → Pipeline（现有）

---

## 1. Skill 名称

| 字段 | 值 |
|------|-----|
| **Skill ID** | `aivoice-cover` |
| **Display Name** | AI Cover Studio / AIVOICE Cover |
| **Short name** | `aivoice` |
| **Version** | `0.1.0-design` |

Agent 触发别名（自然语言）：翻唱、AI cover、换声、so-vits、生成 cover.mp3。

---

## 2. 能力描述

### 做什么

在**本机**对一首输入音频执行完整 AI 翻唱流水线，输出 WAV/MP3：

```text
输入音频 → 人声分离(UVR) → 音色转换(SVC) → 可选人声效果 → 混音 → 导出 MP3
```

### 不做什么

- 不训练模型  
- 不直接暴露 UVR/SVC/ffmpeg CLI  
- 不修改 GUI  
- 不替代桌面端日常使用（GUI 仍可独立使用 CoverService）

### 调用原则

Hermes **只**通过本 Skill 契约访问 AIVOICE；禁止绕过调用 `audio-separator`、`inference_main.py`、`core.pipeline`。

---

## 3. 输入参数

对应现有 DTO：`CoverRequest`（`aivoice_studio.cover.domain.request`）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `input_audio` | string (path) | 是 | — | 本机绝对路径；Hermes 可读写 |
| `model_name` | string | 是 | — | SVC 检查点名，如 `G_16000` |
| `pitch` | int | 否 | `0` | 半音，范围 [-12, 12] |
| `reverb` | string | 否 | `关闭` | `关闭` \| `录音棚` \| `现场` \| `大教堂` |
| `f0_method` | string | 否 | `rmvpe` | 与现网 SVC 一致 |
| `export_mp3` | bool | 否 | `true` | 是否导出 MP3 |
| `accompaniment` | string | 否 | `""` | 可选外部伴奏路径 |
| `workdir` | string\|null | 否 | config | 可选；默认 runtime.workdir |
| `output_dir` | string\|null | 否 | config | 可选；默认 runtime.output_dir |
| `client` | string | 否 | `hermes` | 审计字段；Skill 应传 `hermes` |
| `request_id` | string\|null | 否 | null | 幂等键（未来异步任务用） |

### Skill 工具面（逻辑操作）

| Tool / Operation | 语义 | 同步/异步 |
|------------------|------|-----------|
| `aivoice.cover.run` | 执行一次翻唱至完成 | 同步（P3 首选） |
| `aivoice.cover.submit` | 提交任务立即返回 `job_id` | 异步（未来） |
| `aivoice.cover.status` | 查询任务状态/进度 | 异步配套 |
| `aivoice.cover.models` | 列出可用模型 | 同步 |
| `aivoice.cover.health` | 服务是否可用 | 同步 |

P3 契约以 **`aivoice.cover.run`** 为最小可用能力；其余为扩展。

---

## 4. 输出结果

对应现有 DTO：`CoverResult`。

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | bool | 是否成功 |
| `job_id` | string | 任务/输出目录 ID |
| `wav_path` | string\|null | `cover.wav` 绝对路径 |
| `mp3_path` | string\|null | `cover.mp3` 绝对路径（主交付物） |
| `error` | string\|null | 失败时的错误信息（Pipeline 原文语义） |
| `model_name` | string\|null | 回显 |
| `pitch` | int\|null | 回显 |
| `reverb` | string\|null | 回显 |
| `stages_timing` | object\|null | 可选；各阶段秒数（未来/profiling） |

### Hermes 向用户呈现

- 成功：优先给出 `mp3_path`（可选提及 `wav_path`、`job_id`）  
- 失败：给出 `error`；可提示查看 `logs/pipeline.log`

### 进度事件（可选订阅）

对应 `ProgressEvent`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `job_id` | string | |
| `stage` | enum | 见状态模型 |
| `percent` | int 0–100 | |
| `message` | string | |
| `elapsed_s` | float\|null | |

---

## 5. 任务状态模型

### 5.1 流水线阶段（Progress / Timeline）

与现有 `Stage` / `JobState` 对齐：

| stage | 含义 |
|-------|------|
| `pending` | 已受理未开始 |
| `uvr` | 人声分离 |
| `svc` | 音色转换 |
| `mixing` | 混音（可含人声效果阶段消息） |
| `exporting` | 导出 MP3 |
| `done` | 成功结束 |
| `failed` | 失败结束 |

### 5.2 任务生命周期（未来 Job 对象）

| status | 含义 |
|--------|------|
| `queued` | 已创建，等待执行 |
| `running` | 正在跑 Pipeline |
| `succeeded` | `CoverResult.success == true` |
| `failed` | 业务失败或异常终止 |
| `cancelled` | 已取消（可选，未实现） |

同步 `run`：对 Hermes 可折叠为一次调用，内部仍产生 `job_id` + 终态 `succeeded|failed`。

```text
[submit] queued → running → succeeded
                         ↘ failed
```

---

## 6. 错误模型

### 6.1 传输/契约层（Skill ↔ Service）

| code | HTTP（若走 HTTP） | 何时 | Hermes 行为 |
|------|-------------------|------|-------------|
| `INVALID_REQUEST` | 400 | 缺参、路径非法、pitch 越界 | 修正参数后重试 |
| `SERVICE_UNAVAILABLE` | 503 | 服务未启动/健康检查失败 | 提示启动 AIVOICE Cover Service |
| `NOT_FOUND` | 404 | `job_id` 不存在（status 查询） | 勿死循环轮询 |
| `TIMEOUT` | 504/客户端 | 同步 run 超时 | 改异步或提高超时 |

### 6.2 业务层（写入 `CoverResult`）

与现网 Pipeline 一致：多数阶段失败为 **`success=false` + `error` 字符串**，不强制抛异常。

| 场景 | 典型 `error` 语义 | 说明 |
|------|-------------------|------|
| UVR 失败 | 含 `UVR` / 输出找不到 | 不吞；原样返回 |
| SVC 失败 | 含 `SVC` / model / pth | 不吞 |
| Export 失败 | 含 `MP3` / export | 不吞 |
| 输入不存在 | File not found 类 | 可表现为异常或 failed result |
| ffmpeg 失败 | ProcessError 文本 | 不改变语义 |

### 6.3 Skill 层错误包装（建议）

```json
{
  "ok": false,
  "error": {
    "code": "COVER_FAILED",
    "message": "<CoverResult.error 原文>",
    "job_id": "124d42a42f8b",
    "retryable": false
  }
}
```

成功：

```json
{
  "ok": true,
  "result": {
    "job_id": "...",
    "mp3_path": "...",
    "wav_path": "..."
  }
}
```

`retryable` 仅作建议；P3 不实现重试策略。

---

## 7. 非功能约定

| 项 | 约定 |
|----|------|
| 执行位置 | 本地（同机或可达的 Cover Service） |
| 超时建议 | 同步 run ≥ 10–15 分钟（含 CPU UVR） |
| 并发 | 默认串行 GPU；多任务需 Service 层队列（未来） |
| 密钥 | 无云端 API Key；飞书等另案 |

---

## 8. 与代码的映射（只读）

| Skill 概念 | 现有代码 |
|------------|----------|
| 输入 | `cover.domain.request.CoverRequest` |
| 输出 | `cover.domain.result.CoverResult` |
| 进度 | `cover.domain.progress.ProgressEvent` |
| 阶段 | `cover.domain.stage.Stage` |
| 执行 | `CoverService.run`（当前仅同步） |

P3 **不修改**上述代码；仅冻结契约供后续 Hermes 接入实现使用。
