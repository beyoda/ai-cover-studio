# AIVOICE v1.3-0.3.2 Phase 2 — Minimal Execution Integration Design

> 日期：2026-07-27  
> 性质：**设计**（本文不实现代码）  
> 前置：  
> - Phase 1：`aivoice_v1.3_worker_coverservice_integration_analysis.md`  
> - Skeleton：`worker_runtime_skeleton_report.md`  
> - 契约：`aivoice_v1.3_worker_interface_contract.md`  

**本切片目标：** 让 Worker 在 claim 之后真正跑通翻唱，并回写 `completed` / `failed`。  
**本切片不做：** Hermes enqueue、飞书、outbox 泵、cancel/retry、崩溃恢复扫描（可顺带最小心跳，非必须）。

---

## 1. 设计目标与非目标

### 目标

```text
queued → claim → running
  → CoverService.run(job_id=FS id, on_progress=…)
  → complete_job(output_path) | fail_job(error)
```

验收形态（实现阶段）：

1. 手工 / 脚本 `enqueue_job`（已有音频路径）  
2. 启动 Worker（或 `--once`）  
3. 真实产出 `outputs/{job_id}/cover.mp3`  
4. 任务出现在 `jobs/completed/`（或失败进 `failed/`）  
5. `running/` 清空该 job  

### 非目标

- 不改 Pipeline / UVR / SVC / GUI  
- 不改 FileJobQueue 协议语义  
- 不接飞书 / outbox / Skill 改造（仍可用脚本 enqueue）  
- 不做 `submit()+poll`  

---

## 2. job_id 对齐策略（最小改动）

### 问题

`CoverService.run()` 今日不传 `job_id` → Adapter 自造 uuid → 与 FS `job_id` 不一致。

### 选定方案：**加性扩展 `CoverService.run`**

```text
CoverService.run(
    request,
    *,
    job_id: str | None = None,      # 新增，可选
    on_progress: ProgressCallback | None = None,
) -> CoverResult
```

实现要点（实现阶段）：

```text
return self._adapter.run(
    request,
    job_id=job_id,           # None 时 Adapter 行为与今天完全一致
    on_progress=on_progress,
)
```

| 调用方 | 行为 |
|---|---|
| GUI / 旧代码 `run(req)` | **不变**（job_id 默认 None） |
| Worker `run(req, job_id=J, on_progress=…)` | `outputs/J/` 与队列 J 对齐 |

**不采用：** Worker 直调 Adapter（可作备选，但会绕过 CoverService 作为应用入口的约定）。  
**不采用：** `submit()`（自造第二套 id）。

协议 / Protocol：实现时可同步给 `CoverServiceProtocol.run` 增加可选 `job_id`（纯类型，无行为变化）。

---

## 3. Worker 执行模块切分

建议在 `aivoice_studio.worker` 内新增（命名实现时可微调）：

| 模块 | 职责 |
|---|---|
| `runtime.py` | 主循环：claim → **execute** → 继续；保留 lock / idle / `--once` |
| `executor.py`（新） | FS job → CoverRequest → `CoverService.run` → complete/fail |
| `queue.py` | **不改 API**；仅被调用 |
| `lock.py` | 不变 |

伪代码：

```text
# runtime loop
job = claim_next_job()
if job:
    execute_claimed_job(queue, job)   # 同步，跑完才 claim 下一单
```

---

## 4. execute_claimed_job 详细步骤

输入：已 claim 的 `CoverJobRecord`（`status=running`）。

```text
1. Preflight
   - Path(input_audio).is_file() 否则 fail_job("找不到输入音频")
   - voice_id 非空

2. Build CoverRequest
   - build_cover_request_for_voice(
       input_audio=job.input_audio,
       voice_id=job.voice_id,
       pitch=job.pitch,
       reverb=options.get("reverb","关闭"),
       f0_method=options.get("f0_method","rmvpe"),
       export_mp3=bool(options.get("export_mp3", True)),
       accompaniment=options.get("accompaniment") or "",
       client="worker",
       request_id=job.job_id,
     )
   - 复用 Registry；禁止手写 checkpoint

3. Progress bridge
   def on_progress(ev: ProgressEvent):
       stage = ev.stage.value if hasattr(ev.stage, "value") else str(ev.stage)
       # 映射用户 stage：uvr/svc/mixing/exporting/done/failed
       update_job(
         job.job_id,
         current_stage=stage,
         progress={"percent": ev.percent, "message": ev.message},
       )
       # 可选：metadata.last_heartbeat_at = now
       log event=stage

4. Execute
   service = CoverService()   # 每单新建即可（隔离内存 JobStore）
   try:
       result = service.run(
           request,
           job_id=job.job_id,
           on_progress=on_progress,
       )
   except Exception as exc:
       fail_job(job.job_id, error=friendly(exc))
       return

5. Finalize
   if result.success:
       path = result.mp3_path or result.wav_path
       if not path or not Path(path).is_file():
           fail_job(..., "完成但缺少输出文件")
       else:
           complete_job(job.job_id, output_path=path)
   else:
       fail_job(job.job_id, error=friendly(result.error or "翻唱失败"))
```

