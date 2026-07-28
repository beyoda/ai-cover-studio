# AIVOICE v1.3 Async Worker — Phase 2-2 Job Lifecycle Design

> 日期：2026-07-27  
> 阶段：生命周期设计（不实现、不改代码）  
> 前置：  
> - `aivoice_v1.3_async_worker_phase1_analysis.md`  
> - `v1.3_worker_architecture_options.md`（推荐 **Option A：独立 Worker + 持久化 JobStore**）

---

## 1. Job 数据模型设计

### 1.1 逻辑实体：`CoverJob`

一次「可异步执行的翻唱任务」在持久化层至少包含：

| 字段 | 类型（逻辑） | 含义 |
|---|---|---|
| `job_id` | string (12 hex) | 与现有 CoverService / `outputs/{job_id}` 对齐的主键 |
| `created_at` | datetime ISO | 入队时间 |
| `updated_at` | datetime ISO | 任意状态/进度变更 |
| `started_at` | datetime? | 进入 RUNNING |
| `finished_at` | datetime? | 进入终态 |
| `source` | string? | 用户侧歌名/查询（如「示例歌手的示例曲目」） |
| `input_audio` | path string | Worker 执行前必须已落盘的本地音频绝对路径 |
| `track_id` | string? | GD 选曲 id（可空） |
| `provider` | string? | `gdstudio` / `local` / `url` |
| `voice_id` | string | Registry id（`example_voice_b` / `example_voice`） |
| `pitch` | int | 半音 |
| `options` | object | `reverb`、`export_mp3`、`f0_method` 等 |
| `requester` | string? | 用户标识（飞书 open_id / 显示名） |
| `feishu_chat_id` | string? | 完成后投递目标会话 |
| `hermes_session_id` | string? | 与选歌 session 关联（可选） |
| `status` | enum | 见 §2 |
| `current_stage` | enum/string | `pending/uvr/svc/mixing/exporting/done/failed` |
| `progress` | object? | `{percent, message, stage, updated_at}` |
| `output_path` | path? | 成功时的 `cover.mp3`（或 wav） |
| `error` | string? | 用户可读错误（非 traceback） |
| `notify_status` | enum? | `pending/sent/failed/skipped` |
| `metadata` | object | 扩展袋（见下） |

与现有 `CoverRequest` 的关系：

- 持久化 Job **包含**足够信息以重建 `CoverRequest`（至少 `input_audio`、`voice_id`、`pitch`、`options`）。
- `source` / `track_id` / 飞书字段是 **异步与通知** 所需，不必进入 Pipeline。

### 1.2 必须持久化

跨进程、跨崩溃仍要能恢复或可解释的字段：

- `job_id`, `created_at`, `updated_at`, `started_at`, `finished_at`
- `input_audio`, `voice_id`, `pitch`, `options`
- `status`, `current_stage`, `progress`（至少最近一次）
- `output_path`, `error`
- `feishu_chat_id`（若要自动回传）
- `requester`（审计 / 多会话区分）
- `notify_status`
- `source`, `track_id`, `provider`（产品回执文案）

### 1.3 仅运行时（可不落盘或可丢失）

- CoverService 进程内 `Future` / 线程句柄  
- Pipeline 瞬时回调对象、子进程 Popen 句柄  
- GPU 利用率采样、profiling 临时缓冲  
- Hermes Agent 当轮 tool 上下文  

进度事件可 **抽样持久化**（例如 stage 变化时写一次），不必每个 percent 都写盘。

### 1.4 未来可扩展（放 `metadata`）

- `priority`, `client`（`hermes`/`gui`/`cli`）  
- `eta_seconds`, `uvr_cache_hit`  
- `retry_count`, `last_heartbeat_at`（崩溃检测）  
- `artwork_url`, `song_display_name`  
- 多平台：`telegram_chat_id` 等  

---

## 2. Job 状态机设计

对齐现有 `JobStatus` 枚举，语义在 Worker 层强制：

```text
QUEUED ──► RUNNING ──► COMPLETED
   │            │
   │            └──► FAILED
   │
   └──► CANCELLED

（可选，实现阶段再定是否开放）
RUNNING ──► CANCELLED   # 需能杀 UVR/SVC 子进程；v1.3 可先不做
```

