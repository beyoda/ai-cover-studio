# AIVOICE v1.3-0.4.2 — Outbox Notification Architecture Design

> 日期：2026-07-27  
> 性质：**只设计，不改代码**  
>  
> 前置：  
> - v1.3-0.4.1 Hermes Skill Enqueue **PASS**（`hermes_skill_enqueue_integration_report.md`）  
> - Worker 稳定完成任务；`jobs/completed/{job_id}.json` + `outputs/{job_id}/cover.mp3` 已验证  
>  
> 目标：设计 **completed → outbox → notifier → Hermes/飞书** 的通知架构。  
> 对齐既有契约：`aivoice_v1.3_worker_interface_contract.md` §6、`aivoice_v1.3_worker_job_lifecycle_design.md` §6。

---

## 1. 当前缺口分析

### 1.1 已有链路

```text
Skill enqueue → jobs/queued/
       ↓
Worker claim → CoverService.run(job_id)
       ↓
jobs/completed|failed + outputs/{job_id}/cover.mp3
```

用户侧：Skill 已秒回 `queued`；**无人再把成品推回飞书**。

### 1.2 缺少的一环

```text
completed|failed
       ↓
notification event（持久化）
       ↓
notifier 发送文案 +（成功时）mp3
       ↓
notify_status = sent | failed | skipped
```

今日事实（验收样例 `709cf4b8f094`）：

| 项 | 状态 |
|---|---|
| `output_path` / `metadata.song|voice` / `hermes_session_id` | ✅ completed JSON 已有 |
| `feishu_chat_id` | ❌ 常为 `null`（Skill 尚未稳定写入）→ `notify_status=skipped` |
| `jobs/outbox/` 目录 | ✅ `FileJobQueue.ensure_layout` 已建 |
| Worker 写 outbox | ❌ `executor` / `complete_job` / `fail_job` **未写** |
| Notifier 进程 | ❌ 不存在 |

### 1.3 completed JSON 是否够用？

**执行结果：够用。**  
**通知投递：差一个稳定会话锚点。**

| 通知所需 | completed 来源 | 缺口 |
|---|---|---|
| `job_id` | 顶层 | — |
| `output_path` / `error` | 顶层 | — |
| `song` / `voice` | `metadata` | Skill 已写；缺则 fallback `source` / `voice_id` |
| `hermes_session_id` | 顶层 | 有则利于排障；**发飞书优先要 chat_id** |
| `feishu_chat_id` | 顶层 | **MVP 必填才能投递**；缺失 → skip，不写 pending outbox |
| 用户正文 | 可现算 | Notifier 或写 outbox 时用 `format_cover_done` / fail 文案 |

**结论：** 不必为通知再扩一套 Job schema；需要 **outbox 事件文件** + Skill/enqueue 侧尽量写入 `feishu_chat_id`。

### 1.4 是否需要 outbox schema？

**需要。** completed 是「任务真相」；outbox 是「投递工作项」，二者分离才能：

- 翻唱成功与发消息失败解耦  
- 独立重试、幂等、限速  
- Worker 零飞书依赖  

文件名沿用既有契约（勿另起冲突约定）：

```text
jobs/outbox/{job_id}.notify.json
```

（用户草案中的 `{job_id}.json` 易与 job 本体混淆；**本设计采用 `.notify.json` 后缀**。）

### 1.5 谁写 outbox？幂等谁保证？

见 §3：推荐 **Worker 在 complete/fail 事务尾部写 outbox（方案 A）**；Notifier 只消费 pending。  
幂等见 §7。

---

## 2. 设计目标

| # | 目标 | 含义 |
|---|---|---|
| 1 | 自动产生通知事件 | complete/fail 后磁盘上必有可扫描事件（或显式 skipped） |
| 2 | 不重复发送 | 同一 `job_id` 成功投递至多一次（用户可见） |
| 3 | 飞书失败可重试 | outbox 保留 pending/failed + `retry_count`；不改 job=`completed` |
| 4 | 不影响翻唱成功 | 写 outbox / 发送失败 **不得** 把已完成 job 打回 failed |
| 5 | Worker 不依赖飞书 SDK | Worker 只写文件；Notifier / Hermes 持凭证与发文件能力 |

非目标（本设计切片外）：

- 实时推 UVR/SVC percent 到飞书  
- 取消任务通知  
- 多渠道（邮件/Telegram）  

---

