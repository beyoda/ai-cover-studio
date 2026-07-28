# Job System Design

> Phase: P4.0 — Service Expansion Design（仅设计，无代码）  
> 目标：为 CoverService 增加可查询、可异步的 Job 抽象，而不修改 `run()` / Pipeline

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| Agent-friendly | Hermes 可 `submit` 后轮询，不必长时间阻塞工具调用 |
| 兼容同步 | 现有 `CoverService.run()` 语义不变；内部可复用同一执行核 |
| 单一执行核 | 真正跑翻唱仍只经 `PipelineAdapter.run` → `Pipeline` |
| 可观测 | 状态、阶段、进度、错误、结果均可按 `job_id` 查询 |

---

## 2. Job 模型

### 2.1 CoverJob（逻辑实体）

| 字段 | 类型 | 说明 |
|------|------|------|
| `job_id` | string | 主键；与输出目录名对齐（现有 12 位 hex 风格可延续） |
| `request_id` | string\|null | 客户端幂等键（来自 `CoverRequest.request_id`） |
| `client` | string | `hermes` / `gui` / `cli` / `api` / … |
| `status` | JobStatus | 见生命周期 |
| `request` | CoverRequest | 不可变快照（创建时拷贝） |
| `stage` | Stage\|null | 当前流水线阶段 |
| `progress` | ProgressSnapshot\|null | 最新进度 |
| `result` | CoverResult\|null | 终态成功/失败结果 |
| `error` | CoverError\|null | 结构化错误（可与 result.error 并存） |
| `created_at` | datetime | |
| `queued_at` | datetime\|null | |
| `started_at` | datetime\|null | |
| `finished_at` | datetime\|null | |
| `cancel_requested` | bool | 协作式取消标志 |

### 2.2 存储

| 阶段 | 建议 |
|------|------|
| v1 | 进程内 dict + 可选 JSON 落盘 `workdir/jobs/{job_id}.json` |
| v2 | SQLite（多进程 HTTP worker 时） |

**不**把 Job 表写进 Pipeline。

---

## 3. 状态生命周期（JobStatus）

```text
                 submit()
                    │
                    ▼
                 queued
                    │
         ┌──────────┼──────────┐
         │          │          │
         ▼          ▼          ▼
     cancelled   running    (极少：直接 failed，如校验失败)
                    │
         ┌──────────┼──────────┐
         ▼          ▼          ▼
    succeeded    failed    cancelled
```

| status | 含义 | 终态？ |
|--------|------|--------|
| `queued` | 已受理，等待执行槽 | 否 |
| `running` | 正在 `PipelineAdapter.run` | 否 |
| `succeeded` | `CoverResult.success == true` | 是 |
| `failed` | 业务失败或未捕获异常转失败 | 是 |
| `cancelled` | 取消生效（未启动或协作中断） | 是 |

规则：

- 终态不可再变。  
- `run()` 同步路径：可创建 Job，状态快速 `queued→running→succeeded|failed`，对调用方仍只返回 `CoverResult`。  
- `cancel()`：若仍为 `queued` → 立即 `cancelled`；若 `running` → 置 `cancel_requested`（见 cancel 设计）；已终态 → 幂等返回当前状态。

---

## 4. Stage 定义

与现有 `cover.domain.stage.Stage` / Pipeline `JobState` **完全对齐**，禁止另造名称：

| stage | 含义 |
|-------|------|
| `pending` | Job 已建、流水线尚未进入 UVR |
| `uvr` | 人声分离 |
| `svc` | 音色转换 |
| `mixing` | 混音（含 VocalFX 提示消息时仍可用此 stage 或沿用 Pipeline 上报） |
| `exporting` | 导出 MP3 |
| `done` | 流水线成功完成（通常伴随 JobStatus.succeeded） |
| `failed` | 流水线失败（通常伴随 JobStatus.failed） |

说明：`JobStatus` 描述任务生命周期；`stage` 描述 Pipeline 内部进展。二者同时暴露给 Agent。

---

## 5. Progress 模型

复用并固化现有 `ProgressEvent`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `job_id` | string | |
| `stage` | Stage | |
| `percent` | int 0–100 | 与现网 JobManager 一致 |
| `message` | string | |
| `elapsed_s` | float\|null | 自任务开始或阶段开始（实现时二选一并文档化；GUI 已用阶段内计时） |

### ProgressSnapshot（status 查询用）

```text
ProgressSnapshot = 最新一次 ProgressEvent + updated_at
```

异步执行时：Adapter 的 `on_progress` 写入 Job 的 `progress` 字段，供 `status()` 读取。

---

## 6. Error 模型

### 6.1 CoverError（结构化）

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | string | 稳定错误码 |
| `message` | string | 人类可读；尽量保留 Pipeline 原文 |
| `stage` | Stage\|null | 失败时所在阶段 |
| `retryable` | bool | 建议是否可重试 |
| `details` | object\|null | 可选诊断 |

### 6.2 建议错误码

| code | 典型场景 | retryable |
|------|----------|-----------|
| `INVALID_REQUEST` | 参数/路径非法 | false |
| `UVR_FAILED` | 分离失败 | true（环境类）/ false（输入类） |
| `SVC_FAILED` | 换声/模型失败 | 视 message |
| `EXPORT_FAILED` | ffmpeg/导出 | true |
| `CANCELLED` | 用户取消 | false |
| `INTERNAL` | 未分类异常 | true |

映射原则：Pipeline 返回的 `JobResult.error` 字符串 **原样进入** `message`；`code` 由 Service 层启发式分类，不改 Pipeline。

---

## 7. Result 模型

复用现有 `CoverResult`：

| 字段 | 说明 |
|------|------|
| `success` | |
| `job_id` | 与 CoverJob.job_id 相同 |
| `wav_path` / `mp3_path` | |
| `error` | 字符串；与 CoverError.message 对齐 |
| `model_name` / `pitch` / `reverb` | 回显 |
| `stages_timing` | 可选 |

终态写入：

- `succeeded` → `result.success=true`，路径有效  
- `failed` → `result.success=false`，`error`/`CoverError` 填充  
- `cancelled` → `result` 可为 null，或 `success=false` + `code=CANCELLED`

---

## 8. 与现有类型关系

```text
CoverRequest  ──创建时快照──► CoverJob.request
ProgressEvent ──更新────────► CoverJob.progress
CoverResult   ──终态────────► CoverJob.result
Stage         ──对齐────────► CoverJob.stage
```

`cover.domain.job.JobContext`（request + job_id）可视为 CoverJob 的轻量视图；完整 Job System 升级为 CoverJob 即可。

---

## 9. 非目标（P4.0）

- 不实现分布式调度  
- 不改 Pipeline 内部状态机  
- 不在本设计阶段写代码  
