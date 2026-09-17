# Cover Skill 三层架构设计（第一阶段）

> 状态：设计 / 接口冻结草案  
> 日期：2026-07-26  
> 约束：**现有 Pipeline / GUI / CLI / factory 业务代码本阶段零修改**  
> 目标：Hermes（及同类 Agent）可调用翻唱能力；GUI 继续走现有 `build_pipeline` → `Pipeline.run` 路径

---

## 1. 设计目标

| 目标 | 说明 |
|------|------|
| Pipeline 不变 | `core/pipeline.py`、各 `modules/*`、推理参数、ffmpeg 参数保持原样 |
| GUI 不变 | `MainWindow` / `PipelineWorker` 仍直接 `build_pipeline(cb)` + `JobContext` |
| Hermes 可调用 | 通过 Cover Skill 发现能力，经 Cover Service 提交任务、查进度、取结果 |
| 可演进 | UVR 常驻、GPU、结果缓存等落在 Service / Adapter 外围，不侵入 Pipeline |
| 单一真相源 | 真正执行翻唱的仍是现有 `Pipeline.run(JobContext) → JobResult` |

---

## 2. 三层定义

```
┌─────────────────────────────────────────────────────────┐
│  Cover Skill（Agent / Hermes 契约层）                      │
│  - SKILL.md：何时用、参数语义、输出约定                     │
│  - 不持有模型；只调用 Cover Service API                    │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTP / CLI / SDK
┌───────────────────────────▼─────────────────────────────┐
│  Cover Service（应用服务层）                               │
│  - 任务队列 / 状态机 / 进度广播 / 产物索引                   │
│  - 可选：UVR worker 生命周期、结果缓存策略（未来）            │
│  - 不实现分离/换声/混音算法                                 │
└───────────────────────────┬─────────────────────────────┘
                            │ 仅经 Adapter
┌───────────────────────────▼─────────────────────────────┐
│  Pipeline Adapter（适配层）                               │
│  - CoverRequest → JobContext                             │
│  - Pipeline.run(...)                                     │
│  - JobResult → CoverResult                               │
│  - 进度 JobManager callback → CoverProgress 事件          │
└───────────────────────────┬─────────────────────────────┘
                            │ 现有 API（只读依赖）
┌───────────────────────────▼─────────────────────────────┐
│  现有 Pipeline（禁止本阶段修改）                            │
│  factory.build_pipeline → UVR → SVC → VocalFX → Mix → MP3 │
└─────────────────────────────────────────────────────────┘

并行保留（不经过 Skill/Service）：

GUI / CLI / Flask(api.py)
    → build_pipeline()
    → Pipeline.run(JobContext)
```

**硬规则：** 只有 **Pipeline Adapter** 允许 `import aivoice_studio.factory` / `Pipeline` / `JobContext`。  
Cover Skill **禁止** 直接调 Pipeline。

---

## 3. 调用关系与边界

### 3.1 Hermes 路径（新）

```
Hermes Agent
  → 读取 Cover Skill（SKILL.md）
  → cover.create_job / cover.run / cover.get_status
  → Cover Service
  → Pipeline Adapter
  → Pipeline.run
  → 返回 CoverResult（mp3/wav 路径 + metadata）
```

### 3.2 GUI 路径（保持现状）

```
MainWindow.PipelineWorker
  → build_pipeline(callback)
  → JobContext(...)
  → pipeline.run(...)
  → HistoryStore / LibraryScanner
```

第一阶段 **不要求** GUI 改走 Cover Service。  
第二阶段可选：GUI 改为 Service 客户端以共享队列/UVR 常驻（非本阶段范围）。

### 3.3 与现有 Flask `/api/cover` 的关系

| 入口 | 阶段策略 |
|------|----------|
| `server/api.py` | 继续现状；后续可薄封装为 Cover Service 的 HTTP 前端之一 |
| Cover Service HTTP | 新建独立端口或 `/v1/cover/*`，避免破坏现有网页版 |

---

## 4. 分层职责

### L1 — Cover Skill

**是什么：** Agent 可加载的技能说明书 + 工具绑定说明。  
**不是什么：** 不跑模型、不读 `.venv`、不拼 ffmpeg。

职责：

1. 声明触发条件（「用户要翻唱 / cover / so-vits」）
2. 规范化参数（音频路径、模型名、pitch、reverb）
3. 规定调用 Cover Service 的步骤与错误处理
4. 规定如何向用户呈现结果路径与失败原因