## 3. 设计方案比较

此处比较「**通知事件如何产生**」（与 lifecycle 里「谁调飞书」正交；飞书侧仍默认 Outbox+泵）。

### 方案 A — Worker 完成时直接写 outbox

```text
complete_job / fail_job
  →（同进程）atomic write outbox/{id}.notify.json status=pending
  → 返回；翻唱已成功落盘
```

| | |
|---|---|
| 复杂度 | 低：改 executor 或 queue 收尾钩子 |
| 可靠性 | 高：事件与终态同一执行者写出；少「漏扫」 |
| 适配度 | **最高**（目录已在、契约已有） |

风险：写 outbox 失败时策略需明确（见 §5.4）——**不得**回滚 completed。

### 方案 B — 独立 notifier 扫描 `completed/` / `failed/`

```text
Notifier 轮询 completed/*.json
  → 若 notify_status=pending 且有 chat_id → 合成并发送
  → 更新 job.notify_status
```

| | |
|---|---|
| 复杂度 | 中：要区分 skipped/pending/sent；与历史 completed 兼容 |
| 可靠性 | 中：依赖扫描间隔；进程挂了会积压但仍可补发 |
| 适配度 | 可作 **补扫 / 灾备**，不宜作唯一产生路径 |

风险：与「只读 completed」混用易重复；需强幂等标记。

### 方案 C — 事件总线（Redis/Queue/HTTP）

| | |
|---|---|
| 复杂度 | 高：新中间件、运维面 |
| 可靠性 | 视基建 |
| 适配度 | **低**（本机 Windows 单卡、FS 队列已够） |

### 推荐

**主路径：方案 A（Worker 写 outbox）。**  
**增强（可选，后期）：方案 B 作 reconcile**——仅处理 `notify_status=pending` 且 outbox 缺失的孤儿（崩溃窗口）。  
**不做：方案 C。**

飞书发送端（沿用 lifecycle 方案 B）：

```text
Notifier（独立进程或计划任务）
  → 读 outbox pending
  → 调 Hermes/飞书发文案+文件
  → 标记 sent / 退避重试
```

Worker **绝不** `import` 飞书 SDK。

---

## 4. Outbox JSON Schema

### 4.1 路径与命名

```text
jobs/outbox/{job_id}.notify.json          # 活跃（pending / retrying）
jobs/outbox/{job_id}.notify.sent.json     # 可选：成功后 rename（或改 status 后移到 outbox/sent/）
jobs/outbox/{job_id}.notify.dead.json     # 可选：超过 max_retry
```

MVP 可只保留单文件 + 字段 `notify_status` / `status`，用 rename 做物理隔离（推荐，扫描更简单）。

### 4.2 字段（相对契约 §6 的增量）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | int | ✅ | 固定 `1` |
| `job_id` | string | ✅ | |
| `type` | string | ✅ | `completed` \| `failed` |
| `chat_id` | string | ✅* | = `feishu_chat_id`；\*无则 **不创建** pending 文件，job → `skipped` |
| `hermes_session_id` | string \| null | 否 | 排障 / 将来映射 |
| `message` | string | ✅ | 用户可读正文（写盘时已渲染） |
| `file_path` | string \| null | 否 | completed 指向 mp3；failed 为 null |
| `song` | string \| null | 否 | 自 metadata / source |
| `voice` | string \| null | 否 | 自 metadata / voice_id |
| `output_path` | string \| null | 否 | 与 `file_path` 可同值；便于排障 |
| `created_at` | string ISO | ✅ | 事件创建时刻 |
| `updated_at` | string ISO | ✅ | 每次重试/状态变更新 |
| `status` | string | ✅ | `pending` \| `sent` \| `failed`（投递态；与 job 内 `notify_status` 对齐） |
| `retry_count` | int | ✅ | 初始 0；每次失败 +1 |
| `last_error` | string \| null | 否 | 最近一次发送错误（短文案） |
| `next_attempt_at` | string ISO \| null | 否 | 退避用；未到点 Notifier 跳过 |

### 4.3 完成示例

