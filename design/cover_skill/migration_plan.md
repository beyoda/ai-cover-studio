# Cover 架构迁移计划（GUI → CoverService）

> 对应阶段：P1 骨架已完成之后  
> 前提：现有 GUI 仍使用 `build_pipeline`；本文件描述**下一阶段**如何切换，**不是本阶段任务**。

---

## 现状（P1 结束后）

| 入口 | 调用链 |
|------|--------|
| GUI `PipelineWorker` | `build_pipeline(cb)` → `Pipeline.run(JobContext)` |
| CLI | 同上 |
| Flask `/api/cover` | 同上 |
| CoverService（新） | `CoverService.run(CoverRequest)` → `PipelineAdapter` → 同上 Pipeline |

两条路径共享同一 Pipeline 实现；GUI **尚未**使用 CoverService。

---

## 目标态（后续阶段）

```
GUI PipelineWorker
  → CoverService.run(CoverRequest, on_progress=...)
    → PipelineAdapter
      → build_pipeline / Pipeline.run
```

Hermes / HTTP Cover API 与 GUI 共用 CoverService，便于后续挂 UVR worker、任务队列、统一进度模型。

---

## 建议迁移步骤

### Step 1 — 并行验证（不删旧路径）

1. 用 mock / 真实各跑一次：`CoverService.run(CoverRequest(...))`
2. 对比产物与 GUI 直连结果是否一致（同一输入、模型、pitch、reverb）
3. 确认 `ProgressEvent.stage` 与 UI 阶段文案映射正确

### Step 2 — 仅改 `PipelineWorker`（最小 UI  diff）

在 `ui/main_window.py` 的 `PipelineWorker.run` 中：

1. 构造 `CoverRequest`（字段来自现有 worker 参数）
2. 调用 `CoverService().run(request, on_progress=...)`
3. 将 `ProgressEvent` 转回现有 `progress` signal 形状  
   （`stage.value`, `percent`, `message`, `elapsed_s`）
4. 用 `CoverResult.mp3_path` / `wav_path` / `error` 驱动 `done` / `error` signal

**不要**一次改 LibraryPage、HistoryStore、主题等无关模块。

### Step 3 — 删除 worker 内重复的 `build_pipeline` / `JobContext` 拼装

- Worker 不再直接 `import build_pipeline`
- 配置默认值（workdir/output_dir/f0）交给 Adapter（已从 `ConfigLoader` 读取）

### Step 4 — 回归

- [ ] GUI 拖拽翻唱
- [ ] 音高 / 混响 / 自定义伴奏
- [ ] 作品库写入 metadata
- [ ] CLI / 现有 Flask 网页版（本步可仍直连；或另开 PR 同样改走 CoverService）

### Step 5 —（可选）统一其它入口

| 入口 | 动作 |
|------|------|
| `cli.py` | 改为 `CoverService.run` |
| `server/api.py` / `feishu.py` | 改为 `CoverService.run` |
| Hermes | 接 HTTP 或直接调 `CoverService` |

---

## 明确不做（迁移时仍须遵守）

- 不在迁移 PR 中改 `core/pipeline.py` 业务逻辑
- 不在迁移 PR 中改 UVR/SVC/ffmpeg 参数
- 不把 UVR 常驻 / GPU 安装塞进「GUI 切换」同一 PR
- Cover 层 `JobContext`（`cover.domain.job`）与 Pipeline `core.context.JobContext` 保持区分，避免混用

---

## 回滚策略

若 GUI 切换后出现回归：

1. `PipelineWorker.run` 恢复为 `build_pipeline` + `JobContext`（git revert 单文件即可）
2. CoverService 骨架保留，不影响桌面路径

---

## 验收标准（GUI 切换完成时）

- GUI 行为与切换前一致
- 仓库中 GUI 路径不再直接依赖 `factory.build_pipeline`（仅 Cover Adapter 依赖）
- Hermes 仍可按设计后续接入，无需再改 Pipeline