### 2.1 合法转换

| From | To | 触发 |
|---|---|---|
| — | `QUEUED` | Skill/投递端 enqueue |
| `QUEUED` | `RUNNING` | Worker **claim** 成功 |
| `QUEUED` | `CANCELLED` | 用户取消且尚未 claim |
| `RUNNING` | `COMPLETED` | Cover 成功且 `output_path` 有效 |
| `RUNNING` | `FAILED` | 执行异常 / Pipeline 失败 / 心跳超时判死 |
| `RUNNING` | `CANCELLED` | （可选）协作取消 |

### 2.2 非法转换（禁止）

- `COMPLETED` → 任何非终态  
- `FAILED` / `CANCELLED` → `RUNNING`（重试应 **新 job_id** 或显式 `requeue` 新状态设计，v1.3 不做原地复活）  
- `COMPLETED` → `FAILED`  
- 跳过 `RUNNING`：`QUEUED` → `COMPLETED`  
- 双活：同一 `job_id` 再次 `QUEUED`→`RUNNING` 而无 claim 令牌  

### 2.3 状态图（文本）

```text
                 enqueue
                    │
                    ▼
              ┌─────────┐
       cancel │ QUEUED  │
         ┌────┤         │
         │    └────┬────┘
         ▼         │ claim
   ┌───────────┐   ▼
   │ CANCELLED │ ┌─────────┐
   └───────────┘ │ RUNNING │
                 └────┬────┘
            success   │   error
                 ▼    ▼
          ┌──────────┐  ┌────────┐
          │COMPLETED │  │ FAILED │
          └──────────┘  └────────┘
```

`current_stage` 是 RUNNING 内的子进度，**不是**平行主状态；主状态机只认上表五态。

---

## 3. Worker 消费模型

### 3.1 方案比较

| 方案 | 形态 | 优点 | 缺点 |
|---|---|---|---|
| **A. Filesystem queue** | `jobs/queued|running|completed|failed/` + 原子 rename claim | 零依赖、Windows 友好、易目视调试 | 需约定文件格式；列表要用目录扫描 |
| **B. SQLite queue** | 单库表 + 事务 UPDATE claim | 查询/恢复强、锁清晰 | 多一个 DB 文件与迁移心智 |
| **C. JSON queue** | 单/多 JSON 文件追加 | 实现快 | 并发 claim 易坏；大文件改写不安全 |

### 3.2 场景约束

Windows 11 · 单用户 · RTX 4060 · 个人工作站 → **不需要 Redis/云队列**。

### 3.3 推荐

**推荐：方案 A（Filesystem queue）为主，Job 记录用单文件 JSON。**

建议布局（逻辑，非实现）：

```text
jobs/
  queued/     {job_id}.json      # 仅元数据 + 请求
  running/    {job_id}.json      # claim 后 rename 进来
  completed/  {job_id}.json
  failed/     {job_id}.json
  cancelled/  {job_id}.json
  outbox/     {job_id}.notify.json   # 见 §6
```

Claim = **同卷原子 `rename(queued → running)`**（Windows 上同目录树 rename 足够做互斥）。  
SQLite（B）可作为 v1.4 若需要「按用户查历史 / 复杂过滤」再加；**不必阻断 v1.3**。  
纯「一个巨大 JSON 数组」（C）不推荐。

---

## 4. JobStore 设计

### 4.1 现状

`JobStore` = 进程内 `dict`，随 `aivoice_cover.py` / `CoverService()` 消亡。

### 4.2 升级方向（不改 CoverService 源码行为）

| 做法 | 说明 | 是否推荐 |
|---|---|---|
| 改 CoverService 内嵌 PersistentJobStore | 违反「不改 CoverService」；且 Skill 短进程仍无常驻 | ❌ |
| **新增 Worker 侧 PersistentJobStore / 文件系统状态机** | Worker 拥有真相源；调用 Cover 时仍可用内存 CoverService | ✅ |
| CoverService 实现替换注入 | 未来可选；非本阶段必须 | 可选演进 |