```json
{
  "schema_version": 1,
  "job_id": "709cf4b8f094",
  "type": "completed",
  "chat_id": "oc_xxx",
  "hermes_session_id": "integration-041d",
  "message": "完成！\n\n🎵 clip30\n🎤 ExampleVoiceB\n\n文件见附件。",
  "file_path": "<repo-root>\\outputs\\709cf4b8f094\\cover.mp3",
  "output_path": "<repo-root>\\outputs\\709cf4b8f094\\cover.mp3",
  "song": "clip30",
  "voice": "ExampleVoiceB",
  "created_at": "2026-07-27T22:24:58+08:00",
  "updated_at": "2026-07-27T22:24:58+08:00",
  "status": "pending",
  "retry_count": 0,
  "last_error": null,
  "next_attempt_at": null
}
```

### 4.4 与 job.`notify_status` 对齐

| 时机 | job.`notify_status` | outbox |
|---|---|---|
| enqueue 无 `feishu_chat_id` | `skipped` | **不写** |
| complete/fail 且有 chat_id | `pending` | 写 `status=pending` |
| 发送成功 | `sent` | `status=sent` 或 rename `.sent` |
| 发送失败（仍可重试） | `pending`（或 `failed` 仅表示最近一次） | `status=pending`/`failed` + `retry_count++` |
| 超过 max_retry | `failed` | `.dead` 或 `status=failed` 终态 |

**推荐：** job 侧枚举保持现有 `pending|sent|failed|skipped`；短暂发送失败时 job 仍 `pending`，避免与「任务 failed」语义混淆。

---

## 5. Notifier 生命周期

### 5.1 进程形态（实现阶段再定一）

| 选项 | 说明 |
|---|---|
| **N1** `python -m aivoice_studio.notify` 常驻 | 与 Worker 分窗；推荐 MVP |
| **N2** 任务计划每 N 秒跑一次 | 简单；延迟=周期 |
| **N3** Hermes cron / Skill 扫 outbox | 复用飞书会话；耦合 Hermes 调度 |

**推荐 N1 或 N2**；发送库优先走「已登录的 Hermes/飞书通道」适配器，接口形状：

```text
send_text(chat_id, message) -> None
send_file(chat_id, file_path, caption?) -> None
```

适配器内部可先 stub / 日志，再接真飞书。

### 5.2 主循环

```text
loop:
  scan jobs/outbox/*.notify.json
    where status in (pending, failed)   # failed=可重试
    and (next_attempt_at is null or now >= next_attempt_at)
  for each event (oldest first):
    claim: atomic rename → *.notify.sending.json  (或文件锁)
    validate:
      chat_id 非空
      type=completed ⇒ file_path 存在且 size>阈值
      type=failed ⇒ message 非空
    send text
    if completed and file_path: send file
    on success:
      status=sent; update job.notify_status=sent
      rename → *.notify.sent.json (或移出)
    on failure:
      retry_count += 1
      last_error = short
      next_attempt_at = now + backoff(retry_count)
      if retry_count > MAX: → dead; job.notify_status=failed
      else: 回到 pending（或保持 failed-as-retryable）
  sleep idle_s
```

### 5.3 退避建议

```text
MAX_RETRY = 5
backoff = min(300, 15 * 2^retry_count)  # 秒
```

### 5.4 Worker 写 outbox 失败策略

```text
complete_job 已成功
→ try write outbox
→ 若写盘失败: 记 Worker 日志；job.notify_status 保持 pending（若有 chat_id）
→ 不抛到让整单变 failed
→ 可选：方案 B reconcile 稍后补写
```

**铁律：通知子系统故障 ≠ 翻唱失败。**

### 5.4b 无 chat_id

```text
complete/fail 时:
  if not feishu_chat_id:
    job.notify_status = skipped
    不写 outbox
    return
```

与当前 enqueue 行为（`notify_status=skipped`）一致；集成验收样例即此状态——**产品上需在 Skill 补 `feishu_chat_id` 后通知才闭环**。

---

## 6. 飞书边界

```text
┌─────────────┐     enqueue only      ┌──────────────┐
│ Hermes Skill│ ───────────────────► │ FileJobQueue │
└─────────────┘                       └──────┬───────┘
                                             │ claim
                                      ┌──────▼───────┐
                                      │    Worker    │  ← 无飞书 SDK
                                      │ complete/fail│
                                      │ + write outbox│
                                      └──────┬───────┘
                                             │
                                      ┌──────▼───────┐
                                      │   Notifier   │  ← 唯一发送者
                                      │ 飞书/Hermes  │
                                      └──────────────┘
```

