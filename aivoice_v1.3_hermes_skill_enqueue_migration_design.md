# AIVOICE v1.3-0.4.0 — Hermes Skill Enqueue Migration Design

> 日期：2026-07-27  
> 阶段：Hermes Skill 从同步执行迁移到 FS Queue 异步提交  
>  
> 前置：  
> - v1.3-0.3.3 Worker E2E Smoke **PASS**（`worker_e2e_smoke_report.md`）  
> - FileJobQueue 已稳定  
> - Worker 已真实执行 `CoverService.run(job_id=…)`  
> - `job_id` / `outputs/{job_id}` 对齐已验证  
>  
> 本阶段性质：  
> **只设计，不实现代码**

---

## 1. 当前状态

### 1.1 已完成（执行器侧）

```text
FileJobQueue
    ↓
Worker Runtime（claim → execute）
    ↓
CoverService.run(job_id=…)
    ↓
Pipeline / UVR / SVC / Mix / Export
    ↓
jobs/completed|failed + outputs/{job_id}/cover.mp3
```

冒烟已证明：真实音频下 `queued → running → completed`，且 **A6**（输出父目录 == FS `job_id`）成立。

### 1.2 仍未迁移（消息 / Skill 侧）

```text
飞书 → Hermes Agent → aivoice_cover.py
                         ↓
              MusicSource（search / pick / 本地下载）  ← 可保留同步
                         ↓
              CoverService.submit(cover_req)
                         ↓
              同进程 while status 轮询 ≤ 600s          ← 阻塞点
                         ↓
              emit completed JSON + Agent 当轮发 mp3
```

要点（见 `aivoice_v1.3_async_worker_phase1_analysis.md`）：

| 表象 | 实际 |
|---|---|
| stdout 有 `status=queued` | 随后仍在同一次 tool 内 poll 到终态 |
| CoverService 有 async API | JobStore **内存**；Skill 进程不退出则 Hermes 不能结束本轮 |
| 用户感知 | 飞书侧「卡住等翻唱」 |

Worker 已能吃队列，但 **Skill 仍不写 `jobs/queued/`**，两条执行路径并存：

1. **Worker 路径**（冒烟 / 手工 enqueue）— 正确目标形态  
2. **Skill 路径**（`submit` + poll）— 仍抢 GPU、仍阻塞 Hermes  

若 Skill 不改，飞书用户永远走不到 Worker。

---

## 2. 本切片目标

把 Hermes Skill 的「翻唱执行」从 **同进程长跑** 改为 **FS enqueue + 立即 ACK**，使：

1. Agent tool 在入队成功后 **秒级退出**；  
2. 翻唱只由 **常驻 Worker** 消费；  
3. 用户立刻收到「已排队」类话术；  
4. **完成文件投递** 走后续 outbox / 泵（本切片可只预留字段与边界，不强求泵落地）。

**一句话：** Skill 从「执行器」降级为「选曲 + 入队前台」。

---

## 3. 非目标（明确不做）

| 不做 | 原因 |
|---|---|
| 改 Pipeline / UVR / SVC / GUI | 执行器已稳定；本切片只动投递入口 |
| 改 `CoverService.run` / Worker `executor` | E2E 已 PASS，禁止回归 |
| 改 FileJobQueue 公开 API 语义 | Skill 只调用已有 `enqueue_job` |
| 本切片内落地完整飞书 outbox 泵 | 可分 0.4.1；0.4.0 先切断阻塞 poll |
| 取消 / 重试 / stale `running/` 恢复 | 另切片 |
| HTTP Job API | 非 MVP |
| 让 Agent 再开第二轮 tool 去 poll 整单 | 会把阻塞挪回 Hermes，违背目标 |

---

## 4. 目标调用链

```text
飞书用户
  → Hermes Agent（SKILL.md）
  → aivoice_cover.py
       ├─ --search / --list-voices / choice_needed     【仍同步、短】
       ├─ --pick / 本地·URL 解析 → 得到 input_audio    【仍同步、短～中】
       └─ FileJobQueue.enqueue_job(...)               【写 queued/，立即返回】
  → stdout/stderr：status=queued + user_message
  → Agent 转发「已排队」→ tool 结束

常驻 Worker（已有）
  → claim → CoverService.run(job_id) → completed/failed
  →（预留）写 jobs/outbox/{job_id}.notify.json

Notifier / 泵（后续切片）
  → 读 outbox → 飞书发文案 + cover.mp3
```

