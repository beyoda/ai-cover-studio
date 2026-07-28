# P4 Service 化实现报告

> 阶段：P4 — Job API + 最小 UVR Cache  
> 日期：2026-07-26  
> 结论：**完成**。`CoverService` 已支持 `submit` / `status` / `result`；UVR stems 本地文件缓存可用；GUI 同步 `run()` 路径保持兼容。

---

## 1. 目标与边界

| 项 | 状态 |
|----|------|
| Job API：`submit()` / `status()` / `result()` | ✅ |
| 保留同步 `run()`（GUI） | ✅ |
| 最小 UVR Cache（仅分离结果） | ✅ |
| 禁止：Worker / Redis / DB / GPU 优化 / 社交通道 | ✅ 未引入 |

实现要点：

- Job 存于进程内 `JobStore`（dict + `RLock`）。
- 执行槽：`ThreadPoolExecutor(max_workers=1)`（任务线程，非常驻模型 Worker）。
- 成功终态状态字为 **`completed`**（与本阶段验证用语一致）。
- UVR Cache：`cache/uvr/{sha256}/vocals.wav|instrumental.wav|meta.json`。

---

## 2. 修改文件

### 新增

| 文件 | 说明 |
|------|------|
| `src/aivoice_studio/cover/domain/job_record.py` | `JobStatus` / `CoverJobRecord` / `JobStatusView` |
| `src/aivoice_studio/cover/job_store.py` | 内存 Job 存储 |
| `src/aivoice_studio/cover/uvr_cache.py` | UVR stems 文件缓存 |
| `tests/test_job_service.py` | Job API 自动测试 |
| `tests/test_cache.py` | Cache 命中/写入测试 |
| `scripts/p4_real_cover_verify.py` | 真实翻唱 submit→poll→result |
| `p4_real_cover_result.json` | 真实验证原始结果 |
| `p4_service_report.md` | 本报告 |

### 修改

| 文件 | 说明 |
|------|------|
| `src/aivoice_studio/cover/service/cover_service.py` | 增加 `submit` / `status` / `result`；保留 `run()` |
| `src/aivoice_studio/cover/adapter/pipeline_adapter.py` | 查询/写入 UVR cache；命中时 `skip_uvr` |
| `src/aivoice_studio/cover/__init__.py` | 导出 Job/Cache 相关符号 |
| `src/aivoice_studio/core/context.py` | `skip_uvr` / `cached_vocal` / `cached_instrumental` |
| `src/aivoice_studio/core/pipeline.py` | cache 命中时跳过 `uvr.separate`，复制 stems |
| `.gitignore` | 忽略 `cache/` |

未改：推理命令、模型、ffmpeg、GUI 业务逻辑（仍走 `CoverService().run(...)`）。

---

## 3. 自动测试结果

```text
pytest tests -q
35 passed in 0.67s
```

覆盖（本阶段要求）：

| 用例 | 文件 | 结果 |
|------|------|------|
| submit 成功 | `test_job_service.py` | ✅ |
| status 变化 → completed | `test_job_service.py` | ✅ |
| result 获取 | `test_job_service.py` | ✅ |
| error / failed | `test_job_service.py` | ✅ |
| cache 命中（Adapter `skip_uvr`） | `test_cache.py` | ✅ |
| GUI `run()` 回归 | `test_gui_cover_entry.py` 等 | ✅ |

---

## 4. 真实翻唱验证

| 项 | 值 |
|----|----|
| 输入 | `<repo-root>\test_songs\示例歌手 - 示例曲目.mp3` |
| 模型 | `G_16000` |
| 流程 | `submit` → `job_id` → `status` 轮询 → `completed` → `result` |
| job_id | `b7b3ef418107` |
| 终态 | **completed** |
| success | **true** |
| 墙钟 | **139.07 s** |
| WAV | `<repo-root>\outputs\b7b3ef418107\cover.wav` |
| MP3 | `<repo-root>\outputs\b7b3ef418107\cover.mp3` |
| 本次 cache hit | false（首次，预期 miss） |
| 跑后 cache 已写入 | **true**（`cache/uvr/c3e936a2…`） |

阶段观测（同次 profiling）：

| Stage | 约耗时 |
|-------|--------|
| UVR | 107.46 s（~77.8%） |
| SVC | 28.29 s |
| Export | 2.19 s |
| Mixer | 0.18 s |

状态轨迹摘要：`running/pending` → `running/uvr` → `running/svc` → `running/exporting` → **`completed/done`**。

---

## 5. GUI 回归

| 检查 | 结果 |
|------|------|
| `PipelineWorker` → `CoverService.run()` 未改为 submit | ✅ 保持同步入口 |
| `tests/test_gui_cover_entry.py`（mock 翻唱） | ✅ 通过 |
| 既有 cover 契约测试 | ✅ 通过 |

GUI 仍可按原方式启动翻唱；Job API 为增量能力，不阻塞现有界面。

---

## 6. 性能影响

| 项 | 影响 |
|----|------|
| Job 编排（submit/status/result） | 可忽略（内存 + 单线程池） |
| 同步 `run()` | 契约不变；Adapter 增加一次 cache lookup（哈希读盘） |
| UVR cache miss | 成功后复制 stems → `cache/uvr/`（数秒级 IO，远小于 UVR） |
| UVR cache hit | **跳过 UVR 分离**（本曲约可省 ~107 s） |
| 相对 P2.5 CoverService 路径 | 无推理/GPU 改动；瓶颈仍是 UVR CPU |

---

## 7. 回滚方式

1. **代码回滚**（推荐）：还原本阶段改动的 cover / pipeline / context 文件，删除新增的 `job_store.py` / `uvr_cache.py` / `job_record.py` 与对应测试。
2. **关闭缓存**：不删代码时，可设 runtime `uvr_cache: false`，或向 `PipelineAdapter(UvrCache(enabled=False))` 注入禁用缓存。
3. **清除缓存数据**：删除目录 `<repo-root>\cache\uvr\`。
4. **GUI**：始终可用 `CoverService.run()`；即使移除 Job API，同步路径仍可独立保留。

示例（git，若已提交）：

```bash
git checkout HEAD~1 -- src/aivoice_studio/cover src/aivoice_studio/core/pipeline.py src/aivoice_studio/core/context.py
```

（请按实际提交点调整；未提交时用本地备份 / `git restore` 即可。）

---

## 8. 阶段结束

P4 验证项均已满足。**本阶段停止**；未实现 Redis、数据库、常驻模型 Worker、GPU 优化或社交通道集成。