### 4.3 推荐边界

- **新增：`PersistentJobStore`（或等价「jobs/ 目录状态机」）由 Worker（及 enqueue 端）读写。**  
- **CoverService 不需要知道 Worker 存在。**  
  Worker 生命周期内：`svc = CoverService()` → `submit` →（同进程短轮询或同步 `run`）→ 把结果 **写回** Persistent 层。  
- 对外（Hermes）只认 Persistent 层的 `job_id` / status，不认某次 CoverService 实例内存。

可选两种执行胶水（实现阶段二选一，设计层都合法）：

1. Worker 调 `CoverService.run(...)`（同步，最简单，单线程 Worker 天然串行）  
2. Worker 调 `submit`+同进程 poll（复用 stage 回调），进程仍是 Worker 常驻进程  

无论哪种，**持久化真相在 Worker/FS，不在 CoverService 内存。**

---

## 5. Worker 执行生命周期

只描述流程：

```text
1. Worker 启动
   - 加载配置（AIVOICE root、jobs 根目录、单卡策略）
   - 运行 §8 恢复扫描
   - 进入主循环

2. 发现任务
   - 扫描 jobs/queued/（按 created_at / 文件名排序）
   - 若空：sleep 短间隔，继续

3. Claim job
   - rename queued/{id}.json → running/{id}.json
   - 失败（已被抢）→ 下一单
   - 成功：status=RUNNING，写 started_at、heartbeat

4. 执行翻唱
   - 校验 input_audio 存在、voice_id 合法（Registry）
   - 调用 CoverService（run 或 submit+poll）
   - 不改 Pipeline / UVR / SVC

5. 监听进度
   - 将 Adapter/Pipeline 进度映射为 current_stage + progress
   - stage 变化时更新 running/{id}.json（及可选 heartbeat）

6. 保存结果
   - 成功：status=COMPLETED，output_path，finished_at
     rename running → completed
   - 失败：status=FAILED，error（用户可读），finished_at
     rename running → failed

7. 触发通知
   - 写 outbox 或直接通知（§6）
   - notify_status 更新

8. 回到步骤 2
```

Skill 侧对应缩短为：

```text
选曲完成 → 写 queued/{job_id}.json（含 feishu_chat_id）→ 立刻回「已排队」→ 结束 tool
```

---

## 6. 飞书通知设计

### 6.1 方案比较

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| **A. Worker 直调飞书 API** | Worker 持 FEISHU_* 发消息/传文件 | 路径短 | 复制凭证与 Gateway 逻辑；与 Hermes 双通道易乱 |
| **B. Outbox + Hermes 发送** | Worker 只写 `outbox/*.notify.json`；Gateway/小助手/cron 读后发送 | 职责分离；复用 Hermes 已登录会话 | 需一个「发送端」轮询 outbox |
| **C. Gateway 回调** | Worker HTTP 调 Hermes 内部 hook | 集成深 | Hermes 未必有稳定回调；耦合版本 |

### 6.2 针对当前 Hermes 架构的选择

Hermes 已持有飞书 websocket、鉴权、`NO_PROXY`、发文件能力；Worker 是 AIVOICE 侧进程。

**推荐：方案 B（Notification Outbox）。**

- Worker **不**直接依赖飞书 SDK。  
- 完成/失败时写：

  ```text
  jobs/outbox/{job_id}.notify.json
  # chat_id, text, file_path?, kind=completed|failed
  ```

- 发送端可选（实现阶段定一）：  
  - 轻量 `notify_pump` 脚本由任务计划/与 Worker 同启，调 Hermes 能力或飞书 API；或  
  - Hermes Skill/cron：「有 outbox 则发送并标记 sent」。  

方案 A 仅当坚持「零 Hermes 依赖发文件」时备选；**默认 B 更贴现架构。**  
方案 C 不作 v1.3 默认。

---

## 7. GPU 单任务策略

约束：RTX 4060 Laptop **8GB**；UVR DirectML + SVC CUDA 峰值显存高；并行两单易 OOM/驱动复位。

