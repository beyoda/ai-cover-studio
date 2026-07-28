# AIVOICE v1.3-0.4.2-a — Worker Outbox Generation Report

> 日期：2026-07-27  
> 依据：`aivoice_v1.3_outbox_notification_design.md`  
> 切片：completed → `jobs/outbox/{job_id}.notify.json`

---

## Changed files

| 文件 | 变更 |
|---|---|
| `src/aivoice_studio/worker/outbox.py` | **新增** `write_completed_outbox_event`（幂等写盘） |
| `src/aivoice_studio/worker/executor.py` | `complete_job` 成功后调用写 outbox；fail 路径不写 |
| `tests/test_worker_outbox.py` | **新增** happy / fail / idempotent |

**未修改：** Pipeline / UVR / SVC / `CoverService.run` / Hermes Skill / FileJobQueue API / Notifier / 飞书

---

## Outbox schema

路径：`jobs/outbox/{job_id}.notify.json`

```json
{
  "job_id": "<id>",
  "status": "completed",
  "notify_status": "pending",
  "output_path": "<same as completed.output_path>",
  "song": "<metadata.song or source>",
  "voice_id": "<job.voice_id>",
  "hermes_session_id": "<or null>",
  "feishu_chat_id": "<or null>",
  "retry_count": 0,
  "created_at": "<ISO>"
}
```

- 无飞书 token / 不调飞书 API  
- 已存在 `.notify.json` 或 `.notify.sent.json` → **keep，不覆盖**  
- 写盘失败只打日志，**不**改变 completed  

---

## Tests

```text
pytest tests/test_worker_outbox.py tests/test_worker_executor.py
→ 5 passed
```

| 用例 | 断言 |
|---|---|
| happy | completed + outbox 存在；`output_path` 一致 |
| fail | failed 存在；outbox **不**存在 |
| idempotent | `notify_status=sent` 不被覆盖 |

---

## Verification

- Worker 在 `complete_job()` **之后**产生通知事件  
- 失败任务不生成 outbox（本切片约定）  
- FileJobQueue 公开 API 未改  

---

## 明确说明

```text
Worker 已产生通知事件
Worker 未依赖飞书
Notifier 尚未实现
```

本切片停止。不接飞书，不写 notifier。
