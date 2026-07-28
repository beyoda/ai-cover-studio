# AIVOICE v1.3-0.2 — Worker Runtime Design

> 日期：2026-07-27  
> 阶段：Worker 常驻运行时设计（**不实现**）  
> 前置：  
> - `worker_queue_foundation_report.md`（FileJobQueue 已落地）  
> - `aivoice_v1.3_worker_interface_contract.md`  
> - `aivoice_v1.3_worker_job_lifecycle_design.md`  

**已有：** FS Queue + `enqueue/claim/update/complete/fail`  
**本阶段设计、尚未实现：** 常驻进程、CoverService 接入、`worker.lock` 真互斥、崩溃恢复  

---

## 1. Worker 生命周期

### 1.1 启动流程

```text
1. 解析配置
   - AIVOICE_ROOT / JOBS_ROOT（默认 project_root/jobs）
   - 轮询间隔 idle_sleep_s（建议 1.0–2.0）
   - heartbeat 间隔、running 超时阈值

2. 获取 worker.lock（§4）
   - 失败 → 打日志退出（另一实例已在跑）

3. 初始化
   - FileJobQueue.ensure_layout()
   - 恢复扫描（§6）：处理陈旧 running/
   - （可选）验证 .venv / CoverService 可 import，失败则退出

4. 进入主循环（§1.2）
```

### 1.2 主循环

```text
loop:
  job = claim_next_job()
  if job is None:
      → 空闲状态（§1.3）
      continue

  try:
      执行翻唱（§3 推荐 CoverService.run + on_progress）
      进度 → update_job(stage/progress/heartbeat)
      成功 → complete_job(output_path)
           → 写 outbox（实现切片再做；本设计预留）
      失败 → fail_job(error=用户可读)
           → 写失败 outbox（预留）
  except BaseException:
      fail_job(...)  # 尽量保证
      记录日志后继续 loop（不因单任务杀死 Worker）
```

单线程：**一次只执行一单**，与 GPU 串行一致（§5）。

### 1.3 空闲状态

- `claim_next_job()` 返回 `None`  
- `sleep(idle_sleep_s)`  
- （可选）刷新 lock 心跳字段 / 打 debug「idle」日志（节流，避免刷屏）  
- （可选）检查停止标志（见 §1.4）

空闲时 **不**持有 CoverService 长连接；每单可 `CoverService()` 新实例，或进程内复用一个实例（实现任选；设计上允许每单新建以隔离状态）。

### 1.4 停止流程

| 触发 | 行为 |
|---|---|
| Ctrl+C / SIGINT（若可得） | 设 `stopping=True`；若正在跑 → **不**强杀 Pipeline（MVP：等当前单结束或超时后 fail）；退出前释放 lock |
| 正常 `stop` 文件 / 标志 | 同协作停止 |
| 杀进程 / 断电 | lock 残留 → 下次启动按 §4/§6 回收 |

MVP 不做「运行中优雅 cancel UVR/SVC」；停止语义以 **不再 claim 新任务** 为主。

---

## 2. Worker 与 FileJobQueue 接口

Worker **只通过**已有 `FileJobQueue` API 碰磁盘（不直接 `os.rename` 旁路，除非实现 bugfix）。

| Worker 意图 | FileJobQueue | 说明 |
|---|---|---|
| 发现任务 | `claim_next_job()` | 内部已扫描 `queued/` + rename→`running/` |
| 扫描 queued | （无需 Worker 自扫） | claim 封装扫描；禁止双路径 claim |
| 更新 running | `update_job(job_id, current_stage=..., progress=..., metadata={last_heartbeat_at})` | stage 变化必写；heartbeat 周期性 |
| 成功 | `complete_job(job_id, output_path=...)` | → `completed/` |
| 失败 | `fail_job(job_id, error=...)` | → `failed/` |
| 入队 | **不由 Worker 调用** | enqueue 属 Skill/CLI |

契约提醒：`status` 字段与目录 bucket 保持一致；claim 成功后 JSON 已是 `running`。

---

## 3. CoverService 调用方式比较

### 方案 A — `CoverService.run(request, on_progress=...)`

