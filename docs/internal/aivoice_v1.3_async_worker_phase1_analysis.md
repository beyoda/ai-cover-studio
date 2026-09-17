# AIVOICE v1.3 Async Worker — Phase 1: Current Architecture Analysis

> 日期：2026-07-27  
> 阶段：只读分析（本文件为唯一产出）  
> 约束：未改代码；未实现 Worker；未改 Hermes Skill / CoverService

---

## 1. 当前任务执行链路

```text
飞书用户消息
  → Hermes Gateway（websocket）
  → Hermes Agent（读 aivoice-cover SKILL）
  → terminal：aivoice_cover.py
       ├─ --search / --pick / --json-file …
       ├─ MusicSource（local / URL / GDStudio）
       ├─ Voice Registry（voices.json）
       └─ CoverService.submit(job_id)
            → 同进程 ThreadPool（max_workers=1）
            → PipelineAdapter.run
            → Pipeline：UVR → SVC → VocalFX → Mixer → Export
            → aivoice_cover.py 循环 status() 直至终态
            → stdout JSON + cover.mp3 路径
  → Agent 把文案 / 文件回飞书
```

### 各层职责

| 层 | 主要位置 | 职责 |
|---|---|---|
| **飞书用户** | 手机客户端 | 自然语言意图（音色、歌名、序号） |
| **Hermes Gateway** | `%LOCALAPPDATA%\hermes` | 收消息、会话、调 Agent；**不跑翻唱计算** |
| **Hermes Agent** | Hermes runtime | 选 Skill、拼命令、把 stdout/stderr 转成回复；可被旧 MEMORY 带偏 |
| **aivoice-cover Skill** | `hermes_skill/media/aivoice-cover/` | 契约与话术：搜歌、session pick、禁止硬编码音色 |
| **aivoice_cover.py** | `…/scripts/aivoice_cover.py` | Skill 运行时：解析请求、调 MusicSource/Registry、**submit + 阻塞轮询**、用户文案 |
| **MusicSource** | `src/aivoice_studio/cover/music_source/` | 把歌名/路径/URL/`track_id` 解析成本地音频资产 |
| **Voice Registry** | `config/voices.json` + `cover/voice_registry.py` | `voice_id` → checkpoint/config；唯一音色真相源 |
| **CoverService** | `cover/service/cover_service.py` | 应用入口：`run`（同步 GUI）或 `submit/status/result`（线程池任务） |
| **PipelineAdapter** | `cover/adapter/pipeline_adapter.py` | Cover 域 ↔ 核心 Pipeline 边界；进度回调映射 |
| **Pipeline** | `core/pipeline.py` | 同步编排 UVR→SVC→FX→Mix→Export |
| **UVR** | `modules/uvr` + `scripts/uvr_directml.py` | 人声分离子进程（DirectML） |
| **SVC** | `modules/svc` + so-vits-svc workenv | 音色转换子进程（CUDA） |
| **Mixer / Export** | `modules/mixer` | ffmpeg 混音与 MP3 |
| **输出** | `outputs/{job_id}/cover.mp3` | 磁盘成品；**元数据不随进程持久化** |

要点：表面已有「异步 API」（`submit` 立即返回 `job_id`），但 **Hermes 客户端进程在同一次调用里把轮询跑完**，对用户仍是长阻塞。

---

## 2. 当前同步阻塞原因分析

### 2.1 现象

一次完整翻唱（搜歌已完成后）：

- Agent terminal 占用：**数十秒～数分钟**（示例曲目 / ExampleVoiceB 实测约 80–90s；长曲更久）
- 飞书侧表现为：机器人「还在跑」、会话占坑、短闲聊也可能排队

### 2.2 Skill 调用方式

- Hermes 通过 **terminal / bash** 启动 `aivoice_cover.py`。
- Skill 默认：`--timeout 600`、`--poll-interval 2`。
- `run_cover_request` 在 **同一 Python 进程**内：

  1. `CoverService()`（新建实例）
  2. `job_id = service.submit(...)`
  3. `while` 未超时：`service.status(job_id)` → sleep 2s
  4. `service.result(job_id)` → emit JSON
  5. `service.shutdown(wait=True)`（等到线程池任务结束）

因此：**进程生命周期 = 整单翻唱生命周期**。Agent 的 tool call 必须等这个进程退出。

### 2.3 CoverService 调用方式

- `submit` 本身非阻塞：任务进 `ThreadPoolExecutor(max_workers=1)`。
- 真正重活在线程里同步跑 `PipelineAdapter.run`（内部再 `subprocess` 调 UVR/SVC）。
- 对 Hermes 无帮助：轮询方与执行方共享同一进程；进程不退出，Agent 不能结束本轮 tool。

### 2.4 JobStore 生命周期

- `JobStore` = **进程内 `dict`**（`cover/job_store.py`），文档写明 *no Redis / DB*。
- 每个 `CoverService()` 自带新 Store；脚本退出后 **状态全丢**。
- 磁盘上 `workdir/{job_id}`、`outputs/{job_id}` 会留下文件，但 **无法用 job_id 在新进程里 `status()`** → `JobNotFound`。

### 2.5 status 轮询机制

- 进度靠 **拉模型**：`status()` 读最新 `CoverJobRecord.progress/stage`。
- 无 WebSocket / 推送 / 跨进程订阅。
- 阶段变化仅写到 stderr（UX 文案）；Agent 若提前结束进程，**拿不到终态，也推不了 mp3**。

### 2.6 阻塞因果链（浓缩）

```text
飞书要成品
  → Agent 必须拿到 completed JSON + 文件路径
    → aivoice_cover.py 必须活到 Pipeline 结束
      → JobStore 只活在该进程
        → 无法「submit 后立刻退出、另进程查 status」
```