交付物（本阶段仅文档草稿）：

- `skill/SKILL.md`（契约正文，与本文件同级的 `skill/` 目录）
- 工具 JSON Schema（见 `interfaces/`）

### L2 — Cover Service

**是什么：** 本地（或同机）任务服务。  
**不是什么：** 不是 Pipeline，不是 UVR 实现本身。

职责：

1. `create_job` / `run_job` / `get_job` / `cancel_job`（cancel 第一阶段可声明为 best-effort）
2. 持久化任务状态（内存即可起步，文件 JSON 可选）
3. 进度事件：映射现有 `JobState`（uvr/svc/mixing/exporting/done/failed）
4. 保证同机串行 GPU（配置项 `gpu_serial` 语义在此落实，Pipeline 仍无感）
5. 未来挂载：UVR Persistent Worker、结果缓存 — **只在本层扩展**

### L3 — Pipeline Adapter

**是什么：** 现有 Pipeline 的唯一防腐层。  
**不是什么：** 不复制 UVR/SVC/Mixer 逻辑。

职责：

1. 把 `CoverRequest` 转成现有 `JobContext`
2. 调用 `build_pipeline(progress_callback)` + `pipeline.run(job)`
3. 把 `JobResult` 转成 `CoverResult`
4. 把 `JobState` 进度转成 `CoverProgressEvent`
5. 捕获异常 → 结构化 `CoverError`（不改变 Pipeline 内部失败语义）

---

## 5. 核心数据模型（接口）

详见 `interfaces/cover_api.schema.json`。摘要如下。

### CoverRequest

| 字段 | 类型 | 对应 JobContext | 说明 |
|------|------|-----------------|------|
| `input_audio` | string (path/uri) | `input_audio` | 本地绝对路径优先 |
| `model_name` | string | `model_name` | 如 `G_16000` |
| `pitch` | int -12..12 | `pitch` | |
| `reverb` | string | `reverb` | `关闭`/`录音棚`/`现场`/`大教堂` |
| `f0_method` | string | `f0_method` | 默认 `rmvpe` |
| `export_mp3` | bool | `export_mp3` | 默认 true |
| `accompaniment` | string | `accompaniment` | 可选 |
| `workdir` | string? | `workdir` | 缺省用 config runtime |
| `output_dir` | string? | `output_dir` | 缺省用 config runtime |
| `client` | string | — | `hermes` / `gui` / `cli` / `api`（仅审计） |
| `request_id` | string? | — | 幂等键（可选） |

### CoverProgressEvent

| 字段 | 类型 | 来源 |
|------|------|------|
| `job_id` | string | Service 分配 |
| `stage` | enum | `JobState.value` |
| `percent` | int 0..100 | JobManager |
| `message` | string | JobManager |
| `elapsed_s` | float? | Service 侧计时 |

### CoverResult

| 字段 | 类型 | 来源 |
|------|------|------|
| `success` | bool | `JobResult.success` |
| `job_id` | string | |
| `wav_path` | string? | `JobResult.wav_path` |
| `mp3_path` | string? | `JobResult.mp3_path` |
| `error` | string? | `JobResult.error` |
| `stages_timing` | object? | 可选；未来接 profiling |
| `model_name` / `pitch` / `reverb` | | 回显请求 |

### CoverJob（Service 状态机）

```
queued → running → succeeded
                 ↘ failed
queued → cancelled   (可选，第一阶段可未实现)
```

---

## 6. Cover Service API（接口草案）

传输：本机 HTTP `127.0.0.1`（默认端口建议 `17890`，可配置）。  
亦提供等价 CLI：`aivoice-cover ...`（实现阶段再加 entry point）。

### `POST /v1/cover/jobs`

创建任务并可选择同步等待。

请求体：`CoverRequest` + `{ "wait": false }`

响应：

```json
{
  "job_id": "e49d3ec8f4e6",
  "status": "queued",
  "poll_url": "/v1/cover/jobs/e49d3ec8f4e6"
}
```

### `POST /v1/cover/jobs/{job_id}/run`

若创建与执行为两步；也可合并为 create 时 `wait=true` 直接跑完。

### `GET /v1/cover/jobs/{job_id}`

返回 `CoverJob` 快照（status + 最新 progress + result）。

### `GET /v1/cover/jobs/{job_id}/events`

可选 SSE：推送 `CoverProgressEvent`。

### `GET /v1/cover/models`

列出可用 SVC 模型（可委托现有 `ModelConfigMap`，实现阶段再接）。

