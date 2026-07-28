# AIVOICE v1.3 Async Worker — Phase 2-3 Interface Contract Design

> 日期：2026-07-27  
> 阶段：接口契约（不实现、不改现有模块代码）  
> 前置：Phase 1 分析 · Phase 2-1 放置（Option A）· Phase 2-2 生命周期  

**已定决策回顾**

| 项 | 决定 |
|---|---|
| 部署 | 独立 Worker 进程 |
| 队列 | Filesystem Queue |
| 记录 | JSON per Job |
| 状态真相 | Worker / FS 持久化 |
| 通知 | Outbox |
| 执行栈 | CoverService / Pipeline / UVR / SVC **不变** |

---

## 1. Job JSON Schema

每个任务对应一个文件：`jobs/{bucket}/{job_id}.json`。  
`bucket ∈ {queued, running, completed, failed, cancelled}`。

### 1.1 字段表

#### 请求字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `job_id` | string | ✅ | 12 位 hex，与 `outputs/{job_id}` 对齐 |
| `created_at` | string (ISO-8601) | ✅ | enqueue 时刻 |
| `source` | string \| null | 否 | 用户歌名/展示用查询 |
| `input_audio` | string | ✅* | 本地绝对路径；enqueue 前必须已解析落盘 |
| `provider` | string \| null | 否 | `local` \| `gdstudio` \| `url` |
| `track_id` | string \| null | 否 | GD track id |
| `voice_id` | string | ✅ | Registry id |
| `pitch` | integer | ✅ | 默认 `0` |
| `options` | object | ✅ | 至少含可重建 CoverRequest 的键 |

\* 若仅有 `source` 无 `input_audio`：属于选歌未完成，**不得**进入 `queued/`（仍走 Skill 同步 search/pick）。

`options` 约定键：

| 键 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `reverb` | string | `"关闭"` | 与现 CoverRequest 一致 |
| `export_mp3` | boolean | `true` | |
| `f0_method` | string | `"rmvpe"` | |
| `accompaniment` | string | `""` | 可选 |

#### 用户上下文字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `requester` | string \| null | 否 | 飞书 open_id / 显示名 |
| `feishu_chat_id` | string \| null | 建议✅ | 无则 `notify_status=skipped` |
| `hermes_session_id` | string \| null | 否 | 关联选歌 session |

#### 生命周期字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `status` | string enum | ✅ | `queued`\|`running`\|`completed`\|`failed`\|`cancelled` |
| `current_stage` | string \| null | 否 | 见 §5；queued 时可为 `null`/`pending` |
| `progress` | object \| null | 否 | `{ "percent": number\|null, "message": string\|null }` |
| `updated_at` | string ISO | ✅ | 任意变更刷新 |
| `started_at` | string ISO \| null | 否 | claim 时写入 |
| `finished_at` | string ISO \| null | 否 | 终态写入 |

#### 结果与通知字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `output_path` | string \| null | 否 | 成功时 mp3 优先 |
| `error` | string \| null | 否 | **用户可读**，禁止堆栈 |
| `notify_status` | string enum | ✅ | `pending`\|`sent`\|`failed`\|`skipped` |
| `metadata` | object | 否 | 扩展袋（`client`,`song_display_name`,…） |

状态字符串与目录 bucket **必须一致**（小写）：文件在 `running/` 则 `status` 必为 `"running"`。

### 1.2 示例：刚入队

```json
{
  "job_id": "a55442027dba",
  "created_at": "2026-07-27T14:00:00+08:00",
  "updated_at": "2026-07-27T14:00:00+08:00",
  "source": "示例歌手的示例曲目",
  "input_audio": "<repo-root>\\workdir\\music_source\\gdstudio\\72134026573bd47b\\source.mp3",
  "provider": "gdstudio",
  "track_id": "3382908505",
  "voice_id": "example_voice_b",
  "pitch": 0,
  "options": {
    "reverb": "关闭",
    "export_mp3": true,
    "f0_method": "rmvpe",
    "accompaniment": ""
  },
  "requester": "ou_xxx",
  "feishu_chat_id": "oc_xxx",
  "hermes_session_id": "feishu_oc_xxx",
  "status": "queued",
  "current_stage": "pending",
  "progress": null,
  "started_at": null,
  "finished_at": null,
  "output_path": null,
  "error": null,
  "notify_status": "pending",
  "metadata": {
    "client": "hermes",
    "song_display_name": "示例曲目",
    "chosen_label": "示例曲目 - ExampleArtist"
  }
}
```

