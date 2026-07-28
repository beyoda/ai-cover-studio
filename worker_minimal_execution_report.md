# AIVOICE v1.3-0.3.2 Phase 2 — Minimal Execution Integration Report

> 日期：2026-07-27  
> 依据：`aivoice_v1.3_worker_minimal_execution_design.md`

---

## 1. 修改文件

| 文件 | 变更 |
|---|---|
| `src/aivoice_studio/cover/service/cover_service.py` | `run(..., job_id=None)` 透传 Adapter |
| `src/aivoice_studio/cover/contracts/protocols.py` | Protocol 同步可选 `job_id` |
| `src/aivoice_studio/worker/executor.py` | **新增** `execute_claimed_job` |
| `src/aivoice_studio/worker/runtime.py` | claim 后调用 `execute_claimed_job` |
| `tests/test_cover_service_job_id.py` | **新增** job_id 透传单测 |
| `tests/test_worker_executor.py` | **新增** executor mock 单测 |
| `scripts/validate_worker_execute.py` | **新增** mock 验收 |
| `scripts/validate_worker_skeleton.py` | 改为 mock 执行后进 completed |

**未修改：** Pipeline / UVR / SVC / GUI / FileJobQueue API / Hermes Skill

---

## 2. 行为摘要

```text
claim → execute_claimed_job
  → build_cover_request_for_voice
  → CoverService.run(request, job_id=FS_id, on_progress→update_job)
  → complete_job(output_path) | fail_job(error)
```

GUI：`CoverService.run(req)` 不传 `job_id`，行为与改前一致。

---

## 3. 测试结果

```text
pytest tests/test_cover_service_job_id.py
       tests/test_worker_executor.py
       tests/test_cover_service.py
       tests/test_job_service.py
→ 18 passed

validate_worker_execute.py → ok
validate_worker_skeleton.py → ok (queued → completed, mocked)
validate_worker_queue.py → ok
```

---

## 4. 未完成事项

- 真实音频端到端冒烟（本切片仅 mock CoverService）  
- 启动时 `running/` 陈旧任务恢复  
- outbox / 飞书通知  
- Hermes Skill 改为 enqueue（仍可同步 submit）  
- GUI 与 Worker 抢 GPU 的强制锁  

---

## 5. 手动真翻唱（可选）

```text
# Python enqueue 真实 mp3 后：
.venv\Scripts\python.exe -m aivoice_studio.worker --once -v
```