---

## 3. 当前系统中已有的异步基础

| 能力 | 是否存在 | 位置 / 说明 | 对 Worker 可复用性 |
|---|---|---|---|
| **job_id** | ✅ | `uuid4().hex[:12]`；同时作为 workdir/output 目录名 | **高** — 已是稳定主键 |
| **JobStatus** | ✅ | `QUEUED/RUNNING/COMPLETED/FAILED/CANCELLED` | **高** — DTO 可直接用；`CANCELLED` 尚未被赋值 |
| **CoverJobRecord / JobStatusView** | ✅ | `cover/domain/job_record.py` | **高** |
| **JobStore** | ⚠️ 仅内存 | `cover/job_store.py` | **接口可复用，实现需替换/包装为持久化** |
| **Cover 域 JobContext** | ✅ 但闲置 | `cover/domain/job.py` — CoverService 路径未用 | 低（可选） |
| **Pipeline JobContext** | ✅ | `core/context.py` — 真正跑流水线时使用 | 保持不动 |
| **submit / status / result API** | ✅ | `CoverService` + `CoverServiceProtocol` | **高** — Worker 外可保持同一契约 |
| **进度回调** | ✅ 进程内 | Pipeline → Adapter `ProgressEvent` → Store 更新 | **高** — 可写入持久化 store / 消息 |
| **事件总线 / 推送** | ❌ | 无 pub/sub、无完成 webhook | 需新建（飞书侧靠 Hermes 再发消息） |
| **常驻 Worker 进程** | ❌ | 每次 Skill 新建 CoverService | 本阶段要解决的缺口 |
| **HTTP Job API** | ❌ | Flask `/api/cover` 偏同步 Pipeline，非 CoverService 任务 API | 可选平行入口，非现状 |

**结论：** 异步的「形状」已在 Cover 层具备（submit/status/result + job_id + stage）；缺的是 **持久化 JobStore + 脱离 Hermes 进程的执行宿主 + 完成后的主动通知通道**。

---

## 4. Async Worker 需要解决的问题

（只列问题，不给方案。）

1. **Hermes / Agent 不能（也不应）长时间占用 tool 等待** UVR+SVC 整单。
2. **任务状态无法跨进程保存**：当前 JobStore 随 `aivoice_cover.py` 退出消失。
3. **submit 后客户端无法在新进程可靠查询** 同一 `job_id` 的 status/result。
4. **完成后无法主动通知飞书**：无常驻监听、无「job completed → 发 cover.mp3」钩子；依赖原 tool 进程不退出。
5. **进度无法对用户持续推送**（除非阻塞轮询或另开通道）；阶段文案绑在长跑脚本的 stderr。
6. **GPU / 单卡互斥**：`max_workers=1` 只在单 CoverService 实例内有效；多 Agent 会话 / 多脚本并发会抢 UVR+SVC。
7. **取消语义缺失**：枚举有 `CANCELLED`，无取消 API / 杀子进程路径。
8. **失败与超时的产品语义**：超时发生在 Skill 轮询层，与 Worker 侧任务是否仍在跑可能不一致（若拆进程后更明显）。
9. **会话状态（搜歌 pick）与翻唱 job 状态分裂**：session JSON 在 `hermes_skill/runtime/`，job 在内存；异步后需明确两者关系。
10. **成品投递责任归属不清**：谁上传飞书文件、用哪个 chat_id、失败重试谁负责。
11. **环境隔离仍脆弱**：Worker 必须继续处理 `PYTHONPATH` / 双 venv（DirectML UVR vs CUDA SVC），否则长驻进程会放大污染。
12. **可观测性**：无跨会话的 job 列表 / 历史；磁盘 outputs 与逻辑 job 记录不同步。

---

## 5. 当前不可修改边界

以下在后续 Worker 设计中应视为 **稳定边界（不重写）**：

| 模块 | 原因 |
|---|---|
| **Pipeline** | 已验证的同步编排核心 |
| **UVR / SVC / Mixer 实现** | 外部工具与模型耦合；已调通 DirectML / CUDA |
| **GUI** | 走 `CoverService.run` 同步路径，与飞书异步可并存 |
| **CoverService 核心执行逻辑** | `_execute_job` → `PipelineAdapter.run` 是正确应用边界；可 **外包一层** 持久化/队列，不宜拆散 Adapter 契约 |
| **模型文件** | 权重与 config 配对已验证（含 ExampleVoiceB） |

### Worker 应处位置（定位，非设计细节）

```text
[飞书] → Hermes Agent / Skill（短调用：submit 或 enqueue）
                ↓
        【新增】Async Worker 宿主（常驻进程 / 队列消费者）
                ↓
        CoverService.submit 或等价「跑一单」入口
                ↓
        PipelineAdapter → Pipeline → UVR/SVC/…（不变）
                ↓
        持久化 status/result + 通知通道 → 再回飞书
```

即：Worker **夹在 Hermes Skill 与 CoverService/PipelineAdapter 之间（或旁路为常驻服务）**，  
**向下复用** 现有 Cover 执行栈，**向上缩短** Agent 等待，**向外补齐** 持久化与完成推送。  
不进入 Pipeline / UVR / SVC / GUI 内部。

---

## 6. Phase 1 结论（一句话）

当前系统已有 **job_id + submit/status/result 的异步外观**，但 **JobStore 内存化 + Skill 同进程阻塞轮询** 使飞书体验仍是同步长任务；v1.3 Worker 的本质是补齐 **跨进程任务生命周期与完成通知**，而不是重做翻唱引擎。

---

*Phase 1 结束。下一步（未开始）：Async Worker 方案设计。*