| 手段 | 作用 |
|---|---|
| **Worker 单线程 / 单协程消费** | 主路径：同时只跑一单 Cover |
| **queued 串行 claim** | 自然排队 |
| **lock 文件** | 防多 Worker 实例（误开两个常驻） |
| **SQLite 锁** | 若未用 SQLite，非必须 |

**推荐组合：**

1. **只允许一个 Worker 进程**（启动时获取 `jobs/worker.lock` 独占；失败则退出）。  
2. **进程内单线程顺序执行**（不做线程池并行翻唱）。  
3. 不在 Skill 侧再 `CoverService(submit)` 长跑（避免第二执行器抢 GPU）。

GUI 同步翻唱：产品规则上 **与 Worker 互斥**（同 lock 或文档约定「飞书队列运行时勿开 GUI 重任务」）；实现可用同一 `worker.lock` 或 `gpu.lock`。

---

## 8. 异常恢复设计

| 场景 | 策略 |
|---|---|
| **执行中断电 / 杀进程** | 启动扫描 `running/`：若 `heartbeat` 过期或缺心跳 → 标 `FAILED`（或谨慎 `requeue` 一次，v1.3 建议 **FAILED + 文案「中断，请重试」**），rename → `failed/`，写 outbox |
| **Worker 崩溃后重启** | 同上；`queued/` 保留自动续跑 |
| **Hermes 重启** | 不影响 Worker；outbox 未 sent 的继续泵出 |
| **Pipeline/工具失败** | RUNNING→FAILED，持久化 `error`，outbox 失败通知 |
| **input 文件丢失** | claim 后校验失败 → FAILED，不占 GPU |
| **COMPLETED 但文件被删** | 通知发送前校验 `output_path`；缺失则改失败通知 |
| **重复通知** | `notify_status=sent` 后 outbox 移走或改后缀；泵端幂等 |

**启动恢复顺序：**

```text
acquire worker.lock
→ 修复 running/（超时 → failed）
→ 泵出遗留 outbox（可选）
→ 开始消费 queued/
```

不做：自动无限重试同一 `job_id`（避免坏任务打爆 GPU）。

---

## 9. 与现有架构边界

### 保持不变

- Pipeline  
- UVR / SVC / Mixer 实现  
- GUI（`CoverService.run`）  
- CoverService **执行逻辑**（`_execute_job` / Adapter.run）  

### 新增

| 组件 | 职责 |
|---|---|
| **Enqueue 路径**（Skill 短写） | 生成 `job_id`、写 `queued/`、立即返回 |
| **PersistentJobStore / FS 状态机** | Job 生命周期真相源 |
| **Worker 常驻进程** | claim → 调 Cover → 更新状态 → outbox |
| **Notifier / outbox pump** | 把完成/失败送到飞书 |

### 调用关系

```text
飞书用户
  → Hermes Agent / Skill（选歌仍可同步；翻唱只 enqueue）
       → PersistentJobStore (queued)
  → [立即] 回复「已排队」

常驻 Worker
  → claim → CoverService.run/submit（进程内）
       → PipelineAdapter → Pipeline → UVR/SVC/…
  → PersistentJobStore (completed/failed)
  → outbox

Notifier / Hermes
  → 读 outbox → 飞书发文案 + cover.mp3
```

CoverService **不反向依赖** Worker；Worker **是 CoverService 的调用方**。

---

## 10. Phase 2-2 结论摘要

| 议题 | 决定 |
|---|---|
| 数据模型 | 持久化请求 + 状态 + 飞书投递字段；进度抽样；扩展进 `metadata` |
| 状态机 | QUEUED→RUNNING→COMPLETED/FAILED；QUEUED→CANCELLED；禁非法跳转 |
| 队列 | **Filesystem queue + JSON per job** |
| JobStore | **Worker 侧 Persistent**；CoverService 无感知 |
| 通知 | **Outbox + Hermes/泵发送** |
| GPU | **单 Worker 锁 + 单线程串行** |
| 恢复 | running 超时失败化；queued 续跑；通知幂等 |

---

*Phase 2-2 结束。下一步（未开始）：接口契约 / 目录布局落盘规范 / 实现切片。*
