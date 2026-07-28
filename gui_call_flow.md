# GUI 调用流程梳理（P1.5）

> 状态：只读分析，**本阶段未修改 GUI**  
> 代码依据：`src/aivoice_studio/ui/main_window.py`

---

## 1. 当前调用链（P2 起）

```
用户点击「生成翻唱」
  → MainWindow._start()
    → PipelineWorker(...)
    → CoverService.run(CoverRequest, on_progress=...)
      → PipelineAdapter
        → build_pipeline + Pipeline.run
    → progress / done / error signals（形状未变）
```

历史「直连 build_pipeline」路径已从 GUI 移除。CLI / Flask 仍可能直连，见 `gui_migration_report.md`。

---

## 1b. 迁移前调用链（归档）

```
GUI PipelineWorker
  → build_pipeline(cb)
  → Pipeline.run(JobContext)
```

---

## 2. 未来目标调用链（尚未实施）

```
用户点击「生成翻唱」
  → MainWindow._start()                    # 可保持
    → PipelineWorker(...)                  # 可保持线程边界
      → CoverService.run(CoverRequest, on_progress=...)
        → PipelineAdapter.run(...)
          → build_pipeline(cb)
          → Pipeline.run(Pipeline JobContext)
      → CoverResult → done / error signals
```

---

## 3. 未来需要切换的具体位置

### 必须改（唯一核心）

**文件：** `src/aivoice_studio/ui/main_window.py`  
**类方法：** `PipelineWorker.run`（约 L46–L96）

将以下块：

```text
build_pipeline(cb)
pipeline.run(JobContext(...))
```

替换为：

```text
CoverRequest(...)  # 由 worker 字段填充
CoverService().run(request, on_progress=...)
```

进度映射：

| 现有 | 未来 |
|------|------|
| `cb(JobState, pct, msg)` → `progress.emit(stage, pct, msg, elapsed)` | `on_progress(ProgressEvent)` → 同样 `progress.emit(event.stage.value, event.percent, event.message, event.elapsed_s or stage_elapsed)` |

结果映射：

| 现有 | 未来 |
|------|------|
| `JobResult.success` → `done` / `error` | `CoverResult.success` → `done(wav, mp3)` / `error(friendly)` |

### 建议保留不动（迁移时）

| 位置 | 原因 |
|------|------|
| `MainWindow._start` | 只负责起线程与连 signal |
| `_on_progress` / `_on_done` / `_on_error` | UI 更新逻辑与 Cover 无关 |
| `HistoryStore` / `LibraryScanner` | 产物侧逻辑 |
| `DownloadWorker` | 下载链路，不经 Pipeline |

### 可选后续统一（非 GUI 切换阻塞项）

| 入口 | 现状 |
|------|------|
| `cli.py` | 直连 `build_pipeline` |
| `server/api.py` / `feishu.py` | 直连 `build_pipeline` |

---

## 4. 参数对照表（GUI → CoverRequest）

| PipelineWorker 字段 / config | CoverRequest 字段 |
|------------------------------|-------------------|
| `self.input_audio` | `input_audio=str(...)` |
| `self.model_name` | `model_name` |
| `self.pitch` | `pitch` |
| `self.reverb` | `reverb` |
| `self.accompaniment` | `accompaniment` |
| `config["svc"]["f0_method"]` | `f0_method`（或交给 Adapter 默认） |
| `config["pipeline"]["export_mp3"]` | `export_mp3` |
| runtime workdir/output | `workdir` / `output_dir` 或省略由 Adapter 读配置 |
| — | `client="gui"` |

---

## 5. 本阶段约束

- **禁止** 修改 `main_window.py` 或其它 GUI 文件  
- 本文档仅供下一阶段「GUI → CoverService」切换使用  
- 详见 `gui_migration_checklist.md`