### `GET /v1/health`

进程存活；可选报告 UVR worker 是否已加载（未来）。

**同步便捷接口（给 Hermes 省轮询）：**

### `POST /v1/cover/run`

`CoverRequest` → 阻塞至完成 → `CoverResult`  
（内部仍走 job 状态机，便于日志与取消扩展）

---

## 7. Pipeline Adapter 接口（伪代码契约）

> 本阶段仅契约；实现阶段新建模块，例如  
> `src/aivoice_studio/cover/adapter.py`（**不修改** `pipeline.py`）

```text
protocol PipelineAdapter:
    def run(request: CoverRequest, on_progress: Callable[[CoverProgressEvent], None] | None) -> CoverResult
```

映射规则（冻结）：

1. `Path(request.input_audio)` → `JobContext.input_audio`
2. 未提供 `workdir`/`output_dir` 时，从现有 `ConfigLoader().load()["runtime"]` 读取并 `resolve_path`
3. `build_pipeline(callback)` 的 callback：`(JobState, percent, message)` → `CoverProgressEvent`
4. `JobResult` 字段原样映射；`success=False` 不抛异常（与现 Pipeline 一致），由 Service 标 `failed`
5. Adapter **不得** 改变 pitch/reverb 语义，不得跳过 UVR，不得改命令模板

---

## 8. Cover Skill 行为契约（给 Hermes）

完整正文见 `skill/SKILL.md`。要点：

1. 需要本地 Cover Service 已启动（或 Skill 指引启动命令）
2. 优先调用 `POST /v1/cover/run`（同步）
3. 输入必须是 Agent 可访问的本地音频路径
4. 成功：向用户返回 `mp3_path`（及可选 `wav_path`）
5. 失败：返回 `error` 原文 + 建议查看 `logs/pipeline.log`
6. 禁止 Skill 内直接 `subprocess` 调 `audio-separator` / `inference_main.py`

---

## 9. 目录规划（实现阶段才落代码；本阶段仅文档）

```
design/cover_skill/
  ARCHITECTURE.md          ← 本文件
  skill/SKILL.md           ← Hermes/Agent Skill 契约
  interfaces/
    cover_api.schema.json  ← JSON Schema
    openapi.yaml           ← OpenAPI 3 草案
    python_protocols.md    ← Python Protocol 文本契约

未来实现（非本阶段）：
src/aivoice_studio/cover/
  __init__.py
  service.py               ← Cover Service
  adapter.py               ← Pipeline Adapter
  api.py                   ← HTTP
  models.py                ← dataclass DTO
```

业务目录 **保持不动**：`core/pipeline.py`、`ui/main_window.py`、`factory.py`、`cli.py`。

---

## 10. 演进路线（不在本阶段实施）

| 阶段 | 内容 | 触及层 |
|------|------|--------|
| P0 本文档 | 设计 + 接口 | design/ only |
| P1 | Adapter + 同步 Service + `/v1/cover/run` | cover/* 新模块 |
| P2 | Hermes Skill 安装到 skills 目录并联调 | skill + Service |
| P3 | UVR Persistent Worker 挂到 Service | Service 外围 |
| P4 | GUI 可选改为 Service 客户端 | UI（自愿） |

---

## 11. 非目标（第一阶段明确不做）

- 修改 Pipeline / GUI / CLI / 现有 Flask 网页版行为
- 实现 UVR GPU / 常驻 worker
- 合并 pitch 双重处理等问题修复
- 要求 Hermes 与 GUI 共享同一进程

---

## 12. 验收标准（设计阶段）

- [x] 三层职责无重叠、依赖单向：Skill → Service → Adapter → Pipeline
- [x] GUI 现有调用路径在文档中明确「保留、不改」
- [x] Hermes 调用路径有 API + Skill 契约
- [x] `CoverRequest`/`CoverResult` 与 `JobContext`/`JobResult` 字段映射表完整
- [ ] 实现代码 — **故意不在本阶段提交**

---

## 13. 风险与对策

| 风险 | 对策 |
|------|------|
| 双入口（GUI 直连 vs Service）进度/历史不一致 | 第一阶段接受；P4 再统一 |
| Service 未启动导致 Hermes 失败 | Skill 中写明 health check 与启动命令 |
| Adapter 被绕过直接改 Pipeline | Code review 规则：封面能力只许经 Adapter |
| 与 profiling 钩子冲突 | Adapter 仍调 `Pipeline.run`，现有 profiling 自动生效 |
