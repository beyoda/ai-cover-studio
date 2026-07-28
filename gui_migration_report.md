# GUI → CoverService 迁移报告（P2）

> 日期：2026-07-26  
> 性质：**入口迁移**（非业务重构）  
> Hermes / Worker / Cache / GPU：**未开始**

---

## 0. 迁移前备份

已保存至 `old_gui_entry_backup/`：

| 文件 | 说明 |
|------|------|
| `main_window.py.pre_p2.py` | 迁移前完整 `main_window.py` |
| `PipelineWorker_pre_p2.py` | 直连 `build_pipeline` 的 `PipelineWorker` |
| `README.md` | 回滚说明 |

---

## 1. 修改文件

| 文件 | 变更 |
|------|------|
| `src/aivoice_studio/ui/main_window.py` | `PipelineWorker.run` → `CoverService.run`；GUI 不再 import `build_pipeline` / `JobContext` |
| `src/aivoice_studio/ui/cover_bridge.py` | **新增** — CoverRequest 组装 + 阶段内 elapsed |
| `src/aivoice_studio/cover/__init__.py` | P2 入口说明 |
| `tests/test_cover_bridge.py` | **新增** |
| `tests/test_gui_cover_entry.py` | **新增** GUI 入口集成（无 Qt 窗口） |
| `old_gui_entry_backup/*` | 迁移前备份 |
| `gui_migration_report.md` | **本文件** |

**未修改：** `core/pipeline.py`、CLI、ffmpeg、模型、Hermes、Worker、Cache、推理逻辑。

---

## 2. 迁移前调用链

```
GUI PipelineWorker
  → build_pipeline(cb)
  → Pipeline.run(JobContext)
```

---

## 3. 迁移后调用链

```
GUI PipelineWorker
  → worker_params_to_cover_request(...)
  → CoverService.run(request, on_progress=...)     # 无业务逻辑，仅转发
    → PipelineAdapter.run(...)                     # GUI 路径唯一 Pipeline 入口
      → build_pipeline(cb)
      → Pipeline.run(PipelineJobContext)
```

### Progress

```
Pipeline JobManager
  → Adapter ProgressEvent
  → CoverService（透传）
  → apply_stage_elapsed（阶段名不变；elapsed = 阶段内秒数）
  → progress.emit(stage, pct, msg, elapsed)
```

阶段序列：`uvr` → `svc` → `mixing` → `exporting` → `done`

### 异常

| 类型 | 行为 |
|------|------|
| `CoverResult.success=False` | `_friendly_error(error)` → 原 UI 文案 |
| `FileNotFoundError` 等 | 原中文分支不变 |
| 未预期异常 | 不吞；原「模型/处理失败」提示不变 |

---

## 4. 风险

| 风险 | 缓解 |
|------|------|
| 配置默认值漂移 | Worker 仍读 `ConfigLoader` 写 `f0_method` / `export_mp3` |
| 进度 elapsed 语义 | `apply_stage_elapsed` 复刻旧逻辑 |
| CLI/API 仍直连 Pipeline | 本阶段故意保留；仅 GUI 路径经 Adapter |

---

## 5. 回滚方案

1. 从 `old_gui_entry_backup/PipelineWorker_pre_p2.py` 恢复 `PipelineWorker` + imports（`JobContext` / `build_pipeline` / `resolve_path`）  
2. 或 `git checkout` / revert 相关改动  
3. 不需改 Pipeline / 模型 / ffmpeg  

---

## 6. 测试结果

### 自动化

```text
pytest -q tests/
22 passed
```

### 完整 Cover 路径（GUI 入口组合 + mock_mode）

```text
success True
stages ['uvr', 'svc', 'mixing', 'exporting', 'done']
mp3/wav 已生成
Profiling report written: profiling_report.md / profiling.json / commands.log
```

### 人工 GUI

请**重启桌面端**后点一次「生成翻唱」做真实模型冒烟（自动化未拉起 Qt 窗口）。

---

## 7. 本阶段明确未做

- Hermes  
- UVR Persistent Worker  
- Cache  
- GPU 优化  
- CLI / Flask 改走 CoverService  

**P2 完成，停止。等待下一阶段指令。**