选歌 `choice_needed` **不是** Job；只有确认版本并解析出本地 `input_audio` 后才允许 enqueue（契约：`aivoice_v1.3_worker_interface_contract.md` §3.4）。

---

## 5. Skill 改造设计

### 5.1 保留不变（同步前台）

| 能力 | 说明 |
|---|---|
| `--search` / `--pick` / session 状态机 | 体验切片已稳定 |
| `--list-voices` / `--parse` | 短查询 |
| MusicSource 下载到本地 | enqueue 前必须有绝对路径 `input_audio` |
| `build_cover_request_for_voice` 或等价校验 | **可在 enqueue 前做一次校验**（音色存在、参数合法），但 **不要** 再 `submit` |
| 友好 `user_message` / `pretty` | 继续由脚本产出，Agent 原样转发 |
| `PYTHONPATH` 纪律 | 仍 unset + 用 AIVOICE `.venv` |

### 5.2 必须删除 / 绕开的行为

在 `run_cover_request`（及 pick 后走 cover 的路径）中：

```text
❌ CoverService()
❌ service.submit(cover_req)
❌ while status 轮询（timeout / poll_interval）
❌ service.result / service.shutdown(wait=True)
❌ 在同一次调用里 emit status=completed + output_path（正常异步路径）
```

替换为：

```text
✅ 解析 audio.path + voice_id + pitch + options
✅ FileJobQueue(jobs_root?).enqueue_job(
     input_audio=...,
     voice_id=...,
     pitch=...,
     options=...,
     source=...,
     provider=...,
     track_id=...,
     requester=...,
     feishu_chat_id=...,
     hermes_session_id=...,
     metadata={ song, voice_label, smoke:false, ... },
   )
✅ emit status=queued + job_id + user_message → exit 0
```

### 5.3 推荐代码落点（实现阶段，本设计不定 patch）

| 触点 | 建议 |
|---|---|
| `hermes_skill/.../aivoice_cover.py` | `run_cover_request` 改为 enqueue；CLI 可加 `--sync-legacy` **仅应急**（默认关） |
| `SKILL.md` | Overview / Flow A·B：完成后发 mp3 → 改为「回已排队；成品由后续通知」 |
| `user_messages.py` | 增加 / 调整「已入队」文案；去掉依赖本轮 duration 的完成句（完成句归泵） |
| `session_state.py` | pick 入队成功后：可 `clear_session` 或标 `stage=queued` + 记 `job_id`（二选一，见 §5.5） |
| 验收脚本 `validate_e2e.py` 等 | 期望从 `completed` 改为 `queued`（或单独 `validate_enqueue.py`） |

**禁止** 为迁 Skill 去改 `src/aivoice_studio/worker/executor.py` / Pipeline。

### 5.4 Skill 最小输出契约（给 Hermes）

入队成功：

```json
{
  "status": "queued",
  "job_id": "a55442027dba",
  "song": "示例曲目",
  "voice": "ExampleVoiceB",
  "pitch": 0,
  "output_path": null,
  "error": null,
  "user_message": "已收到，翻唱已进入制作队列。完成后会发到本会话。",
  "pretty": "已收到，翻唱已进入制作队列。完成后会发到本会话。"
}
```

| 字段 | 规则 |
|---|---|
| `status` | 固定 `queued`（成功入队） |
| `job_id` | FS Queue 生成的 id，与后续 `outputs/{job_id}` 一致 |
| `output_path` | **null**（本轮不提供成品路径） |
| exit code | `0` |
| stderr | 可再打一行 ACK，供 Agent 转发 |

入队前失败（缺音色、搜歌失败、下载失败等）仍走现有 `_fail` / `choice_needed`，**不写** `queued/`。

### 5.5 Session 状态

