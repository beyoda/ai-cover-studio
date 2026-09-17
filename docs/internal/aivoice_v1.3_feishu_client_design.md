# AIVOICE v1.3-0.4.3-b — Feishu Client Real Integration Design

> 日期：2026-07-27  
> 性质：**只读扫描 + 实现计划**（不写飞书代码、不配 token、不发消息、不改 consumer）  
> 前置：Notifier Mock Consumer **PASS**（`notifier_mock_test_report.md`）

目标：仅将 `MockFeishuClient` 替换为真实 `FeishuClient` 实现；**保持 `outbox_consumer.py` 调用契约不变**。

---

## 1. Current Interface

扫描：`src/aivoice_studio/notifier/feishu_client.py`

### Protocol（consumer 依赖）

```text
send_message(chat_id: str, text: str) -> None
upload_file(chat_id: str, file_path: str | Path) -> None
```

| 方法 | 参数 | 返回 | Mock 行为 |
|---|---|---|---|
| `send_message` | `chat_id`, `text` | `None`（成功）；异常表示失败 | 记录 `MockSendRecord(kind=message)` |
| `upload_file` | `chat_id`, `file_path` | `None`（成功）；异常表示失败 | 记录 `MockSendRecord(kind=file)`，**不读文件内容发网** |

`outbox_consumer.py` 用法（勿改）：

```text
client.send_message(chat_id, text)
client.upload_file(chat_id, str(output_path))
```

语义约定（实现真实 Client 时必须遵守）：

- `upload_file` = **上传本地文件并作为文件消息发到该 chat**（不是只上传拿到 key 却不发）。
- 成功：正常返回；失败：抛异常，由 consumer `_release_pending` + `retry_count++`。
- **不**返回复杂结构；与 mock 一致用异常表达失败。

参考（勿直接复用进 Notifier）：`server/feishu.py` 已有 tenant token + `/im/v1/files` 上传，但是 **reply(`message_id`)**，不是按 `chat_id` 主动发。

---

## 2. 飞书接入方案确认

**采用方案 A：飞书自建应用（内部应用）+ Open API。**

```text
FEISHU_APP_ID + FEISHU_APP_SECRET
        ↓
POST /open-apis/auth/v3/tenant_access_token/internal
        ↓
tenant_access_token
        ↓
POST /open-apis/im/v1/messages   (text, receive_id=chat_id)
        ↓
POST /open-apis/im/v1/files      (upload mp3 → file_key)
        ↓
POST /open-apis/im/v1/messages   (file, content.file_key)
```

- 传输：`requests`（与现有 Flask 飞书蓝图一致；可不引入 `lark-oapi`）。  
- **凭证只来自环境变量**，禁止写入 job JSON / outbox / 仓库内 config。

---

## 3. Config

| 变量 | 必填 | 说明 |
|---|---|---|
| `FEISHU_APP_ID` | ✅ | 自建应用 App ID |
| `FEISHU_APP_SECRET` | ✅ | App Secret |
| `FEISHU_BASE_URL` | 否 | 默认 `https://open.feishu.cn` |
| `FEISHU_RECEIVE_ID_TYPE` | 否 | 默认 `chat_id`（群）；若发用户可 `open_id`（另测） |

CLI（实现阶段，非本文）：

```text
python -m aivoice_studio.notifier --real   # 用 RealFeishuClient
# 默认仍 mock，避免误发
```

Token 缓存：进程内缓存 `tenant_access_token` + 过期时间（飞书一般 ~2h）；401 时清缓存重取一次。

---

## 4. Permission

开放平台需开通（名称以飞书后台为准，语义如下）：

| 能力 | 权限方向 |
|---|---|
| 获取 `tenant_access_token` | 应用身份 |
| **发送消息** | `im:message` / 以应用身份发消息 |
| **上传文件** / 发文件消息 | 文件上传 + 发消息中的 file 类型 |
| 读取群聊（可选） | 便于排障；非 MVP 必须 |

运维约束：

- 机器人必须 **已加入目标群**，或具备向目标用户发消息的能力。  
- `chat_id` 必须是该机器人可见的会话 id（群 `oc_…` 等）。  
- 应用发布/可用范围需覆盖测试租户。

---

## 5. chat_id 链路检查

```text
Skill enqueue
  req.feishu_chat_id | options.feishu_chat_id
        ↓
FileJobQueue.enqueue_job(feishu_chat_id=…)
        ↓
Worker complete → outbox.feishu_chat_id
        ↓
Notifier: chat_id = feishu_chat_id or chat_id
```

**现状（代码事实）：**

- `aivoice_cover.py` **仅**在 request/options 显式带 `feishu_chat_id` 时写入；**不会**从 `--session-id` 自动推导。  
- 本地验收样例多为 `feishu_chat_id=null` → consumer 已 **`skipped` / `missing_chat_id`**。  
- **不要自动猜测** chat_id（禁止把 session_id 当 chat_id）。

