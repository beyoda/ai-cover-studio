# AIVOICE v1.3-0.1 — Persistent Job Queue Foundation Report

> 日期：2026-07-27  
> 范围：仅文件系统队列基础设施  
> **未改**：Pipeline / CoverService / GUI / Hermes Skill  
> **未接**：飞书 / 真实翻唱

---

## 1. 实现内容

### 目录

```text
jobs/
├── queued/
├── running/
├── completed/
├── failed/
├── cancelled/
├── outbox/
├── worker.lock
└── .gitignore
```

### 代码

| 路径 | 职责 |
|---|---|
| `src/aivoice_studio/worker/models.py` | `CoverJobRecord` / status / notify 枚举 |
| `src/aivoice_studio/worker/queue.py` | `FileJobQueue`：enqueue / claim / update / complete / fail |
| `src/aivoice_studio/worker/__init__.py` | 导出 |
| `scripts/validate_worker_queue.py` | 无翻唱验收 |

### API

- `enqueue_job(...)` → 12 位 `job_id`，临时 JSON + `os.replace` 进 `queued/`
- `claim_next_job()` → 扫描 `queued/`（mtime 升序），`rename` → `running/`，写 `started_at`
- `update_job(job_id, **fields)` → 原地更新 JSON
- `complete_job(job_id, output_path=...)` → `running` → `completed`
- `fail_job(job_id, error=...)` → `running` → `failed`

---

## 2. 验证结果

```text
python scripts/validate_worker_queue.py
→ ok: true
```

| 步骤 | 结果 |
|---|---|
| enqueue | `queued/{id}.json` 出现 |
| claim | queued 消失，`running/{id}.json` 出现 |
| update | `current_stage=uvr` |
| complete | running 消失，`completed/{id}.json` 出现 |
| fail（第二单） | `failed/{id}.json` 出现 |
| layout | 六目录 + `worker.lock` |

未调用 CoverService / Pipeline / UVR / SVC。

---

## 3. 未做（后续切片）

- Worker 常驻消费循环  
- Skill enqueue 接入  
- Outbox 泵 / 飞书  
- `worker.lock` 独占进程语义（现为占位空文件）  

---

## 4. 边界确认

| 模块 | 状态 |
|---|---|
| Pipeline | 未改 |
| CoverService | 未改 |
| GUI | 未改 |
| Hermes Skill | 未改 |
| 飞书 | 未接 |