| 组件 | 做 | 不做 |
|---|---|---|
| **Skill** | 选曲、落地音频、`enqueue_job`（尽量带 `feishu_chat_id`） | 发 mp3、poll completed |
| **Worker** | 翻唱、写 completed/failed、写 outbox | 调飞书、持 app secret |
| **Notifier** | 扫 outbox、发文案/文件、标 sent/retry | 跑 UVR/SVC、改 Pipeline |
| **Hermes Agent** | 转发 Skill 的 queued ACK | 本轮假设有 output_path |

---

## 7. 幂等设计

| 场景 | 策略 |
|---|---|
| Worker 重复写同一 outbox | 若已存在 `sent` / `.sent` → **不再覆盖**；若 `pending` 且内容等价 → no-op |
| Notifier 双实例 | outbox 文件 `rename` claim（`.sending`）；丢锁者跳过 |
| 进程在「已发送未标 sent」崩溃 | 可能重复发一次 —— 可接受；降低办法：先标 `sending`+记录 `send_attempt_id`，飞书侧若有消息 id 可去重（MVP 不做） |
| 网络失败后重试 | 同 `job_id` 同一文件；用户可能收到重复 —— 用「文案含 job_id 短码」便于辨认；`MAX_RETRY` 封顶 |
| 重复扫 completed（方案 B） | 仅当 `notify_status=pending` 且无 outbox/无 sent 时补写；`sent`/`skipped` 永不补发 |
| 文件已被删 | completed 通知：发送前校验 `file_path`；缺失则改 type 文案为失败通知或 dead，**不**改 job status=completed |
| Skill 无 chat_id | skipped，永不进入发送队列 |

**核心幂等键：`job_id`（每任务至多一条活跃 notify 生命周期）。**

---

## 8. 验收标准（实现阶段对照）

### 8.1 outbox 生成

- [ ] 有 `feishu_chat_id` 的 job：`complete` 后存在 `outbox/{id}.notify.json`，`status=pending`，`file_path` 指向真实 mp3  
- [ ] `fail` 后存在 failed 型 outbox（无 file 或 null）  
- [ ] 无 `feishu_chat_id`：`notify_status=skipped`，**无** pending outbox  
- [ ] 写 outbox 抛错时 job 仍为 `completed`/`failed`（翻唱结果不变）

### 8.2 notifier 消费

- [ ] pending → 发送成功 → `sent`（或 `.sent`）；job.`notify_status=sent`  
- [ ] 用户侧收到文案；（completed）收到可播放 mp3  

### 8.3 失败重试

- [ ] 模拟发送失败 → `retry_count` 增加、`next_attempt_at` 推迟、仍可再次消费  
- [ ] 超过 `MAX_RETRY` → dead；job.`notify_status=failed`；翻唱 completed 不变  

### 8.4 重复保护

- [ ] 连续跑两次 Notifier：用户不因第二次成功路径再收第二份（已 sent 跳过）  
- [ ] 双 Notifier 争同一文件：仅一方 claim 成功  

### 8.5 回归

- [ ] Skill enqueue → Worker → completed 路径不被通知改动破坏（可复用 0.4.1-d 验收）  
- [ ] Worker 进程内无飞书 import  

---

## 9. 建议实现顺序（本文不执行）

```text
0.4.2-a  Skill/enqueue 写入 feishu_chat_id（若可从 session 推导）
0.4.2-b  Worker complete/fail 钩子写 outbox（无飞书）
0.4.2-c  Notifier 骨架：扫描 + 日志适配器（先 dry-run 不真发）
0.4.2-d  接真飞书/Hermes 发送 + 重试/幂等
0.4.2-e  集成验收报告 + 可选 completed reconcile
```

报告建议：`outbox_notification_report.md`。

---

## 10. 设计结论

1. **缺口**是「投递工作项」，不是再造 JobStore；completed 字段基本够用，缺稳定 **`feishu_chat_id`**。  
2. **主路径：Worker 写 `jobs/outbox/{job_id}.notify.json`（方案 A）**；Notifier 独占飞书发送。  
3. **扫描 completed（方案 B）** 仅作崩溃补洞；**不做事件总线（方案 C）**。  
4. 通知失败 **不得** 否定翻唱成功；幂等键为 **`job_id`**。  
5. Skill 只 enqueue；Worker 不碰飞书；闭环靠 outbox + Notifier。  

---

*v1.3-0.4.2 设计结束。下一步：评审后按 §9 实现；本文档内不改代码。*
