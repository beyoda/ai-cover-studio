# AIVOICE v1.3-0.4.3-d — Feishu Real Sandbox Test Report

> 日期：2026-07-27  
> 性质：**测试验证 only**（未改 Worker / Skill / Pipeline / outbox schema）  
> 前置：RealFeishuClient 已实现；Mock 流程 PASS

---

## Environment

| 项 | 值 |
|---|---|
| app mode | 目标 `real`；本机 **未配置** `FEISHU_APP_ID` / `FEISHU_APP_SECRET` |
| `FEISHU_MODE` | unset |
| 仓库 `.env` | **无** |
| job_id | `f65ddb9ca5cb` |
| chat_id 是否存在 | **否**（`feishu_chat_id=null`） |
| output_path | `<repo-root>\outputs\f65ddb9ca5cb\cover.mp3`（存在，1003146 bytes） |
| outbox 初态 | `jobs/outbox/f65ddb9ca5cb.notify.json`，`notify_status=pending`，`status=completed` |

凭证检查：仅确认环境变量是否设置，**未**打印 secret。

---

## Execution log

### Real Notifier（无凭证）

```text
python -m aivoice_studio.notifier --real
→ {"ok": false, "error": "missing_feishu_credentials", "mode": "real"}
→ exit 2
```

**未调用**飞书 HTTP（Client 构造阶段即失败）。  
**未猜测** chat_id；未改业务逻辑。

### 异常 A — missing_chat_id（mock 验证路径）

因无真实凭证，用默认 mock 消费同一 pending 事件，验证 skip 契约：

```text
result=skipped
skip_reason=missing_chat_id
message_called=false
upload_called=false
→ jobs/outbox/skipped/f65ddb9ca5cb.notify.json
```

### 幂等（二次扫描）

再次 `python -m aivoice_studio.notifier`：

```text
consumed_count=0  # 无 pending；不重复发送
```

---

## Result

| 项 | 结果 |
|---|---|
| token 获取 | **BLOCKED**（缺 `FEISHU_APP_ID`/`SECRET`） |
| 文本发送 | **BLOCKED** / 未执行真发 |
| 文件上传 | **BLOCKED** / 未执行真发 |
| outbox 状态迁移 | **PARTIAL**：pending → **skipped**（`missing_chat_id`），非 `sent/` |
| 幂等 | **PASS**（跳过后二次运行不发送） |
| 无 chat_id 行为 | **PASS**（`skipped` + `missing_chat_id`，不发飞书） |
| 人工飞书收消息 | **未验证**（环境不具备） |

---

## Failure points（分类）

| 类型 | 说明 |
|---|---|
| **环境/凭证** | 进程环境无飞书应用凭证 → `--real` 明确 `missing_feishu_credentials` |
| **chat_id 链路** | 测试 outbox `feishu_chat_id=null`（Skill 未注入）→ 按设计 skip，不猜测 |
| **真发闭环** | 以上两项阻断；**不是** Worker / Pipeline / Client 单元实现失败 |

未发现：Worker 回归、outbox schema 损坏、Notifier 在有 chat_id+凭证时的逻辑缺陷（该路径本切片无法实跑）。

---

## Conclusion

**FAIL（沙盒真发未完成）** — 暂停宣称「飞书通知闭环完成」。

已证明：

- `--real` 缺凭证时失败清晰、不污染 traceback  
- `feishu_chat_id=null` → `outbox/skipped/` + `missing_chat_id`，不发送  
- 二次消费不重复发  

未证明：

- 真实 token → 文本 + mp3 到达飞书会话  
- `notify_status=sent` / `outbox/sent/`

**重跑沙盒前需人工准备：**

1. 设置 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`（仅环境变量）  
2. 准备 pending outbox，且 **`feishu_chat_id` 为机器人已加入的真实群/会话 id**  
3. `output_path` 指向可读 mp3  
4. `python -m aivoice_studio.notifier --real`  
5. 人工确认飞书收到文案 + 可播放 mp3，并确认 `outbox/sent/{job_id}.notify.json`

下一阶段（另开切片）：`feishu_chat_id` 自动注入、文案优化、重试、生产部署。

本切片停止；未改 Worker / Skill / Pipeline。
