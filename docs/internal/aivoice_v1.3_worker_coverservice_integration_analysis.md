# AIVOICE v1.3-0.3.2 Phase 1 — CoverService Execution Integration Analysis

> 日期：2026-07-27  
> 性质：**只读分析**（未改代码、未接 Worker 执行）  
> 前置：Worker Runtime Skeleton · FileJobQueue · Runtime Design  

用户提问原文在 Q1 处截断（`submit()+`），本文仍完整回答 **A `run()` vs B `submit()+poll`**，并标出接入前必须正视的 **job_id 缺口**。

---

## 1. CoverService

| 项 | 结论 |
|---|---|
| **位置** | `src/aivoice_studio/cover/service/cover_service.py` → `class CoverService` |
| **初始化** | `CoverService(adapter=None, uvr_cache=None, max_workers=1)`；默认自建 `PipelineAdapter` + 内存 `JobStore` + `ThreadPoolExecutor` |
| **`run()` 签名** | `run(request: CoverRequest, *, on_progress: ProgressCallback \| None = None) -> CoverResult` |
| **`submit()`** | `submit(request) -> str`（内部新生成 12-hex `job_id`，与 FS queue **无关**） |
| **CoverRequest** | `cover/domain/request.py`：`input_audio`, `voice_id`/`model_name`, `pitch`, `reverb`, `f0_method`, `export_mp3`, `accompaniment`, `workdir`/`output_dir`, `client`, `request_id` |
| **CoverResult** | `cover/domain/result.py`：`success`, `job_id`, `wav_path`, `mp3_path`, `error`, … |
| **job_id 注入** | **`run()` 当前不接受 `job_id`**，直接 `_adapter.run(request, on_progress=...)`，Adapter 会自造 uuid。`submit()` 路径才把内存 job_id 传给 Adapter |
| **progress callback** | ✅ `on_progress: Callable[[ProgressEvent], None]`；`ProgressEvent(job_id, stage, percent, message, elapsed_s)` |

### 关键缺口（接入 Worker 前必须处理）

契约要求：FS `job_id` == `outputs/{job_id}/`。

但：

```text
CoverService.run(request, on_progress=...)
  → PipelineAdapter.run(request, on_progress=...)   # 无 job_id
       → resolved_job_id = uuid4().hex[:12]          # 新 id！
```

而 `_execute_job`（submit 路径）是：

```text
_adapter.run(request, job_id=job_id, on_progress=...)
```

因此：**若 Worker 只调现在的 `CoverService.run()`，磁盘目录 job_id 会与队列 job_id 不一致。**  
实现切片需在下列之一中择一（属后续实现，非本分析改码）：

1. **最小加性**：给 `CoverService.run(..., job_id: str | None = None)` 并原样传给 Adapter（不改执行逻辑）。  
2. Worker 直接调 `PipelineAdapter.run(..., job_id=fs_job_id)`（绕过 Service 薄封装，仍复用 Adapter）。  
3. 用 `submit()` 但 **放弃** FS job_id 与 output 对齐（**违反契约，不推荐**）。

---

## 2. PipelineAdapter

| 项 | 结论 |
|---|---|
| **位置** | `cover/adapter/pipeline_adapter.py` |
| **Worker 进入点** | CoverService → **Adapter.run** → `build_pipeline(callback)` → `Pipeline.run` |
| **job_id** | 参数 `job_id`；缺省则新 uuid；写入 `PipelineJobContext.job_id` → `workdir/{id}`、`outputs/{id}` |
| **output_path** | Pipeline 成功后填入 `CoverResult.mp3_path` / `wav_path`（通常 `outputs/{job_id}/cover.mp3`） |
| **progress** | Pipeline `JobManager` callback `(state, percent, message)` → `Stage.from_value` → `ProgressEvent` → `on_progress` |
| **音色** | `resolve_request_voice(request)`；绑定 `pipeline.svc.config.model_path/config_path` |
| **UVR cache** | 可选命中则 `skip_uvr` |

Adapter 已是正确边界：**Worker 不应复制 Registry 绑路径 / build_pipeline / UVR cache 逻辑**。

---

## 3. Pipeline

