# CoverService API v2 Design

> Phase: P4.0 — 仅设计  
> 约束：**不修改现有 `CoverService.run()` 的签名与同步语义**  
> 执行核：仍仅 `PipelineAdapter` → `Pipeline`

---

## 1. 设计原则

1. **Additive**：新增方法，不破坏 GUI/P2 已依赖的 `run()`。  
2. **同一执行核**：`submit` 最终调用的仍是 `adapter.run(...)`。  
3. **Skill 对齐**：对应 `AIVOICE_SKILL_SPEC` 的 `submit` / `status` / `result` /（可选）`cancel`。  
4. **可选 HTTP**：方法可先 Python SDK，再映射到 `/v2/...`（本设计两者同构）。

---

## 2. 现有 API（保持不变）

```text
CoverService.run(request: CoverRequest, *, on_progress=None) -> CoverResult
```

行为：阻塞至完成；内部可（实现阶段选择）：

- **A.** 直接 `adapter.run`（现状）  
- **B.** `submit` + 同线程等待终态（统一走 Job 表，仍对外同步）

无论 A/B，对 GUI **观察不到差异**。

---

## 3. 新增 API 一览

| 方法 | 作用 | 返回 |
|------|------|------|
| `submit(request) -> job_id` | 异步提交 | `str` |
| `status(job_id) -> JobStatusView` | 查询状态/进度 | 视图对象 |
| `result(job_id) -> CoverResult` | 取终态结果 | `CoverResult`（未完成则错误） |
| `cancel(job_id) -> CancelOutcome` | 请求取消 | 结果枚举/对象 |
| `health() -> HealthView` | 就绪检查（建议一并加） | |
| `list_models() -> list[str]` | 模型列表（建议一并加） | |

以下详细定义前四个。

---

## 4. `submit(request) -> job_id`

### 语义

1. 校验 `CoverRequest`（路径存在、pitch 范围等）。  
2. 分配 `job_id`（若 `request_id` 命中未终态任务则返回已有 id — 幂等）。  
3. Job 写入 store，`status=queued`。  
4. 将任务交给执行槽（线程池 size=1 起步，保证 GPU 串行）。  
5. **立即返回** `job_id`，不阻塞到 Pipeline 结束。

### 伪签名

```text
def submit(self, request: CoverRequest) -> str: ...
```

### 错误

- 校验失败 → 抛 `InvalidRequest` 或返回 failed Job（推荐抛，避免幽灵 job_id）。

### 与 `run()` 关系

```text
run()  =  可选实现为：jid = submit(req); wait_until_terminal(jid); return result(jid)
         或继续直接 adapter.run（零行为变化）
```

**禁止**为迁就 `submit` 而改变 `run()` 的返回类型或参数表。

---

## 5. `status(job_id) -> JobStatusView`

### JobStatusView

| 字段 | 类型 | 说明 |
|------|------|------|
| `job_id` | string | |
| `status` | JobStatus | queued/running/succeeded/failed/cancelled |
| `stage` | Stage\|null | |
| `progress` | ProgressEvent\|null | 最新进度 |
| `created_at` / `started_at` / `finished_at` | datetime\|null | |
| `cancel_requested` | bool | |

不含大结果体（路径放 `result()`）。

### 伪签名

```text
def status(self, job_id: str) -> JobStatusView: ...
```

### 错误

- 未知 `job_id` → `NotFound`

### Hermes 用法

短轮询（如 1–2 s）或未来 SSE；直到 `status in {succeeded, failed, cancelled}`。

---

## 6. `result(job_id) -> CoverResult`

### 语义

- 仅当 `status in {succeeded, failed}`（以及约定 cancelled 时返回失败形结果）时返回完整 `CoverResult`。  
- `queued` / `running` → `ResultNotReady`（或返回 `None` + 明确文档；推荐异常/错误码，避免与 failed 混淆）。

### 伪签名

```text
def result(self, job_id: str) -> CoverResult: ...
```

成功时：`mp3_path` / `wav_path` 与现网一致。  
失败时：`success=false`，`error` 保留 Pipeline 语义。

---

## 7. `cancel(job_id) -> CancelOutcome`

### CancelOutcome

| 值 | 含义 |
|----|------|
| `cancelled` | 已在 queued 阶段取消，或 running 已成功协作停止 |
| `cancel_requested` | 已通知 running 任务，等待其退出 |
| `already_finished` | 已是终态，无操作 |
| `not_found` | 无此 job |

### 协作式取消（现实约束）

Pipeline **当前无取消 API**。P4.0 设计：

1. `queued`：从队列移除 → `cancelled`（强保证）。  
2. `running`：设 `cancel_requested=True`；执行包装在 Adapter 调用外层，**下一 progress 回调**检查标志则不再继续——但 Pipeline 内部仍可能跑完当前子进程。  
3. 真正的硬取消（杀 audio-separator/SVC 子进程）列为 **Worker/演进阶段**，本设计不要求立刻具备。

**不修改 Pipeline 源码**的前提下，cancel 对 running 为 best-effort。

---

## 8. HTTP 映射（可选，v2）

| SDK | HTTP |
|-----|------|
| `submit` | `POST /v2/cover/jobs` → `{ job_id }` |
| `status` | `GET /v2/cover/jobs/{id}` |
| `result` | `GET /v2/cover/jobs/{id}/result` |
| `cancel` | `POST /v2/cover/jobs/{id}/cancel` |
| `run`（保留） | `POST /v1/cover/run` 或 `POST /v2/cover/run`（同步） |

`/v1` 与 `/v2` 可并存；GUI 继续进程内 `run()`，不必上 HTTP。

---

## 9. 并发与执行槽

| 配置 | 默认建议 |
|------|----------|
| 最大并行 Pipeline | **1**（GPU 串行，对齐 config `gpu_serial` 意图） |
| 队列长度 | 有限（如 8）；满则 `submit` 拒绝或阻塞策略二选一（文档化） |

`run()` 与 `submit` 共享同一执行槽，避免 GUI 与 Hermes 双开打爆显存。

---

## 10. 非目标

- 不在本阶段改 GUI 去调 `submit`  
- 不删除或改名 `run`  
- 不实现分布式多机队列  
- 不改 Pipeline / 模型 / Hermes 运行时（仅预留对接）

---

## 11. 实现顺序建议（后续阶段）

1. Job store + `submit` / `status` / `result`  
2. 单线程执行槽挂 `adapter.run`  
3. `cancel`（queued 先做）  
4. `health` / `list_models`  
5. HTTP `/v2`（若 Hermes 跨进程）  