| 维度 | 分析 |
|---|---|
| 复杂度 | **低**：同步调用，与 GUI 同路径 |
| 稳定性 | **高**：无额外线程池生命周期；单线程 Worker 自然串行 |
| 进度获取 | `on_progress(ProgressEvent)` → `update_job` |
| 崩溃恢复 | 进程死在 `run()` 中 → job 留在 `running/` → 启动时超时判 failed（§6） |

### 方案 B — `submit()` + `status` 轮询

| 维度 | 分析 |
|---|---|
| 复杂度 | **中高**：线程池 + poll + `shutdown(wait=)` |
| 稳定性 | 同进程双层异步，收益小；shutdown 易踩坑 |
| 进度获取 | `status().stage/progress` 拉模型，与现 Hermes Skill 类似 |
| 崩溃恢复 | 与 A 相同（都依赖 FS）；无额外优势 |

### 推荐

**推荐方案 A：`CoverService.run()` + `on_progress`。**

理由：Worker 已是常驻单消费者；再套 `submit` 等于「线程池套进程」，无必要。进度用回调写 FS 即可。Pipeline / Adapter / UVR / SVC **零改动**。

构造 `CoverRequest`：从 job JSON 的 `input_audio` / `voice_id` / `pitch` / `options` 映射；`job_id` 传入以保持 `outputs/{job_id}/`（与契约一致；实现时走 Adapter 已有 `job_id` 参数路径）。

---

## 4. worker.lock 设计

### 4.1 目的

全局 **仅一个** Cover Worker，防止双实例双 claim / 双 GPU。

### 4.2 现状

`jobs/worker.lock` 现为 **占位空文件**（layout 用）。运行时需升级为真互斥。

### 4.3 Windows 方案比较

| 方案 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| **A. 独占打开** | `open(lock, 'x')` 或 `msvcrt.locking` / Win32 共享模式不共享 | 进程活着则锁在；进程死句柄释放 | 需注意句柄保持到退出 |
| **B. pid 文件 + 探活** | 写 `{pid, created_at}`；启动时查 pid 是否存活 | 实现简单 | pid 复用竞态；需配合删除陈旧 |
| **C. 仅 rename 哨兵** | 不够作进程级锁 | — | 不推荐单独使用 |

**推荐：A + B 组合（契约已有 pid JSON 形态）**

1. 启动：尝试以独占方式创建/打开 `worker.lock` 并保持 FD。  
2. 写入 JSON：`{"pid": N, "created_at": "...", "host": "..."}`。  
3. 若无法独占：读现有 JSON；若 `pid` 不存在 → 删陈旧 lock 后重试；若存活 → **退出**。  
4. 正常退出：关闭 FD 并删除 lock。  
5. 强制结束：OS 释放句柄；下次启动走陈旧回收。

### 4.4 异常退出释放

| 退出类型 | lock |
|---|---|
| 正常 / 捕获的信号 | 主动删除 |
| Task Manager 杀进程 | 句柄释放；文件可能残留 → 启动时 pid 探活清理 |
| 蓝屏/断电 | 同残留；启动清理 |

---

## 5. GPU 串行策略

约束：RTX 4060 Laptop 8GB；UVR（DirectML）+ SVC（CUDA）峰值高，并行易 OOM。

| 层 | 策略 |
|---|---|
| **进程** | `worker.lock` 单实例 |
| **循环** | 主循环同步 `run()`，claim 下一单前必须结束上一单 |
| **禁止** | Worker 内 ThreadPool 并行多 job；Skill 侧再长跑 CoverService |
| **GUI** | 产品约定：Worker 运行时避免 GUI 重翻唱；可选共享同一 lock（实现可选，非本切片必须） |

`config/default.yaml` 的 `gpu_serial` 仍可视为产品意图；**运行时强制力来自单 Worker + 单线程**，不依赖 Pipeline 改动。

---

## 6. Worker 错误处理

