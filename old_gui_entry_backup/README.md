# old_gui_entry_backup

迁移前（P2 之前）GUI Cover 入口备份。

| 文件 | 说明 |
|------|------|
| main_window.py.pre_p2.py | 迁移前完整 main_window.py（git HEAD） |
| PipelineWorker_pre_p2.py | 仅 PipelineWorker（直连 uild_pipeline） |

## 回滚

将 PipelineWorker 与相关 import（JobContext, uild_pipeline, 
esolve_path）恢复到 src/aivoice_studio/ui/main_window.py。

调用链：

`
GUI → build_pipeline() → Pipeline.run(JobContext)
`
