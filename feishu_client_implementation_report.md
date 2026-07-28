# AIVOICE v1.3-0.4.3-c — Feishu Client Implementation Report

> 日期：2026-07-27  
> 依据：`aivoice_v1.3_feishu_client_design.md`  
> 切片：RealFeishuClient（mock HTTP 单测；未真发消息）

---

## Changed files

| 文件 | 变更 |
|---|---|
| `src/aivoice_studio/notifier/feishu_client.py` | 新增 `RealFeishuClient`、错误类型、`build_feishu_client`；保留 Mock |
| `src/aivoice_studio/notifier/config.py` | **新增** env 读取 / `FEISHU_MODE` |
| `src/aivoice_studio/notifier/__main__.py` | `--real` / 默认 mock；缺凭证友好退出 |
| `src/aivoice_studio/notifier/__init__.py` | 导出 Real / 异常 |
| `tests/test_feishu_client.py` | **新增** mock HTTP 单测 |

**未修改：** `outbox_consumer.py`、Worker、Skill、Pipeline、outbox schema

---

## Interface

保持不变：

```text
send_message(chat_id, text) -> None
upload_file(chat_id, file_path) -> None
```

- `upload_file`：上传得 `file_key` 后发文件消息（不发送本地路径）  
- 缺 `FEISHU_APP_ID`/`SECRET`：`FeishuAuthError("missing_feishu_credentials")`  
- 切换：默认 **mock**；`FEISHU_MODE=real` 或 `--real`

---

## Test

```text
pytest tests/test_notifier_mock.py tests/test_feishu_client.py → 12 passed
py_compile → ok
```

| 项 | 结果 |
|---|---|
| mock regression | **PASS** |
| token mock | **PASS** |
| message mock | **PASS** |
| upload mock | **PASS** |
| config error | **PASS** |

本切片**未**配置真实 token、**未**发送真实消息。

---

## Conclusion

**PASS** — `RealFeishuClient` 已实现，接口与 consumer 兼容，可以进入真实飞书沙盒测试。

下一阶段：人工配 `FEISHU_*` + 有效 `feishu_chat_id` outbox，跑 `--real` 验收。