| 方案 | 行为 | 推荐 |
|---|---|---|
| **A. 入队后 clear** | 与现「完成后 clear」类似；用户再来是新会话流程 | **MVP 推荐**（简单） |
| **B. 记 job_id** | `stage=queued`，支持「我的任务怎样了」短查 FS | 增强项；需只读 `find_job_path`，**禁止**长轮询 |

本设计默认 **A**；若实现 B，查询必须秒回，不得阻塞等 Worker。

### 5.6 飞书上下文如何进 job

Worker / 未来 outbox 需要知道「回哪个会话」：

| 字段 | 来源建议 |
|---|---|
| `hermes_session_id` | 现有 `--session-id` |
| `feishu_chat_id` | 从 session id 推导，或新增 CLI `--feishu-chat-id`；缺失则 `notify_status=skipped`，仍可完成翻唱 |
| `requester` | 可选；有则写入 |

**实现约束：** 不把飞书 token 写进 job JSON。

---

## 6. 与 Worker / Outbox 的边界

### 6.1 本切片（0.4.0）必须对齐

| 项 | 要求 |
|---|---|
| 入队 API | 只用已有 `FileJobQueue.enqueue_job` |
| `input_audio` | 绝对路径且文件已存在 |
| 执行 | **仅 Worker**；Skill 不再 `CoverService.submit` |
| GPU | Skill 入队后立即释放进程；避免与 Worker 双跑 |

### 6.2 本切片可预留、不强求完成

| 项 | 说明 |
|---|---|
| Worker 写 `jobs/outbox/*.notify.json` | 契约已有；可在 0.4.1 与 Skill 迁移拆开或紧随 |
| Hermes / 泵发文件 | 用户暂时只收到「已排队」；成品需泵或临时人工从 `outputs/` 取 |
| Agent 本轮 `send_file(cover.mp3)` | **删除**该期望；否则 Agent 会空等 `output_path` |

**产品过渡话术（设计约定）：**

> 已排队；完成后会推送到本会话。  
> （若泵未上线：报告中标注「通知未接，仅队列+Worker」——不可对外宣称飞书闭环完成。）

### 6.3 推荐通知方案（沿用既有结论）

继续采用 **Outbox + 泵**（lifecycle 设计 §6.2 方案 B）：

- Worker 不直连飞书 SDK；  
- Skill 不负责发完成文件；  
- 泵幂等消费 `outbox/`。

0.4.0 迁移 Skill 时，**至少**把 `feishu_chat_id` / `hermes_session_id` 写入 job，避免泵上线后无法回溯会话。

---

## 7. SKILL.md 行为变更（设计稿）

### 7.1 Overview 替换

```text
Hermes → aivoice_cover.py
  --search / --pick / --list-voices / …
  → session + MusicSource（得到本地音频）
  → FileJobQueue.enqueue_job → 立即 queued ACK
  →（常驻 Worker 异步制作；完成后由 outbox/泵通知）
```

### 7.2 Hard rules 增补

1. 翻唱入队成功后 **停止本轮 tool**，不要再跑第二条 cover 命令「等完成」。  
2. **禁止** 为了拿 `output_path` 而循环调用 Skill。  
3. 用户问进度：可读 `jobs/` 短查或回复「制作中，完成后推送」——**不要** 同步重跑翻唱。  
4. 同一时间仍「业务上单用户一单」；真正串行由 Worker + lock 保证。

### 7.3 Flow A（搜歌）终态变化

| 步骤 | 旧 | 新 |
|---|---|---|
| `--pick 1` | 阻塞至 completed，Agent 发 mp3 | 下载+enqueue → `queued` ACK → **结束** |
| 完成投递 | 同轮 Agent | outbox 泵（后续） |

`--dry-run` 仍只生成 request / 不入队。

---

## 8. 兼容与回滚

| 机制 | 用途 |
|---|---|
| `--sync-legacy`（可选） | 紧急回退旧 `submit+poll`；默认 **关闭**；文档标明「会阻塞且与 Worker 抢 GPU」 |
| 环境变量 `AIVOICE_SKILL_ENQUEUE=0` | 同上，便于运维开关 |
| 冒烟脚本 | 继续直接 enqueue，不依赖 Skill |