| 情况 | Job 状态更新 | 说明 |
|---|---|---|
| `CoverService.run` 抛异常 | `fail_job(error=友好文案)` | 截断 traceback；日志留详情 |
| Pipeline 返回失败 `CoverResult` | `fail_job(error=result.error)` | |
| UVR/SVC 子进程非零退出 | 同上（经现有错误链冒泡） | 不改 UVR/SVC |
| 子进程僵死 / 极长无进度 | heartbeat 超时（实现可配，如 30–60min）→ `fail_job("任务超时或中断")` | MVP 可先不做墙钟超时，仅依赖进程存活 |
| 电脑睡眠 | 睡眠中进程暂停；醒来后若仍在 `run` 则继续；若被杀 → running 残留 → 启动恢复 |
| 强制关闭 Worker | job 留在 `running/` | 下次启动：`running` 且无存活 worker / heartbeat 过期 → `fail_job` + 移至 failed（通过 fail_job API） |
| claim 后发现 `input_audio` 丢失 | 立即 `fail_job`，不调 Cover | |
| 成功但无 output 文件 | `fail_job("完成但缺少输出文件")` | |

### 启动恢复（与生命周期衔接）

```text
acquire lock
for each jobs/running/*.json:
  if stale (no heartbeat beyond TTL OR previous worker pid dead):
     fail_job(job_id, error="Worker 异常中断，请重新提交")
queued/ 保持不动，主循环自动续跑
```

不对同一 `job_id` 自动无限重试。

---

## 7. Worker 日志设计

### 7.1 目标

可按 `job_id` 追踪一单从 claim 到终态；便于对照 `jobs/**/*.json`。

### 7.2 建议落盘

- 文件：`logs/worker.log`（或 `logs/aivoice_worker.log`）  
- 格式：一行一条，建议 JSON lines 或固定字段文本  

### 7.3 必记字段

| 字段 | 何时 |
|---|---|
| `ts` | 每条 |
| `job_id` | claim 之后 |
| `event` | `start` / `claim` / `stage` / `complete` / `fail` / `idle` / `lock` / `shutdown` |
| `stage` | stage 变更 |
| `error` | 失败（短消息）；详情可 `exc_type` |
| `duration_s` | complete/fail |

示例（逻辑）：

```text
2026-07-27T15:00:01+08:00 event=claim job_id=a55442027dba
2026-07-27T15:00:02+08:00 event=stage job_id=a55442027dba stage=uvr
2026-07-27T15:00:25+08:00 event=stage job_id=a55442027dba stage=svc
2026-07-27T15:01:20+08:00 event=complete job_id=a55442027dba duration_s=79
```

不在日志打飞书密钥；不打完整音频二进制路径以外的隐私可按需脱敏（MVP 可保留本机路径）。

---

## 8. Worker 启动方式（Windows）

| 方式 | 优点 | 缺点 | 适合 |
|---|---|---|---|
| **手动** `python -m …` | 开发最快 | 易忘 | 开发调试 |
| **.bat** | 双击；可 `unset` 等价清环境 | 无自动拉起 | **当前阶段推荐** |
| **PowerShell 脚本** | 与现 `scripts/*.ps1` 一致；易设 `PYTHONPATH` | 执行策略限制 | 与 bat 二选一 |
| **Task Scheduler** | 登录启动、崩溃重启 | 配置重；调试难 | 稳定后生产 |

### 当前阶段推荐

**`scripts/run_worker.bat`（或 `.ps1`）手动/快捷方式启动**，与 Hermes Gateway 分开窗口：

1. 清 `PYTHONPATH`（避免 Hermes 污染，与翻唱 Skill 同纪律）  
2. 用 AIVOICE `.venv\Scripts\python.exe`  
3. 工作目录 `<repo-root>`  
4. 控制台可见日志，便于 v1.3 联调  

登录自启（Task Scheduler）放到「飞书异步闭环已通」之后。

---

## 9. 设计结论摘要

| 议题 | 决定 |
|---|---|
| 主循环 | claim → `CoverService.run` → complete/fail → 继续 |
| Cover 调用 | **方案 A：`run()` + on_progress** |
| 队列 | 只用 `FileJobQueue` API |
| 单实例 | **worker.lock 独占 + pid 探活** |
| GPU | 单 Worker × 单线程串行 |
| 恢复 | 陈旧 `running/` → fail |
| 启动 | 现阶段 **bat/ps1 手动** |

### 实现边界（下一批切片）

- 新增 Worker 入口模块 / 启动脚本  
- **不改** CoverService 执行逻辑、Pipeline、UVR、SVC、GUI、Hermes Skill（Skill enqueue 另切片）  

---

*v1.3-0.2 设计结束。下一步（未开始）：按本文实现 Worker Runtime。*
