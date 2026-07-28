# AIVOICE v1.3-0.3.1 — Worker Runtime Skeleton Report

> 日期：2026-07-27  
> 范围：常驻 Worker **骨架**（仅 claim）  
> **未接**：CoverService / Pipeline / UVR / SVC / Hermes / 飞书 / outbox  
> **未改**：FileJobQueue API

---

## 1. 实现文件

| 路径 | 职责 |
|---|---|
| `src/aivoice_studio/worker/runtime.py` | 主循环：claim → 打印 → idle sleep；`--once`；信号处理 |
| `src/aivoice_studio/worker/lock.py` | `worker.lock` 独占 + pid JSON |
| `src/aivoice_studio/worker/__main__.py` | `python -m aivoice_studio.worker` |
| `scripts/run_worker.ps1` | Windows 启动脚本 |
| `scripts/validate_worker_skeleton.py` | 验收：enqueue → worker --once → running |

---

## 2. 行为

```text
启动
 → FileJobQueue(jobs_root)
 → 获取 worker.lock
 → loop:
      job = claim_next_job()
      if None: sleep(idle)
      else: print "claim job {id} status=running"
            # 本阶段不执行翻唱；任务留在 running/
 → Ctrl+C / SIGTERM → 释放 lock → 退出
```

CLI：

```text
.venv\Scripts\python.exe -m aivoice_studio.worker
.venv\Scripts\python.exe -m aivoice_studio.worker --once --jobs-root <path>
scripts\run_worker.ps1
```

---

## 3. 验收结果

`validate_worker_skeleton.py` → **ok: true**

| 步骤 | 结果 |
|---|---|
| enqueue | queued 出现 |
| worker `--once` | stdout: `claim job … status=running` |
| 目录 | queued 消失，running 出现 |

未调用 CoverService / 真实翻唱。

---

## 4. 已知骨架限制

- Claim 后任务 **留在 `running/`**（下一切片再 `run()` → complete/fail）  
- 无崩溃恢复扫描  
- 无 outbox  

---

## 5. 边界确认

| 项 | 状态 |
|---|---|
| FileJobQueue API | 未修改 |
| CoverService / Pipeline | 未调用 |
| Hermes / 飞书 | 未接 |