### Stage 映射（写入 FS）

与契约一致，直接使用 Adapter/`Stage` 的 value（小写）：

`pending` → `uvr` → `svc` → `mixing` / `exporting` → `done` | `failed`

Worker **不**向飞书推 stage（本切片无 outbox）。

---

## 5. 错误与友好文案

| 来源 | FS `error` |
|---|---|
| 缺输入文件 | 固定中文短句 |
| `CoverResult.success=False` | 截断 `result.error` 首行；去 traceback |
| 未捕获异常 | `str(exc)` 首行截断 |
| 成功无文件 | 「完成但缺少输出文件」 |

详细堆栈只进 `logs/worker.log`（若已有 logging）。

---

## 6. 与骨架行为的差异

| 项 | Skeleton (0.3.1) | Phase 2 执行接入 |
|---|---|---|
| claim 后 | 打印并 **留在 running/** | 跑完 → **completed/failed** |
| CoverService | 不调用 | `run(job_id=…)` |
| `--once` | claim 一单就退出 | claim **并执行完** 一单再退出（验收友好） |
| GPU | 无负载 | 单线程串行跑真实 UVR/SVC |

停止信号：若正在 `run()`，MVP **等当前单结束** 再退出（与 Runtime Design 一致）；不杀子进程。

---

## 7. 允许的代码触点（实现清单）

| 文件 | 变更类型 |
|---|---|
| `cover/service/cover_service.py` | **加性** `run(..., job_id=None)` 传给 Adapter |
| `cover/contracts/protocols.py` | 可选同步 Protocol 签名 |
| `worker/executor.py` | **新增** |
| `worker/runtime.py` | claim 后调用 executor |
| `scripts/validate_worker_execute.py`（名可变） | mock 或短音频验收 |
| 测试 | `run(job_id=)` 透传单测（mock Adapter） |

**禁止触点：** Pipeline、UVR、SVC、GUI、Hermes Skill、FileJobQueue 方法签名。

---

## 8. 验收计划（实现阶段）

### 8.1 单元（无 GPU）

- mock `PipelineAdapter.run`：断言收到的 `job_id` 等于入参  
- GUI 风格 `CoverService().run(req)` 仍可不传 `job_id`  

### 8.2 集成（可选短音频 / mock_mode）

若环境允许 `runtime.mock_mode` 或极短真实 mp3：

1. `enqueue_job(input_audio=真实或 mock 可用路径, voice_id=example_voice_b|example_voice)`  
2. `python -m aivoice_studio.worker --once`  
3. 断言：`jobs/completed/{id}.json` 存在，`output_path` 指向文件  
4. 断言：`output_path` 父目录名 == `job_id`  

失败路径：故意错误 `voice_id` 或缺失文件 → `failed/`。

### 8.3 明确不测

- 飞书推送  
- Skill `--pick` enqueue（可用 Python 直接 enqueue）  

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 长任务占满 Worker | 已接受；单卡串行是目标 |
| claim 后崩溃留 running | 下切片做 stale 恢复；本切片文档注明 |
| `on_progress` 写盘过频 | stage 变化必写；percent 可节流（≥5% 或 2s） |
| 与 GUI 同时跑 | 产品约定 + 已有 worker.lock；本切片不强制 GUI 抢锁 |

---

## 10. Phase 2 设计结论（一句话）

**最小接入 = 给 `CoverService.run` 增加可选 `job_id` + Worker claim 后同步 `run` + progress 写 FS + complete/fail；不改 Pipeline，不走 submit，不接飞书。**

---

## 11. 实现顺序建议

1. 加性改 `CoverService.run(job_id=…)` + 单测  
2. 新增 `executor.py`  
3. 改 `runtime.py` 主循环调用 executor  
4. `validate_worker_execute` / 短音频冒烟  
5. 出 implementation report  

*Phase 2 设计结束。下一步：按本文实现 Minimal Execution Integration。*
