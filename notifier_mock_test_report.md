# AIVOICE v1.3-0.4.3-a — Notifier Mock Test Report

> 日期：2026-07-27  
> 依据：`aivoice_v1.3_feishu_notifier_implementation_plan.md`  
> 切片：Notifier 骨架 + MockFeishuClient（不接真飞书）

---

## Environment

| 项 | 值 |
|---|---|
| jobs_root | 测试用 `tmp_path/jobs`（pytest） |
| test mode | **mock**（无网络、无 token） |
| 入口 | `python -m aivoice_studio.notifier` |

---

## Changed / Added files

| 文件 | 说明 |
|---|---|
| `src/aivoice_studio/notifier/__init__.py` | 包导出 |
| `src/aivoice_studio/notifier/feishu_client.py` | `FeishuClient` Protocol + `MockFeishuClient` |
| `src/aivoice_studio/notifier/outbox_consumer.py` | scan / claim / send / sent\|skipped |
| `src/aivoice_studio/notifier/__main__.py` | CLI `--once` 统计 |
| `tests/test_notifier_mock.py` | T1–T3 |

**未修改：** `worker/`、Pipeline、UVR、SVC、CoverService、Skill

---

## File state flow（本切片）

```text
jobs/outbox/{job_id}.notify.json      # pending
        ↓ claim (rename)
jobs/outbox/{job_id}.sending.json     # sending
        ↓ success
jobs/outbox/sent/{job_id}.notify.json # sent

        ↓ missing feishu_chat_id
jobs/outbox/skipped/{job_id}.notify.json  # skipped + skip_reason
```

兼容 Worker 现有写入路径（`*.notify.json`）；未改 `worker/outbox.py`。

---

## Result

| 项 | 结果 |
|---|---|
| pending consume | **PASS** |
| mock message | **PASS** |
| mock upload | **PASS** |
| idempotent | **PASS** |
| missing chat_id | **PASS**（`skipped` / `missing_chat_id`） |

```text
py_compile src/aivoice_studio/notifier/*.py → ok
pytest tests/test_notifier_mock.py → 3 passed
```

---

## Conclusion

**PASS** — Notifier 本地消费链路通过：outbox pending → mock send/upload → sent；无 chat_id → skipped；重复消费不二次发送。

**可以进入真实飞书 Client 接入**（下一切片）。本切片未配 token、未调飞书 API。
