# AIVOICE v1.3-0.4.3 — Feishu Notifier Local Implementation Plan

> 日期：2026-07-27  
> 性质：**实现前文件级计划确认**（本文不改生产代码、不接真飞书）  
> 前置：Local Outbox Notification Pipeline Test **PASS**

---

## 1. 当前缺口确认

| 已验证 | 剩余 |
|---|---|
| Skill → queued | outbox → **飞书消息 + 文件** |
| Worker → completed + mp3 | 独立 Notifier 进程 |
| `jobs/outbox/{id}.notify.json` | claim / sent / 幂等 |
| 本地 consumer 可读 | `feishu_chat_id` 常为 **null**（投递目标缺口） |

链路卡点：

```text
outbox/*.notify.json  ✅
        ↓
   Notifier（缺失）
        ↓
飞书 send text + upload file（缺失独立模块）
        ↓
notify_status=sent / *.notify.sent.json（缺失）
```

---

## 2. 设计原则（确认）

| 组件 | 做 | 不做 |
|---|---|---|
| **Worker** | 翻唱、completed、写 outbox | import 飞书、发消息、存 token |
| **Notifier** | 读 outbox、发飞书、上传文件、标 sent | 跑 Pipeline / 改 Skill |
| **Skill** | enqueue + queued ACK | 查完成、本轮发 mp3 |

**禁止改：** Pipeline / UVR / SVC / Worker 执行流程 / Skill enqueue（本 Notifier 切片）。

---

## 3. 只读扫描结果

### 3.1 Outbox（`src/aivoice_studio/worker/outbox.py`）

| 项 | 现状 |
|---|---|
| 路径 | `jobs/outbox/{job_id}.notify.json` |
| 写入时机 | `executor` 在 `complete_job` 成功后 |
| schema | `job_id, status=completed, notify_status=pending, output_path, song, voice_id, hermes_session_id, feishu_chat_id, retry_count, created_at` |
| **无** | `message`、`metadata` 嵌套、claim/rename、sending 态 |
| 幂等（写侧） | 已存在 `.notify.json` 或 `.notify.sent.json` → **keep 不覆盖** |
| fail 任务 | **不写** outbox（0.4.2-a 约定） |

**Notifier 须自行实现：** pending → sending → sent 的 rename claim；文案由 `song`/`voice_id` 现场拼装（或调用 `format_cover_done`，非 Skill 路径）。

### 3.2 飞书相关现状

| 位置 | 能力 | 与 Notifier 关系 |
|---|---|---|
| `src/aivoice_studio/server/feishu.py` | `FEISHU_APP_ID` / `APP_SECRET`；tenant token；**reply** 文本/文件；上传 `/im/v1/files` | **可参考** token+上传；**不可直接复用**（依赖 `message_id` reply，且内嵌旧 Pipeline 翻唱） |
| Hermes Gateway | 飞书 websocket（产品主通道） | Notifier MVP **不依赖** Hermes；独立 Open API 发送 |
| `src/aivoice_studio/notifier/` | **不存在** | **需新建** |

结论：**需要新增 notifier 模块**；不要把发送逻辑塞进 `server/feishu.py` 的 callback，也不要塞进 Worker。

### 3.3 chat_id 缺口

本地验收样例 `feishu_chat_id=null`。真实发送前必须具备其一：

1. Skill/enqueue 写入真实 `feishu_chat_id`（**建议并行小切片 0.4.3-pre**，或真测时手工改 outbox）；或  
2. 测试用环境变量 `FEISHU_TEST_CHAT_ID` 仅覆盖 dry-run/真测（不写回生产 Skill）。

无 chat_id → Notifier **skip**（记日志），**不得**改 completed。

---

## 4. 推荐新增结构

```text
src/aivoice_studio/notifier/
  __init__.py
  __main__.py              # python -m aivoice_studio.notifier [--once]
  models.py                # OutboxEvent 解析（兼容现行 schema）
  feishu_client.py         # token / send_text / upload+send_file（可 mock）
  outbox_consumer.py       # scan / claim / send / mark sent|retry
  message_format.py        # 从 song/voice_id 生成用户文案

scripts/run_notifier.ps1   # PYTHONPATH=src，清 VIRTUAL_ENV（可选）
tests/test_notifier_*.py   # mock 飞书 + 幂等
```

**不修改：** `worker/executor.py` 执行路径、`worker/outbox.py` 写逻辑（除非后续单独加「读辅助」且不改写侧语义——MVP 建议 Notifier 自包含读写 outbox 文件）。

