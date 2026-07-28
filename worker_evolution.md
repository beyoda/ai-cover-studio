# Worker Evolution Roadmap

> Phase: P4.0 — 仅设计  
> 问题：当前为何不引入常驻 Worker？未来何时引入？

---

## 1. Worker 指什么

本文 **Worker** = 长驻进程/线程，持有昂贵资源并接收 CoverService 派发的任务，例如：

| Worker 类型 | 持有资源 | 主要收益 |
|-------------|----------|----------|
| **UVR Worker** | `audio_separator.Separator` + 已 `load_model` | 去掉每次 CLI 冷启动与模型加载 |
| **SVC Worker** | 常驻 so-vits-svc 推理服务 | 去掉每次 Python/模型加载 |
| **Job Worker** | 仅执行槽线程（无模型常驻） | 支撑 `submit` 异步，不一定省推理时间 |

三者可独立演进；**不要**与「文件 Cache」混淆（Cache 见 `cache_strategy.md`）。

---

## 2. 当前为什么不引入 Worker

### 2.1 架构节奏

已完成：Pipeline 稳定 → Cover 骨架 → GUI 迁 CoverService → Skill 契约。  
**下一步缺口是 Job/异步 API**，不是常驻推理。

先补 `submit/status/result`（进程内队列即可），Agent 即可友好；Worker 是性能项，非契约阻塞项。

### 2.2 复杂度与风险

| 风险 | 说明 |
|------|------|
| 显存常驻 | UVR GPU 化后 + SVC CUDA 同时常驻易 OOM（4060 8GB） |
| 生命周期 | GUI 退出是否杀 Worker？Hermes 独用谁拉起？ |
| Windows 进程 | 子进程崩溃恢复、句柄泄漏、命名管道/HTTP 端口管理 |
| 正确性 | 多请求串行/并行、取消、与 profiling 钩子交互 |
| 运维 | 多一个需健康检查的守护进程 |

### 2.3 收益尚未「强制」

Profiling（迁移后）：

- 瓶颈在 **UVR CPU 推理时间本身**（~100s+），不全是「模型加载 1–2s」。  
- 仅 Worker 不换 GPU，墙钟改善有限。  
- SVC ~30s 含推理；常驻有收益，但需独立服务化 so-vits-svc，改造面大于 CoverService。

### 2.4 产品路径仍双入口

GUI 与未来 Hermes 共用 CoverService；在 Job API 稳定前引入 Worker，易造成「半接 GUI、半接 Agent」的临时分叉。

### 2.5 结论（现在）

```text
P4.0 决策：不引入 UVR/SVC 常驻 Worker。
允许设计 Job 执行槽（线程池 size=1）——这是轻量「Job Worker」，不是模型常驻。
```

---

## 3. 未来引入条件

同时满足或明显满足多项时，再立项 Worker：

### 3.1 UVR Worker 触发条件

1. **UVR 已切 GPU**（ORT CUDA），且 profiling 显示冷启动/重复 load 占比升高；或  
2. 用户/Agent **高频短间隔** 多首歌翻唱，L1 Cache 未命中仍反复 load；或  
3. 产品要求「首曲慢、其后快」的会话内体验，且接受常驻显存预算。

前置：`.venv` GPU 栈可用；CoverService `health` 能报告 `uvr_worker.loaded`。

### 3.2 SVC Worker 触发条件

1. Profiling 证明 **模型加载 + 进程启动** 占 SVC 阶段显著比例；且  
2. 同一 `model_name` 连续复用率高；且  
3. 有可维护的 so-vits-svc **服务化协议**（HTTP/gRPC），而不只是反复 `inference_main.py`。

前置：与 UVR Worker **显存分时**（同一时刻只加载一侧）或升配 GPU。

### 3.3 仅 Job 执行槽（轻量）

在实现 `submit()` 时 **即可引入**，条件宽松：

- 需要异步 + 队列  
- 不持有模型，只 `adapter.run`  
- 与「常驻推理 Worker」分开命名，避免范围膨胀

---

## 4. 推荐演进顺序

```text
Now (P4.0 设计)
  │
  ├─① CoverService API v2：submit / status / result / cancel（进程内队列）
  │
  ├─② Cache L1（UVR stems）——可与①并行设计，实现另批
  │
  ├─③ UVR 推理 GPU（环境，非 Worker）
  │
  ├─④ UVR Persistent Worker（Separator 常驻）
  │
  └─⑤ SVC Persistent Worker（可选，更重）
```

 guile：

- **① 不依赖 Worker**  
- **④ 依赖 ③ 才更值得**  
- **② 与 ④ 互补**：Cache 跨进程复用；Worker 会话内复用  

---

## 5. 引入时的架构位置

```text
Hermes / GUI
    → CoverService（Job 调度 + Cache 闸门）
        → [可选] UvrWorkerClient
        → [可选] SvcWorkerClient
        → PipelineAdapter（无 Worker 时仍走现网子进程）
            → Pipeline
```

Adapter 可增加「执行后端」端口，**Pipeline 业务步骤保持不变**；或 Worker 只替换 UVR/SVC 模块的进程调用方式（另阶段 RFC）。

---

## 6. 明确不做（当前）

- 不实现 UVR/SVC 常驻进程  
- 不修改 Pipeline / GUI / Hermes / 模型  
- 不把 Cache 与 Worker 绑死在同一发布  

---

## 7. 一句话

**现在不要 Worker：** 契约与异步 Job 更优先，且主瓶颈是 UVR CPU 算力而非缺少守护进程。  
**以后再 Worker：** 当 GPU 就绪、重复调用频繁、且 profiling 证明冷启动可观时，在 CoverService 侧挂载常驻 UVR（再考虑 SVC）。