| 项 | 结论 |
|---|---|
| **执行模型** | **同步** `Pipeline.run(job) -> JobResult`；内部顺序 UVR→SVC→FX→Mix→Export |
| **Worker 额外封装** | 不需要再包一层 Pipeline；最多在 Worker 里把 FS job → CoverRequest → 调 Service/Adapter |
| **异常** | 业务失败多以 `JobResult/CoverResult(success=False, error=...)` 返回；未预期异常会向上抛，由调用方 `fail_job` 捕获（与现 `_execute_job` try/except 同模式） |
| **子进程** | UVR/SVC/ffmpeg 经现有模块；Worker 无需直接碰 |

---

## 4. 当前 v1.2 成功入口（须复用 vs 勿复制）

```text
aivoice_cover.py
  → MusicSource / session pick（同步选歌）
  → build_cover_request_for_voice(...)
  → CoverService().submit(cover_req)
  → 同进程 status 轮询
  → result.mp3_path
```

### 必须复用

- `build_cover_request_for_voice`（或等价：Registry + `CoverRequest` 字段填充）  
- `PipelineAdapter` / `Pipeline` 执行链（经 CoverService 或 Adapter）  
- `CoverResult` 的 `mp3_path`/`wav_path`/`success`/`error`  
- `on_progress` → 写 FS `update_job(current_stage, progress)`  

### Worker 不应复制

- Hermes 搜歌 / `--pick` / session 状态机  
- Skill 内 600s 阻塞 poll 与飞书话术  
- CoverService **内存** JobStore 作为跨进程真相（真相在 FileJobQueue）  
- 直接拼 SVC CLI / UVR CLI  

### enqueue 侧（非本 Worker 执行切片，但边界清晰）

选歌与下载仍属 Skill；写入 `queued/` 时 **已有** `input_audio`。Worker 只消费就绪音频。

---

## 5. 重点问题

### Q1 — Worker 应调用 A `run()` 还是 B `submit()+poll`？

| | **A. `CoverService.run()`** | **B. `submit()` + status 轮询 |
|---|---|---|
| 复杂度 | 低 | 高（线程池 + poll + shutdown） |
| 与单线程 Worker | 天然匹配 | 多余嵌套 |
| 进度 | `on_progress` 直接写 FS | 拉 `status()` 再转写 |
| job_id 对齐 | **现状缺口**（见上）；需加性传 `job_id` 或改调 Adapter | submit **自造** id，与 FS id **冲突**，更糟 |
| 崩溃恢复 | 依赖 FS `running/` 超时 | 同左，无优势 |
| 稳定性 | 与 GUI 同路径 | 多一层生命周期 |

**推荐：A（`run()` + `on_progress`），并在实现时补上 `job_id` 传入（优先扩展 `run(job_id=...)`，或 Worker 调 `PipelineAdapter.run(job_id=...)`）。**  
**不推荐 B** 作为 Worker 主路径。

（原文 B 在 `submit()+` 处截断；完整对比即为 `submit` + 同进程 `status`/`result` 轮询。）

---

## 6. 建议的 Worker 执行伪流程（设计，非代码）

```text
claim_next_job()  →  FS job (status=running, job_id=J)
校验 input_audio 存在
req, asset = build_cover_request_for_voice(
    input_audio=job.input_audio,
    voice_id=job.voice_id,
    pitch=job.pitch,
    reverb=job.options["reverb"],
    ...
    client="worker",
    request_id=J,
)
def on_progress(ev: ProgressEvent):
    update_job(J, current_stage=ev.stage.value, progress={percent, message}, heartbeat=...)

result = CoverService().run(req, on_progress=on_progress)   # 理想：+ job_id=J
# 或 adapter.run(req, job_id=J, on_progress=...)

if result.success and (result.mp3_path or result.wav_path):
    complete_job(J, output_path=...)
else:
    fail_job(J, error=友好文案(result.error))
```

---

## 7. 本阶段结论

| 问题 | 答案 |
|---|---|
| 执行入口 | **复用 Cover 层，优先 `run()`** |
| 进度 | **`on_progress` → FileJobQueue.update_job** |
| 输出 | **`CoverResult.mp3_path` → complete_job** |
| Pipeline | **保持同步；Worker 不封装 Pipeline 内部** |
| 阻塞点 | **`CoverService.run()` 未透传 job_id** — 实现接入前必须解决，否则违背 FS 契约 |

---

## 8. 明确未做

- 未修改 CoverService / Pipeline / Worker 代码  
- 未实现真实翻唱接入  
- 未接 outbox / 飞书  

*Phase 1 分析结束。下一步（未开始）：实现接入（含 job_id 透传策略）。*