### 1.3 示例：成功完成（节选变更）

```json
{
  "status": "completed",
  "current_stage": "done",
  "progress": { "percent": 100, "message": "导出完成" },
  "started_at": "2026-07-27T14:00:01+08:00",
  "finished_at": "2026-07-27T14:01:28+08:00",
  "updated_at": "2026-07-27T14:01:28+08:00",
  "output_path": "<repo-root>\\outputs\\a55442027dba\\cover.mp3",
  "error": null,
  "notify_status": "pending"
}
```

---

## 2. Queue 文件协议

### 2.1 目录契约

根目录（逻辑名 `JOBS_ROOT`，建议 `<repo-root>\jobs\`）：

```text
jobs/
  queued/
  running/
  completed/
  failed/
  cancelled/
  outbox/
  worker.lock
```

规则：

- 每个非 outbox 子目录内：`{job_id}.json` 至多一份。  
- **同一 `job_id` 全局唯一**：不得同时出现在两个 bucket。  
- outbox：`{job_id}.notify.json`（见 §6）。

### 2.2 enqueue

| 问题 | 契约 |
|---|---|
| **谁创建 `queued/` 文件？** | **Skill 侧（或专用 enqueue CLI）**，不是 Worker |
| Worker 是否写 queued？ | 否（仅消费） |

流程：

1. Skill 完成 MusicSource（得到 `input_audio`）+ 解析 `voice_id` 等。  
2. 生成 `job_id`（与现规则一致：12 hex）。  
3. 写临时文件再 rename 进 `queued/{job_id}.json`（避免半写入）。  
4. 立刻返回 `{status:"queued", job_id}`，**不**调用 CoverService 长跑。

### 2.3 claim

| 问题 | 契约 |
|---|---|
| **如何 claim？** | Worker 对候选文件执行 **同卷原子 `rename(queued/X → running/X)`** |
| 成功 | 视为独占；随后更新 JSON：`status=running`，写 `started_at`/`updated_at` |
| 失败（文件已不在） | 跳过，认领下一单 |
| lock | **不做** per-job 额外 lock 文件；互斥靠 rename + `worker.lock`（§7） |
| timestamp | claim 时写 `started_at`；循环中可写 `metadata.last_heartbeat_at`（恢复用） |

禁止：先读 JSON 再删 queued（非原子，双 Worker 会双跑）。

### 2.4 完成移动

| 结果 | 动作 |
|---|---|
| 成功 | 更新 JSON 字段 → **`rename(running → completed)`** |
| 失败 | 更新 `error` → **`rename(running → failed)`** |
| 取消（MVP 暂缓） | `rename(queued → cancelled)` 或 running→cancelled（若实现取消） |

**文件所在目录即主状态的物理投影**；JSON 内 `status` 必须在 rename 前后与目录一致（先改 JSON 再 rename，或 rename 后立刻改——实现任选，契约要求二者最终一致）。

---

## 3. Skill → Worker 接口

### 3.1 从「submit + poll」到「enqueue」

| | 当前 | v1.3 契约 |
|---|---|---|
| Skill | `CoverService.submit` + 同进程 poll ≤600s | 只 **enqueue** 到 `queued/` |
| 返回时机 | 整单结束后 | 入队成功后立即 |
| 长任务 | 占用 Hermes tool | Worker 常驻执行 |

### 3.2 Skill 最小输入（enqueue 请求逻辑体）

Skill 在写 `queued/{job_id}.json` 前必须备齐：

```json
{
  "source": "示例歌手的示例曲目",
  "input_audio": "D:\\...\\source.mp3",
  "provider": "gdstudio",
  "track_id": "3382908505",
  "voice_id": "example_voice_b",
  "pitch": 0,
  "options": { "reverb": "关闭", "export_mp3": true },
  "requester": "ou_xxx",
  "feishu_chat_id": "oc_xxx",
  "hermes_session_id": "feishu_oc_xxx"
}
```

`job_id` / `created_at` / `status:"queued"` / `notify_status:"pending"` 由 enqueue 例程填充。

### 3.3 Skill 最小输出（给 Hermes / 用户）

```json
{
  "status": "queued",
  "job_id": "a55442027dba",
  "user_message": "已收到，翻唱已进入制作队列。完成后会发到本会话。"
}
```

### 3.4 Skill 最小职责（契约边界）

**负责**

- 音色 / 歌名解析、搜歌、session pick（可仍同步）  
- 解析出本地 `input_audio`  
- enqueue + 立即 ACK  
- （可选）查询 Persistent 状态做短答，**禁止**再阻塞整单 UVR/SVC  

**不负责**

- 跑 Pipeline / CoverService 长任务  
- 直接发完成文件（交给 outbox 泵）  
- 持有 GPU  

选歌 `choice_needed` **不是** Job；只有用户确认版本并解析出音频后才 enqueue。

---

## 4. Worker → CoverService 接口

### 4.1 方案比较

| 方案 | 调用 | 优点 | 缺点 |
|---|---|---|---|
| **A. `CoverService.run()`** | 同步，当前线程跑完返回 `CoverResult` | 与 GUI 同路径；Worker 单线程天然串行；无需同进程再 poll | 进度需 `on_progress` 回调写入 FS |
| **B. `CoverService.submit()`** | 线程池 + status 轮询 | 复用现有 async API 外形 | Worker 内再建线程池多余；shutdown 生命周期啰嗦 |

### 4.2 推荐

**推荐方案 A：`CoverService.run(request, on_progress=...)`。**

理由：

1. Worker 已是常驻单线程消费者，不需要再套一层 `max_workers=1` 线程池。  
2. GUI 今天就走 `run()`——Worker 对齐同一执行入口，行为一致。  
3. Pipeline / Adapter / UVR / SVC **零改动**；仅 Worker 把 `on_progress` 落到 job JSON。  
4. `submit` 留给「将来 HTTP 多客户端共用一个进程内服务」；非 MVP 必需。

Worker 构造 `CoverRequest` 时字段来自 job JSON（`input_audio`→`input_audio`，`voice_id`，`pitch`，`options`…），`job_id=` 传入 Adapter/Pipeline 以保持输出目录一致（若 `run` 当前签名需 `job_id`，实现阶段用 Adapter 已有参数；**契约要求成品落在 `outputs/{job_id}/`**）。

---

## 5. Worker Progress Interface

### 5.1 来源

现有 `ProgressEvent`（Adapter 从 Pipeline `JobState` 映射）→ Worker `on_progress`。

### 5.2 Stage 列表（写入 `current_stage`）

| stage | 含义 | 用户可见文案（建议） |
|---|---|---|
| `pending` | 已排队 / 刚 claim | 排队中 / 准备开始 |
| `uvr` | 人声分离 | `[1/3] 人声分离` |
| `svc` | 音色转换 | `[2/3] AI音色转换` |
| `mixing` | 混音 | `[3/3] 混音导出` |
| `exporting` | 导出 | `[3/3] 混音导出` |
| `done` | 成功结束 | 完成 |
| `failed` | 失败 | 制作失败 |

（与现有 Stage / UX 文案对齐；`vocal_fx` 若出现可并入 `mixing` 展示。）

### 5.3 持久化进度对象

```json
{
  "current_stage": "svc",
  "progress": {
    "percent": 70,
    "message": "音色转换中"
  },
  "updated_at": "2026-07-27T14:00:45+08:00"
}
```

契约：

- **stage 变化必写盘**；percent 可节流（如 ≥5% 或每 N 秒）。  
- 不向飞书实时推每一个 percent（MVP）；完成靠 outbox。  
- 禁止伪造未发生的 stage。

---

## 6. Outbox Notification Schema

路径：`jobs/outbox/{job_id}.notify.json`

### 6.1 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `job_id` | string | ✅ | |
| `chat_id` | string | ✅ | 即 `feishu_chat_id`；缺失则不写 outbox，job.`notify_status=skipped` |
| `type` | string | ✅ | `completed` \| `failed` |
| `message` | string | ✅ | 用户可读正文 |
| `file_path` | string \| null | 否 | completed 时指向 mp3；failed 通常 null |
| `created_at` | string ISO | ✅ | |
| `status` | string | ✅ | outbox 投递态：`pending`\|`sent`\|`failed` |

与 job.`notify_status` 应对齐演进：outbox `sent` ⇒ job `notify_status=sent`。

### 6.2 示例：完成

```json
{
  "job_id": "a55442027dba",
  "chat_id": "oc_xxx",
  "type": "completed",
  "message": "完成！\n\n🎵 示例曲目\n🎤 ExampleVoiceB\n\n文件见附件。",
  "file_path": "<repo-root>\\outputs\\a55442027dba\\cover.mp3",
  "created_at": "2026-07-27T14:01:28+08:00",
  "status": "pending"
}
```

### 6.3 示例：失败

```json
{
  "job_id": "a55442027dba",
  "chat_id": "oc_xxx",
  "type": "failed",
  "message": "翻唱失败：人声分离阶段出错。可以换一首或稍后再试。",
  "file_path": null,
  "created_at": "2026-07-27T14:01:28+08:00",
  "status": "pending"
}
```

泵端：发送成功后将 outbox `status`→`sent`，或 rename 为 `{job_id}.notify.sent.json` / 移出目录（实现任选，需幂等）。

---

## 7. Worker Lock Contract

路径：`jobs/worker.lock`

### 7.1 目的

保证 **全局仅一个** AIVOICE Cover Worker 实例，避免双消费抢 GPU。

### 7.2 内容（JSON 文本）

```json
{
  "pid": 12345,
  "created_at": "2026-07-27T14:00:00+08:00",
  "host": "mancity"
}
```

### 7.3 规则

| 事件 | 行为 |
|---|---|
| 启动 | 尝试独占创建 lock（或 Windows 文件独占打开）；失败则退出并打日志 |
| 持有 | 运行期间保持句柄；可选周期性刷新 `updated_at` |
| 正常退出 | 删除 lock |
| 异常恢复 | 若 lock 存在但 `pid` 已不存在 → 视为陈旧，删除后重建；若 pid 仍存活 → 拒绝启动 |

GUI 重任务（可选同一契约）：启动同步翻唱前探测 `worker.lock`；若 Worker 忙，提示「飞书队列占用 GPU」——**非 MVP 强制**，文档约定即可。

---

## 8. GUI 兼容策略

| 路径 | 入口 | v1.3 |
|---|---|---|
| GUI | `CoverService.run(...)` | **保持不变** |
| 飞书 | enqueue → Worker → `CoverService.run(...)` | 新增旁路 |

保证 GUI 不受影响：

1. **不修改** `CoverService` 执行逻辑与 GUI 调用点。  
2. Worker **另进程**调用 `run()`，不替换 GUI 的 Service 单例。  
3. 产品层：尽量避免 GUI 与 Worker **同时**跑重任务（8GB VRAM）；技术强制可共享 `worker.lock` / `gpu.lock`（实现可选）。  
4. 输出目录规则不变：`outputs/{job_id}/`，GUI 自建 job_id 与 Worker 不冲突（uuid 空间）。

---

## 9. 第一版实现范围（MVP）

### 必须

- [ ] 独立 Worker 进程 + `worker.lock`  
- [ ] FS Queue 目录协议  
- [ ] Persistent Job JSON  
- [ ] Skill/CLI **enqueue**（立即返回 queued）  
- [ ] Worker：`run()` + progress 写回 + rename 终态  
- [ ] **outbox** 写入  
- [ ] 最小 notify 泵（或文档化手工泵）  
- [ ] 启动时 `running/` 陈旧任务 → failed  

### 暂缓

- cancel / 协作取消 RUNNING  
- 自动 retry / 同一 job 复活  
- HTTP Job API  
- SQLite  
- 多用户 / 优先级队列  
- 飞书实时 stage 推送  
- Worker 直连飞书 API（默认 outbox）  

---

## 10. 输出总结 — AIVOICE v1.3 MVP Architecture Contract

```text
[飞书] → Hermes Skill
            │  search/pick（同步，短）
            │  enqueue → jobs/queued/{id}.json
            └─ 立即 {status:queued, job_id}

[常驻 Worker] ← worker.lock
            │  rename claim → running/
            │  CoverService.run(on_progress→更新 JSON)
            │  rename → completed|failed/
            └─ 写 outbox/{id}.notify.json

[Notify 泵] → 飞书发 message + 可选 file_path

[GUI] → CoverService.run（原路径，不动）
```

### 稳定接口（未来勿随意改语义）

1. **Job JSON 必填字段与 `status` 枚举**（§1）  
2. **目录 bucket 名称与 rename-claim 协议**（§2）  
3. **Skill enqueue 输入/输出最小集**（§3）  
4. **Worker 调用 `CoverService.run` + `outputs/{job_id}`**（§4）  
5. **`current_stage` 取值表与用户文案映射**（§5）  
6. **Outbox notify JSON 与 `type` 枚举**（§6）  
7. **`worker.lock` 单实例语义**（§7）  
8. **GUI `run()` 路径继续可用**（§8）  

以上契约变更需显式版本升级（例如 job schema `schema_version: 1`），避免静默破坏 Hermes Skill 与 Worker。

---

*Phase 2-3 结束。下一步（未开始）：按本契约做 MVP 实现切片。*