---

## 5. 消费流程（实现契约）

```text
scan jobs/outbox/*.notify.json
  where notify_status == pending（或缺失视为 pending）
  skip if *.notify.sent.json 已存在

claim:
  atomic rename → {job_id}.notify.sending.json

validate:
  feishu_chat_id 非空（否则 → skip/dead，不发）
  Path(output_path).is_file()

payload:
  text = format_cover_done 或「翻唱完成\\n🎵 {song}\\n🎤 {voice_id}」
  file = cover.mp3

send:
  FeishuClient.send_text(chat_id, text)
  FeishuClient.send_file(chat_id, output_path)

success:
  rename → {job_id}.notify.sent.json
  （可选）回写 jobs/completed/{id}.json 的 notify_status=sent —— 用原子读改写，失败只打日志

failure:
  retry_count += 1
  rename 回 *.notify.json 或保持 sending→pending
  不碰 completed 状态
```

飞书 API（相对旧 Flask）：

| 能力 | 建议端点 |
|---|---|
| token | `POST .../auth/v3/tenant_access_token/internal`（同现有） |
| 文本 | `POST .../im/v1/messages`，`receive_id_type=chat_id` |
| 文件 | 先 `POST .../im/v1/files`，再 `messages` `msg_type=file` |

凭证：仅环境变量 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`（及可选 `FEISHU_TEST_CHAT_ID`）；**不写进 outbox JSON**。

---

## 6. 幂等规则

| 规则 | 做法 |
|---|---|
| 发送前 claim | rename → `.sending` |
| 已 sent | 见 `.notify.sent.json` 或 `notify_status=sent` → **skip** |
| 双 Notifier | rename 失败者跳过 |
| 同 job_id 跑两次 | 第一次 sent；第二次 skip；**不二次上传** |
| 发送成功、rename 失败 | 可能重复一次（记观察项）；MVP 可接受 |

---

## 7. 飞书接入边界

**允许：** SDK 或 `requests`、access token、消息 API、文件上传。  

**禁止塞入：** Hermes Skill、Worker executor、Pipeline、UVR、SVC。

**可选依赖：** 不强制 `lark-oapi`；与现有 `feishu.py` 一致用 `requests` 即可，便于 mock。

---

## 8. 测试计划（实现后）

| # | 内容 | 真飞书 |
|---|---|---|
| **T1** | mock `FeishuClient`：outbox → consumer → 断言 payload + mark sent | 否 |
| **T2** | 真 chat_id + 真凭证：收文本 + mp3 | 是（人工） |
| **T3** | 同 job_id 跑两次 consumer：第二次 skip | 否（mock） |

验收映射：A1–A6（读 outbox / 消息 / 上传 / sent / 幂等 / 不影响 completed）。

报告文件（**实现并测完后**才写）：`feishu_notifier_test_report.md`。

---

## 9. 建议实现顺序

```text
Step 1: 新建 notifier 包骨架 + OutboxEvent 解析（现行 schema）
Step 2: FeishuClient 接口 + MockFeishuClient
Step 3: outbox_consumer claim/sent/retry（无真网）
Step 4: pytest T1 + T3
Step 5: FeishuClient 真实现（requests）
Step 6: run_notifier.ps1 + --once
Step 7:（可选）真飞书 T2 + 补 feishu_chat_id 来源
Step 8: 写 feishu_notifier_test_report.md
```

**并行注意：** 无 `feishu_chat_id` 时 T2 无法 PASS；需 Skill 传 chat_id 或测试注入，**仍不要**为了 Notifier 去改 Worker 执行链。

---

## 10. 本阶段结论（计划确认）

1. **只新增** `src/aivoice_studio/notifier/`（+ 脚本/测试）；不改 Worker/Skill/Pipeline。  
2. 可参考 `server/feishu.py` 的 token/上传，但必须改为 **按 `chat_id` 主动发消息**。  
3. Outbox **无 claim**；claim/sent 由 Notifier 负责。  
4. 文案用 `song`/`voice_id` 拼装；`feishu_chat_id` 为空则 skip。  
5. 先 mock 闭环，再真飞书；报告在实现后输出。

**下一步：** 按本计划进入 **0.4.3-a Notifier 骨架 + mock 飞书**（仍可不真下发）。

---

*计划确认结束。未改代码、未接飞书。*
