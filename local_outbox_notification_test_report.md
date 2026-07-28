# AIVOICE v1.3-0.4.2 — Local Outbox Notification Pipeline Test Report

> 日期：2026-07-27  
> 性质：**测试验证 only**（未接飞书、未改 Worker/Pipeline 生产逻辑）  
> 前置：Worker E2E / Skill Enqueue / Worker Outbox Generation PASS

---

## Environment

| 项 | 值 |
|---|---|
| audio | `<repo-root>\workdir\_gpu_smoke\clip30.mp3` |
| voice_id | `example_voice_b` |
| worker command | `python -m aivoice_studio.worker --once -v` |
| consumer | `scripts/test_outbox_consumer.py`（只读，无飞书 SDK） |
| jobs_root | `<repo-root>\jobs` |

说明：验收前将残留 `queued/*.json` 移至 `jobs/_validation_parked/`，保证 `--once` 消费本单。

---

## Result

| 项 | 结果 |
|---|---|
| skill enqueue (A1) | **PASS** |
| worker execute (A2) | **PASS**（rc=0，~12.9s） |
| completed (A3) | **PASS** |
| cover.mp3 (A4) | **PASS**（1003146 bytes） |
| outbox (A5–A6) | **PASS** |
| local consumer (A7) | **PASS** |

失败分类：无 Queue / Worker / Outbox / Consumer 失败。

---

## Payload

| 项 | 值 |
|---|---|
| job_id | `f65ddb9ca5cb` |
| Skill wall | 0.25s，`status=queued`，`output_path=null`（无 completed） |
| completed | `jobs/completed/f65ddb9ca5cb.json` |
| output_path | `<repo-root>\outputs\f65ddb9ca5cb\cover.mp3` |
| mp3 size | 1003146 |
| outbox path | `jobs/outbox/f65ddb9ca5cb.notify.json` |
| paths match | completed.output_path == outbox.output_path |
| Worker log | `claim` → `outbox_written` → `complete` |

### 实际 Outbox schema（相对测试清单的差异）

测试清单期望含 `message` / `metadata`；**当前 0.4.2-a 生产 schema 为：**

```text
job_id, status, notify_status, output_path, song, voice_id,
hermes_session_id, feishu_chat_id, retry_count, created_at
```

| 期望字段 | 实际 |
|---|---|
| `job_id` | ✅ |
| `status` | ✅（`completed`） |
| `output_path` | ✅ |
| `message` | ❌ 无；consumer 用 `song`+`voice_id` 派生展示 |
| `metadata` | ❌ 无；曲名/音色已平铺为 `song` / `voice_id` |
| `chat_id` | 对应 `feishu_chat_id`（本单为 `null`） |

**未改生产代码**；差异记入契约，供飞书 Notifier 实现时选用：要么消费平铺字段，要么后续切片补 `message`。

本地 consumer 输出摘要：

```text
OUTBOX EVENT OK
  job_id=f65ddb9ca5cb
  status=completed
  notify_status=pending
  message=[derived] song=clip30 voice=example_voice_b
  output_path=<repo-root>\outputs\f65ddb9ca5cb\cover.mp3
  chat_id=None
  mp3_exists=True
```

---

## Conclusion

**PASS** — 本地通知链路验证通过：

```text
Skill enqueue → Worker → completed → outbox/*.notify.json → 本地 consumer
```

Outbox 可作为未来飞书发送的可靠中间层（`job_id` + `output_path` + mp3 存在性已闭环）。

**可以进入飞书 Notifier 实现**（需另行处理 `feishu_chat_id` 写入与可选 `message` 渲染）。

本阶段未接飞书 SDK / 未真发消息 / 未改 Worker 执行逻辑。