真发前缺口（另切片，非本 Client 设计强制改 Skill）：

- Hermes/Skill 传入真实群 `chat_id`；或  
- 真测时手工写入 outbox / 测试夹具注入。

空 chat_id → 保持 **skipped**，翻唱 completed 不变。

---

## 6. 文件发送设计

禁止：把本机路径字符串当飞书内容发送。

**推荐流程（封装在 `upload_file(chat_id, file_path)` 内）：**

```text
1. 校验 Path(file_path).is_file() 且 size > 0
2. multipart POST {BASE}/open-apis/im/v1/files
     file_type=stream|mp3（按文档；现有蓝图用 mp3）
     file_name=cover.mp3（或 Path.name）
3. 解析 data.file_key；缺失 → 抛 UploadError
4. POST {BASE}/open-apis/im/v1/messages
     receive_id_type=chat_id
     receive_id=chat_id
     msg_type=file
     content={"file_key": "..."}
5. code!=0 → 抛 SendError
```

文本：`send_message` 单独发 `msg_type=text`（consumer 先 text 后 file，顺序保持）。

可选增强（非 MVP）：失败时只发文本说明「文件上传失败」——须在 Client 层明确策略，避免 consumer 以为成功；**MVP：任一步失败整单抛错 → pending 重试**。

---

## 7. Error handling

| 类别 | 典型原因 | Client 行为 | Consumer（已有，不改） |
|---|---|---|---|
| **token 失败** | app_id/secret 错、网络 | 抛 `FeishuAuthError` | failed → pending + retry |
| **chat 无效** | 未入群、错误 id | 抛 `FeishuChatError` | 同上；可观察后改 skipped（**后期**） |
| **上传失败** | 文件过大、类型拒收 | 抛 `FeishuUploadError` | 同上 |
| **发消息失败** | 限流、权限 | 抛 `FeishuSendError` | 同上 |

铁律：

- **不修改** `jobs/completed/{id}.json` 的 `status=completed`。  
- 仅更新 outbox：`sent` / 回 `pending`+`error` / 已有 `skipped`。  
- 日志可打 `code`/`msg`；**禁止**打 `app_secret` / token。

---

## 8. 幂等确认

| 层 | 机制 |
|---|---|
| Outbox 写侧 | Worker：已有 notify/sent 不覆盖 |
| Consumer | claim → `sent/`；再扫 skip（已测 PASS） |
| 业务键 | **`job_id` 唯一**；成功后不得二次 `send_message`/`upload_file` |

真实 Client **不**额外做飞书侧去重；依赖文件系统 sent。进程在「已发送未 rename」窗口可能重复一次——记观察项，MVP 可接受。

---

## 9. mock → real 映射

| Mock | Real |
|---|---|
| `MockFeishuClient.send_message` | `RealFeishuClient.send_message` → IM text API |
| `MockFeishuClient.upload_file` | upload files API + IM file message |
| 无网络 | `requests` + env 凭证 |
| 记录 `calls` | 可选 debug 日志；正式不落敏感内容 |

建议类名：`RealFeishuClient`，与 `MockFeishuClient` 并列；`__main__` 用 `--real` 切换。

**明确不改：** `outbox_consumer.py` 的 claim/sent/skipped 逻辑。

---

## 10. Test plan（实现阶段）

| # | 内容 | 网络 |
|---|---|---|
| T1 | `RealFeishuClient` 用 `responses`/`unittest.mock` 假 HTTP：断言 URL/headers/body | 否 |
| T2 | consumer + RealClient(mock HTTP)：pending → sent | 否 |
| T3 | 人工真飞书：有效 `FEISHU_*` + 真实 `feishu_chat_id` outbox | 是 |
| T4 | 幂等：sent 后再跑不二次请求 | 否 |

实现完成后写：`feishu_notifier_test_report.md`（非本文）。

---

## 11. 建议实现顺序（本文不执行）

```text
0.4.3-c  RealFeishuClient + 异常类型 + token 缓存（单测 mock HTTP）
0.4.3-d  __main__ --real 接线；默认仍 mock
0.4.3-e  真飞书手工验收（需 chat_id 来源）
（并行可选）Skill/enqueue 写入 feishu_chat_id — 独立切片
```

---

## 12. 设计结论

1. **接口已定**：`send_message(chat_id, text)` / `upload_file(chat_id, file_path)`；真实实现保持签名。  
2. **方案 A**：自建应用 + env 凭证 + Open API；不写密钥进 outbox。  
3. **文件**：上传得 `file_key` 再发文件消息；禁止发本地路径。  
4. **chat_id 空 → skipped**；不猜测。  
5. **错误只影响 notify 态**；completed 不动。  
6. **consumer 逻辑冻结**；只新增 Real Client。

---

*v1.3-0.4.3-b 设计结束。下一步：实现 RealFeishuClient（仍可先 mock HTTP）；本文档内不改代码、不接 API。*
