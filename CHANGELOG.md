# Changelog

## [1.0.0] — 2026-07-28 — AIVOICE v1.0 Stable

首个可日常使用的个人 AI 音频服务冻结版。

主闭环：

```text
飞书 → Hermes Gateway → aivoice-cover Skill → 入队
  → Worker (按需 drain) → UVR → SVC → 混音导出
  → Outbox → Notifier → 飞书收到成品
```

### Added

- **飞书自然语言入口**：经 Hermes Gateway + `hermes_skill/media/aivoice-cover`
- **MusicSource**：本地路径 / URL / GD音乐台搜索与选曲、`track_id`、本地缓存
- **Voice Registry**：`config/voices.json`（含 ExampleVoiceB / example_voice 等），禁止硬编码 checkpoint
- **CoverService + Pipeline**：UVR（DirectML）→ so-vits-svc → 混音 / 导出 MP3
- **File Job Queue**：`jobs/{queued,running,completed,failed,outbox}`
- **Worker**：claim / execute / lock；`--drain` 按需清空队列后退出
- **Outbox + Notifier**：完成事件、Mock/Real Feishu Client、文案 + mp3 自动推送
- **按需流水线 kick**：Skill 入队后后台 `scripts/kick_cover_pipeline.py`
- **投递目标推断**：`--session-id` 的 `ou_`/`oc_`，或从 Gateway 日志回填
- **升降调 / 混响**：自然语言 pitch（升/降 key）与混响开关
- **完成通知文案**：含完成时间与耗时
- **示例资产（Git LFS）**：`examples/voices/example_voice`、`examples/models/uvr`、`examples/demo/eason_preview.mp3`
- **在线试听**：`examples/demo/eason_preview.mp3`（约 25s 真实 example_voice《示例曲目》翻唱片段，GitHub 可直接播放）
- **模型说明**：`docs/MODEL_GUIDE.md`（可用模型条件 + so-vits-svc 训练概要）
- **免责声明**：`docs/DISCLAIMER.md`（示例音色 / 歌曲版权 / 训练 / 无担保等详细条款）
- **一键安装**：`scripts/setup_tools.ps1`（装示例模型 / 准备 so-vits-svc 源码 / 写配置路径）
- **GUI 路径保留**：桌面端仍可经 CoverService 使用

### Performance (实测量级)

- 冷启动全流程约 **1 分钟**（UVR ~15–20s + SVC ~30–50s，视歌曲与缓存而定）
- UVR 缓存命中时可明显缩短

### Known limits (v1.0 不修)

- Hermes Gateway 需本机常驻（未做开机自启封装）
- Worker 按需拉起；电脑休眠/关机则飞书不可达
- 未做多 Worker 并行、Web UI、多平台入口
- 精细 EQ / 自动变调策略 / 多段剪辑不在本版

### Freeze policy

v1.0 起默认**不继续堆功能**。体验与质量优化走 v1.1+；Athena / 多角色等走后续主线。

---

## Unreleased

（冻结后新改动记在此处，直至下一版本号。）

### Changed — 开源发布准备（Open-source readiness）

- **移除全部第三方资产**：`examples/voices/example_voice/G_27200.pth`（628 MB）、`examples/models/uvr/UVR_MDXNET_Main.onnx`（67 MB）、`examples/demo/eason_preview.mp3` 不再随仓库分发；对应路径已加入 `.gitignore`，本地原件未受影响。仓库现在只发布代码。
- **`scripts/setup_tools.ps1` 重写**：默认只做**诊断**，不再 `git lfs pull`、不再把示例模型复制进运行时目录、不再覆盖 `config\svc.yaml`。缺组件时逐项列出下一步并支持 `-Strict` 以非零码退出，不再虚报安装成功。克隆 so-vits-svc 源码改为显式 `-CloneSvcSource`。
- **配置去除个人机器路径**：`config/svc.yaml`、`config/uvr.yaml` 改为相对路径；`config/uvr.yaml` 新增 `{python}` 占位符（由 `UVRService` 用 `sys.executable` 填充），UVR 子进程工作目录固定为仓库根。
- **`config/voices.json` 改为空模板**：移除了具体艺人音色与 `G_27200`/`G_16000` 硬编码，改为一条 `example_voice` + `"enabled": false`，`default_voice_id: null`。
- **`config/svc.yaml` 移除 `default_model`**，不再默认指向某个未授权 checkpoint。
- **`AI Cover Studio.bat` 可移植化**：改用 `%~dp0`，不再写死本机绝对路径；清理临时文件需输入 `YES` 确认。
- **补齐缺失源码包**：`src/aivoice_studio/models/`（`__init__.py`、`results.py`）此前从未提交，导致全新克隆 `import aivoice_studio` 直接 `ModuleNotFoundError`；现已纳入版本控制。
- **移除构建产物**：`src/aivoice_studio.egg-info/` 不再跟踪，`*.egg-info/` 加入 `.gitignore`。
- **移除生成的 profiling 产物**：`profiling_report.md`、`issues.md` 由 `src/aivoice_studio/profiling/report.py` 在每次插桩运行时重写，之前被提交且内容含个人绝对路径；现已取消跟踪并加入 `.gitignore`（与已有的 `profiling.json` / `metrics.csv` / `commands.log` 一致）。
- **补齐依赖声明**：`pyproject.toml` 的 `dependencies` 缺少 `requests`（`aivoice_studio.notifier` 在模块级导入），导致全新克隆 `pytest` 直接收集失败；现已补上，并把 `flask` / `yt-dlp` / `pillow` / `psutil` / `ffmpeg-python` 归入可选 extras。
- **测试可在全新克隆运行**：Voice Registry 与 Music Source 相关测试改为使用临时目录中的合成注册表，不再依赖特定艺人音色、本机 `.venv` 路径或真实模型文件；新增 `tests/test_install_consistency.py` 作为配置一致性护栏（可移植路径、不下载、不覆盖配置、无被跟踪的模型/音频二进制、无未声明依赖、无被跟踪的生成物、README 链接可达）。
- **文档更新**：README 增补 Bring Your Own Models / Tests 章节，修正安装步骤与实际脚本行为；`docs/MODEL_GUIDE.md` 补充 UVR 模型位置、环境自检与模板说明。

### Remaining (not in this change)

- Git 历史与 LFS 远端仍保有旧资产的 blob；彻底清除需要重写历史与强制推送（待确认）。
- `hermes_skill/` 仍指向个人部署（固定本机绝对路径、个人音色 id），需要单独一次脱敏。
- `src/aivoice_studio/server/*`、`ui/main_window.py`、`scripts/run_cli.ps1` 等处仍有示例模型名兜底字符串。
- 根目录若干内部设计/测试报告（`AIVOICE_*_REPORT.md`、`hermes_*_report.md`、`aivoice_v1.3_*.md`、`post_migration_profiling.md` 等）仍含本机绝对路径，属于历史文档，建议单独一轮清理或移入 `docs/internal/`。