**默认路径必须是 enqueue。** Legacy 仅灾难开关，不作双轨产品。

---

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 用户只见「已排队」、迟迟无 mp3 | 0.4.0 报告标明通知缺口；尽快 0.4.1 outbox 泵；过渡期可人工看 `outputs/` |
| Skill 与 Worker 同时跑旧路径 | 默认关 legacy；SKILL 禁止长跑；GUI 约定互斥 |
| `feishu_chat_id` 缺失 | 仍可完成；`notify_status=skipped`；泵跳过 |
| Agent 仍按旧 MEMORY 去「等完成」 | 改 SKILL.md + 清理相关 MEMORY；验收列检查项 |
| 下载仍慢，tool 不算「秒回」 | 可接受：阻塞在 MusicSource，不在 UVR/SVC；文案可先「正在准备音源」再「已排队」 |
| 校验音色失败却已写队列 | enqueue **前**做 Registry 解析；失败不入队 |

---

## 10. 验收标准（实现阶段对照）

### Must Pass

1. 飞书或本地模拟：`--pick` / 本地音频路径 → Skill 退出码 0，耗时 **远小于** 整单翻唱（无 UVR/SVC 日志）。  
2. `jobs/queued/{job_id}.json` 存在且 `input_audio` 指向真实文件。  
3. 常驻 Worker（或 `--once`）能 claim 并完成；`outputs/{job_id}/cover.mp3` 父目录 == `job_id`。  
4. Skill 进程 stdout **无** 本轮 `status=completed`（正常 enqueue 路径）。  
5. SKILL.md / Agent 行为：入队后不二次阻塞 poll。  

### Should Pass

6. job 含 `hermes_session_id`（及可得的 `feishu_chat_id`）。  
7. 故意错误音色 / 缺文件在 **enqueue 前** 失败，不留下脏 queued（缺文件若已入队则仍由 Worker `failed/`——与冒烟 F1 一致；Skill 侧应尽量前置校验路径）。  

### 非本切片门禁

8. 飞书自动收到 mp3（属 outbox 泵切片）。

---

## 11. 建议实现顺序（下一切片，非本文执行）

```text
0.4.0-a  aivoice_cover.py：submit+poll → enqueue_job；默认关 legacy
0.4.0-b  SKILL.md + user_message + session 策略 A
0.4.0-c  validate_enqueue / 改 validate_e2e 期望
0.4.0-d  手工：Skill enqueue → Worker --once → 断言 outputs（可复用 smoke 思路）
0.4.1    Worker complete/fail → 写 outbox；最小泵 → 飞书发文件
```

报告建议：`hermes_skill_enqueue_migration_report.md`（实现后填 PASS/FAIL；区分「入队迁移」与「通知闭环」）。

---

## 12. 设计结论

1. **阻塞根因在 Skill 同进程 poll**，不在 CoverService / Worker；E2E PASS 后应立刻切投递入口。  
2. Skill **只负责** 选曲、落地 `input_audio`、`enqueue_job`、立即 ACK。  
3. **禁止** Skill 再 `CoverService.submit` 长跑（除非显式 legacy 灾难开关）。  
4. 完成投递走 **outbox**；0.4.0 可先切 enqueue，但必须改掉 Agent「本轮发 mp3」的契约，避免假完成。  
5. 不改 Pipeline / UVR / SVC / Worker 执行逻辑 / FileJobQueue API。  

---

## 13. 与既有文档关系

| 文档 | 关系 |
|---|---|
| `aivoice_v1.3_worker_interface_contract.md` §3 | Skill enqueue 输入/输出契约源 |
| `aivoice_v1.3_worker_job_lifecycle_design.md` §6 | Outbox 方案 B |
| `aivoice_v1.3_async_worker_phase1_analysis.md` | 同步阻塞根因分析 |
| `worker_e2e_smoke_report.md` | 执行器门禁已 PASS，允许开本迁移设计 |

---

*v1.3-0.4.0 设计结束。下一步：评审本设计后实现 Skill enqueue（仍可不做飞书泵）；实现时另开切片，勿在本文档内直接改代码。*
