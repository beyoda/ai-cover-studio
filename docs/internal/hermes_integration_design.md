# Hermes × AIVOICE 集成设计

> Phase: P3 — 仅设计  
> 依赖契约：`AIVOICE_SKILL_SPEC.md`  
> 实现栈（只读依赖）：CoverService → PipelineAdapter → Pipeline

---

## 1. 目标架构

```
Hermes Agent
    ↓  (Skill 工具调用 / 自然语言触发)
AIVOICE Skill（契约层：aivoice-cover）
    ↓  (本机 IPC：推荐 HTTP 127.0.0.1，或同进程 SDK)
CoverService
    ↓
PipelineAdapter
    ↓
Pipeline（Legacy，不修改）
    ↓
UVR / SVC / ffmpeg（子进程）
```

### 边界

| 层 | 职责 | 禁止 |
|----|------|------|
| Hermes | 理解用户意图、填参、展示结果 | 拼 CLI、改模型 |
| Skill | 参数校验、调用 Service、错误包装 | 实现分离/推理 |
| CoverService | 编排入口（及未来 job/状态） | UVR/SVC 细节 |
| Adapter | DTO ↔ JobContext / JobResult | 改 Pipeline 逻辑 |
| Pipeline | 现有翻唱业务 | 感知 Hermes |

GUI 已走 CoverService；Hermes 与 GUI **共享同一业务入口**，互不修改对方。

---

## 2. 调用时序（同步 run — P3 最小路径）

```text
用户: 「用 G_16000 翻唱 示例曲目.mp3」
        │
        ▼
┌───────────────┐
│ Hermes        │ 解析意图 → 选择 Skill aivoice-cover
└───────┬───────┘
        │ aivoice.cover.health（可选）
        ▼
┌───────────────┐
│ Skill         │ GET /v1/health 或 SDK health()
└───────┬───────┘
        │ ok
        │ aivoice.cover.run(CoverRequest)
        ▼
┌───────────────┐
│ CoverService  │ run(request, on_progress?)
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ PipelineAdapter│ CoverRequest → Pipeline JobContext
└───────┬───────┘
        │ build_pipeline + Pipeline.run
        ▼
┌───────────────┐
│ Pipeline      │ UVR → SVC → FX → Mix → Export
└───────┬───────┘
        │ JobResult
        ▼
┌───────────────┐
│ Adapter       │ → CoverResult
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ Skill         │ 包装 { ok, result|error }
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ Hermes        │ 向用户报告 mp3_path 或 error
└───────────────┘
```

进度（若 Hermes 支持流式工具反馈）：

```text
Pipeline JobManager
  → Adapter ProgressEvent
  → CoverService 回调
  → Skill 转发 stage/percent/message
  → Hermes UI/日志
```

阶段名保持：`uvr` / `svc` / `mixing` / `exporting` / `done` / `failed`。

---

## 3. 调用时序（异步 — 未来扩展）

```text
Hermes
  → Skill aivoice.cover.submit(CoverRequest)
  → CoverService.create_job → job_id (queued)
  → 立即返回 job_id

Hermes 轮询或订阅
  → Skill aivoice.cover.status(job_id)
  → CoverService.get_job
  → { status, progress, result? }

终态 succeeded/failed 后
  → 读取 result.mp3_path
```

P3 **不实现**异步；契约预留 `submit` / `status`，避免 Skill 与 Service 日后撕裂。

---

## 4. 传输选项

| 选项 | 说明 | 建议 |
|------|------|------|
| **A. 本地 HTTP** | `http://127.0.0.1:17890/v1/cover/run`（见既有 openapi 草案） | Hermes 跨进程首选 |
| **B. Python SDK** | 同解释器 `CoverService().run(...)` | 仅当 Hermes 宿主即 AIVOICE venv |
| **C. CLI wrapper** | `aivoice-cover run --input ...` | 备选；仍应调 CoverService |

Skill 文档应对 Hermes 隐藏 B/C 细节，统一暴露逻辑 tool 名。

---

## 5. Hermes 侧伪流程

```text
1. IF user wants local AI cover:
2.   ENSURE health OK else ASK user to start Cover Service
3.   RESOLVE input_audio to absolute path
4.   RESOLVE model_name (ask user or list models)
5.   CALL aivoice.cover.run with client="hermes"
6.   IF ok: PRESENT mp3_path
7.   ELSE: PRESENT error.message (verbatim business text)
8. NEVER call audio-separator / so-vits / ffmpeg directly
```

---

## 6. 与 GUI 共存

```text
                    ┌── GUI PipelineWorker ──┐
                    │                        │
Hermes → Skill ─────┴→ CoverService → Adapter → Pipeline
```

- 同一 Adapter / Pipeline  
- 不同 `client` 字段：`gui` vs `hermes`  
- 不在本阶段改 GUI

---

## 7. 安全与运维（设计注意）

- 仅监听 localhost（默认）  
- 输入路径限制在用户授权目录（实现阶段再定）  
- 长耗时：同步调用需长超时（CPU UVR 可达数分钟）  
- 日志：沿用 `logs/pipeline.log` + 现有 profiling 钩子

---

## 8. 实现阶段切分（非本阶段）

| 阶段 | 内容 |
|------|------|
| P3（本阶段） | 契约与设计文档 |
| P3.x | CoverService HTTP façade（若选 HTTP） |
| P4 | Hermes Skill 包落地与联调 |
| 其后 | 异步 job / 状态查询 |

**本文件不含代码变更。**
