# GUI → CoverService 迁移 Checklist

> P1.5 准备文档。**本阶段不执行迁移。**  
> 每一步均可独立回滚（建议每步单独 commit）。

---

## 迁移步骤

### Step 0 — 基线（已完成于 P1 / P1.5）

- [x] `CoverService` / `PipelineAdapter` 骨架存在
- [x] Contract tests 通过（`tests/test_cover_service.py`, `tests/test_pipeline_adapter.py`）
- [x] 现有 `tests/test_pipeline_mock.py`、`tests/test_config.py` 通过
- [x] GUI 仍直连 `build_pipeline`

**回滚：** 无需（无 GUI 变更）

---

### Step 1 — 引入适配辅助（可选，仍不改行为）

在 **新文件**（例如 `ui/cover_bridge.py`）中实现纯函数：

- `worker_params_to_cover_request(...)` → `CoverRequest`
- `progress_event_to_signal_args(event)` → `(stage, pct, msg, elapsed)`

**不**修改 `PipelineWorker.run`。

**验证：** 单测 bridge 函数；GUI 手工点一次翻唱确认无回归。

**回滚：** 删除新文件即可。

---

### Step 2 — PipelineWorker 双路径开关（推荐）

在 `PipelineWorker.run` 增加环境变量或常量开关，例如：

```text
AIVOICE_USE_COVER_SERVICE=0|1
```

- `0`（默认）：现有 `build_pipeline` 路径  
- `1`：`CoverService.run` 路径  

**验证：**

- 默认 `0`：与迁移前行为一致（对照同一首歌）
- `1`：产物路径、进度阶段序列与 `0` 一致

**回滚：** 开关拨回 `0`，或 revert 该 commit；GUI 立即恢复旧路径。

---

### Step 3 — 默认改为 CoverService

- 默认走 CoverService
- 保留紧急 fallback 开关一周

**验证：** 见下方「验证方案」全表。

**回滚：** 开关回旧路径；或 `git revert` Step 3。

---

### Step 4 — 删除旧直连代码与开关

- 移除 `PipelineWorker` 内 `build_pipeline` / `JobContext` 拼装
- 移除 feature flag

**验证：** 全量回归 + contract tests。

**回滚：** `git revert` Step 4（仍可从历史恢复直连）。若需热回滚，应在 Step 3 保留 flag 更久。

---

### Step 5 —（可选）统一 CLI / Flask

单独 PR，不与 GUI 绑定。

**回滚：** 各入口独立 revert。

---

## 风险点

| 风险 | 影响 | 缓解 |
|------|------|------|
| 进度 `elapsed` 语义差异 | UI 阶段耗时显示不准 | Adapter 已提供 `elapsed_s`；Worker 可继续用「阶段内计时」以保持 UI 一致 |
| `f0_method` / `export_mp3` 默认值来源不一致 | 输出或音高行为变化 | 对照表写死与当前 GUI 相同的 config 读取逻辑 |
| `_friendly_error` 仅 GUI 有 | CoverResult.error 为原文 | 迁移后仍在 Worker 内对 `CoverResult.error` 套 `_friendly_error` |
| 异常：Pipeline 内部已吞并转 `JobResult` | 与现网一致 | Contract test 覆盖 failure → CoverResult；Worker 继续区分 `success` vs raise |
| 双 JobContext 命名混淆 | 开发误用 | 代码中 Pipeline 侧保持 `JobContext as PipelineJobContext` |
| Profiling 钩子 | 两路径都应触发 | 均经 `Pipeline.run`，无需额外处理 |
| 线程亲和 | CoverService 在 QThread 调用 | 与现 `build_pipeline` 相同，勿在主线程跑 |

---

## 回滚方案（总览）

| 已完成步骤 | 回滚动作 | 预期恢复时间 |
|------------|----------|--------------|
| Step 1 | 删 bridge 文件 | 即时 |
| Step 2 | flag=0 或 revert | 即时 |
| Step 3 | flag=0 或 revert | 即时 |
| Step 4 | revert Step 4（必要时 cherry-pick 回 flag） | 一次发布窗口内 |
| Step 5 | 分入口 revert | 即时 |

原则：**任何一步失败不得要求改 Pipeline / 模型 / ffmpeg 才能回滚。**

---

## 验证方案

### 自动化

```powershell
cd <repo-root>
$env:PYTHONPATH = "<repo-root>\src"
.\.venv\Scripts\python.exe -m pytest -q
```

必须：全部绿（含 cover contract + 原有 mock）。

### 手工（每步 GUI 相关变更后）

| # | 场景 | 期望 |
|---|------|------|
| 1 | 拖入测试曲，默认模型，pitch=0，混响关闭 | 成功出 mp3；作品库可见 |
| 2 | pitch=+2，混响「录音棚」 | 成功；参数进 metadata |
| 3 | 可选伴奏文件 | 成功（行为与现网一致） |
| 4 | 故意坏路径 / 缺模型（如可造） | UI 显示友好错误，不崩溃 |
| 5 | 进度条阶段顺序 | uvr → svc → mixing/export → done |

### 对照法（Step 2 flag 阶段）

同一首歌：

1. `AIVOICE_USE_COVER_SERVICE=0` 跑一遍，记录耗时与输出哈希  
2. `=1` 再跑一遍  
3. 音频观感一致；失败时错误可达  

---

## 明确不在本 Checklist 范围

- Hermes 接入  
- UVR GPU / 常驻 worker  
- Pipeline 业务修复（双 pitch 等）  
- 本阶段（P1.5）修改 GUI 源码  
