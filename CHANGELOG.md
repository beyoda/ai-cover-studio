# Changelog

Notable changes to this project are recorded here.

The package version lives in [`pyproject.toml`](pyproject.toml) and is currently
`0.1.0`. The bracketed headings below are internal development milestones, not
published releases: this repository is pre-1.0, and no stable release has been
declared.

## [0.1.0] — 2026-07-28 — 首个可用里程碑（内部标记 “v1.0”，非公开发布）

首个可日常使用的个人 AI 音频服务冻结版。

> 本节记录当时的实现状态。其中若干行为（示例资产分发、`setup_tools.ps1` 的默认动作、配置中的绝对路径）已在下方 `Unreleased` 中变更；版本号 `1.0` 仅为内部里程碑标记，与 `pyproject.toml` 的 `0.1.0` 对应同一份代码。

主闭环：

```text
飞书 → Hermes Gateway → aivoice-cover Skill → 入队
  → Worker (按需 drain) → UVR → SVC → 混音导出
  → Outbox → Notifier → 飞书收到成品
```

### Added

- **飞书自然语言入口**：经 Hermes Gateway + `hermes_skill/media/aivoice-cover`
- **MusicSource**：本地路径 / URL / GD音乐台搜索与选曲、`track_id`、本地缓存
- **Voice Registry**：`config/voices.json`，禁止硬编码 checkpoint（发布版已改为空模板，见下）
- **CoverService + Pipeline**：UVR（DirectML）→ so-vits-svc → 混音 / 导出 MP3
- **File Job Queue**：`jobs/{queued,running,completed,failed,outbox}`
- **Worker**：claim / execute / lock；`--drain` 按需清空队列后退出
- **Outbox + Notifier**：完成事件、Mock/Real Feishu Client、文案 + mp3 自动推送
- **按需流水线 kick**：Skill 入队后后台 `scripts/kick_cover_pipeline.py`
- **投递目标推断**：`--session-id` 的 `ou_`/`oc_`，或从 Gateway 日志回填
- **升降调 / 混响**：自然语言 pitch（升/降 key）与混响开关
- **完成通知文案**：含完成时间与耗时
- **示例资产（Git LFS）**：`examples/voices/`、`examples/models/uvr/`、`examples/demo/` 下的示例音色 / UVR 权重 / 试听片段（**发布时已全部移除，见下**）
- **在线试听**：`examples/demo/` 下的短试听片段（约 25s，GitHub 可直接播放；**已移除**）
- **模型说明**：`docs/MODEL_GUIDE.md`（可用模型条件 + so-vits-svc 训练概要）
- **免责声明**：`docs/DISCLAIMER.md`（示例音色 / 歌曲版权 / 训练 / 无担保等详细条款）
- **一键安装**：`scripts/setup_tools.ps1`（当时会安装示例模型 / 准备 so-vits-svc 源码 / 写配置路径；已在下方改为默认只诊断）
- **GUI 路径保留**：桌面端仍可经 CoverService 使用

### Performance (实测量级)

- 冷启动全流程约 **1 分钟**（UVR ~15–20s + SVC ~30–50s，视歌曲与缓存而定）
- UVR 缓存命中时可明显缩短

### Known limits (该里程碑不修)

- Hermes Gateway 需本机常驻（未做开机自启封装）
- Worker 按需拉起；电脑休眠/关机则飞书不可达
- 未做多 Worker 并行、Web UI、多平台入口
- 精细 EQ / 自动变调策略 / 多段剪辑不在该里程碑

### Scope policy

自该里程碑起默认**不继续堆功能**。体验与质量优化走后续版本；多角色等走后续主线。

---

## Unreleased

（内部里程碑之后的新改动记在此处，直至下一版本号。两轮「开源发布准备」都记在本节。）

### Changed — 开源发布准备（第一轮：配置与资产）

- **移除全部第三方资产**：示例音色权重（约 628 MB）、UVR 分离权重（约 67 MB）与试听片段不再随仓库分发；对应路径（`examples/voices/**/*.pth`、`examples/models/**/*.onnx`、`examples/**/*.mp3`）已加入 `.gitignore`，本地原件未受影响。仓库现在只发布代码。
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

### Changed — Hermes 集成去个人化（第二轮）

- **移除个人绝对路径**：`SKILL.md` 与验证脚本改用 `<repo-root>` / 由脚本自身位置推导的路径；不再出现维护者机器路径。
- **音色不再硬编码**：新增 `hermes_skill/media/aivoice-cover/scripts/voice_lookup.py` 作为 Voice Registry 桥接（`default_voice_id()` / `available_voice_ids()` / `resolve_voice_id()`）；`session_state.build_cover_request_from_pick` 的兜底音色改为读注册表，注册表为空时返回 `None` 而不是猜测。
- **示例改为合成数据**：`validate_beta.py`、`validate_e2e.py`、`validate_experience.py` 全部改为在临时目录生成合成注册表（`alpha` / `beta` 两条音色），并通过 `AIVOICE_VOICES_CONFIG` 注入，不再读取也不写入用户的 `config/voices.json`。
- **删除个人化夹具**：移除 `hermes_skill/media/aivoice-cover/scripts/` 下两份请求样例（`_request_*.json` 含个人音色 id 与本机音频路径，`cover_request.json` 含商业歌曲查询）；新增可复制的 `example_request.json` 骨架（占位值不可直接运行）并写入 `SKILL.md`。
- **新增共享测试夹具**：`scripts/testkit.py`（合成注册表、临时 session/队列目录、可移植解释器、`run_skill()`）。
- **保持功能完整**：自然语言解析、搜索选曲、会话状态、入队、状态查询与通知路径均保留，仅替换其中的个人数据；验证脚本以真实子进程调用 Skill 脚本，不做桩替代。

### Changed — 文档去标识化与归档

- **内部分类**：根目录 59 份 Markdown 分类为「公开文档」（`README` / `CHANGELOG` / `CONTRIBUTING` / `SECURITY` / `ROADMAP`）、「内部设计文档」与「历史报告」。
- **内部设计文档移入 `docs/internal/`**（29 份 + `cover_skill/` 子树），并新增 `docs/internal/README.md` 索引；`design/cover_skill/` 随之移动，`design/` 目录已清空。
- **历史报告取消跟踪**（25 份 `*_report.md` 等）：含真实运行路径与个人音色，不属于公开发布内容；文件已移出克隆（保留在本地归档目录），Git 历史中仍可检出。
- **去标识化**：共享 `example_voice` / `example_voice_b` / `示例歌手` / `示例曲目` 与 `C:/path/to/...` 占位路径，替换个人音色 id、艺人名、商业歌曲名与本机绝对路径。
- **修正交叉引用**：修正移动后失效的相对引用，并新增护栏测试（全部被跟踪文档的相对链接必须可达、文档不得出现机器路径、文档不得出现私人音色标识）。

### Changed — 剩余发布阻断项

- **版本口径统一**：README 不再宣称 `v1.0.0` 稳定版，改为与 `pyproject.toml` 一致的 `0.1.0` + 明确的 pre-1.0 说明。
- **依赖护栏不再依赖环境**：`tests/test_install_consistency.py` 的 `declared_distributions()` 改为直接解析本仓库 `pyproject.toml`（`tomllib`，3.10 回退 `tomli`），不再读取其他目录安装产生的分发元数据；`dev` extra 增加 `tomli; python_version < "3.11"`。
- **UVR/SVC 命令模板支持含空格的路径**：新增 `aivoice_studio.utils.process.split_command_template()`（先分词、后代入，保留反斜杠，支持引号），`separator.py` 与 `svc_runner.py` 共用；新增 `tests/test_command_template.py` 作为回归测试。
- **去除非必需的默认模型兜底**：`server/api.py`、`server/feishu.py`、`ui/main_window.py`、`cli.py`、`scripts/run_cli.ps1`、`scripts/p4_real_cover_verify.py` 不再回落到示例模型名；无可用音色时给出明确提示 / 非零退出。
- **艺人别名表改为用户可配置**：`gdstudio.py` 硬编码别名移除，改为 `config/artist_aliases.json`（默认空）与 `AIVOICE_ARTIST_ALIASES` 覆盖；搜索扩写与排序能力保留。
- **新增环境变量覆盖**：`AIVOICE_JOBS_DIR`（队列根目录）与 `AIVOICE_SKIP_PIPELINE_KICK`（不自动拉起 worker），便于隔离部署与离线验证；`kick_cover_pipeline.py` 与 `notifier` 共用同一队列根解析。
- **免责声明补齐条款**：`docs/DISCLAIMER.md` 增加输入素材授权、训练数据、冒充/官方授权声明（不声称任何艺人、厂牌或权利方的授权或背书）。
- **README 使用既有资源**：未引用的 `docs/assets/aivoice-hero.svg` 现用于 README 顶部；新增 Documentation 导航。

### Remaining (not in this round)

- Git 历史与 LFS 远端仍保有已移除资产的 blob；彻底清除需要重写历史与强制推送（本轮明确不做）。
- 历史上提交过的个人绝对路径仍可从旧提交（如 `dcd944c`）检出；最新工作区已清理，但**历史未重写**。
- 真实 GPU 全链路（UVR → SVC → 混音）在本轮环境中没有可用的运行时与授权素材，状态为**未验证**；仓库内的验证脚本对该阶段明确标记 `SKIP`。
- 缺少可公开的运行时界面截图。
- 推送到 GitHub 需要凭据，当前环境没有可用凭据（未推送）。

## Update — 2026-09-17 (post-publication)

The preceding "Remaining (not in this round)" block was written at the end of the in-repo preparation round and reflects that snapshot only. As of **2026-09-17**, verified against the public GitHub API:

- `main` HEAD has been force-pushed to `482056000cb6500075f1f6e63980355b10279abe`.
- The `v1.0.0` tag's object is `cb129e49279598da177fd7c3e266c28d96de69ff`. The tag labels the same freeze described under `[0.1.0]` above as an *internal* milestone and points to code version `0.1.0`; it is not a separate published release.
- Old commits that held private paths, personal voice ids, or artist-specific references have been replaced in the published history. A complete replacement of all in-tree content was verified against the 213 tracked files at the current HEAD.

This commit is a documentation-only follow-up: it adjusts `README.md` and `CHANGELOG.md` to match the public state above. It does **not** rewrite history, does **not** move or re-tag the `v1.0.0` tag, and does **not** access the orphaned LFS objects.

Still open and **not** addressed in this round:

- GitHub Support ticket **#4767216** — server-side cleanup of remaining reachable old commit blobs and the four orphaned LFS objects (including a private training voice model) has not been confirmed on the GitHub side. Resolution depends on GitHub Support, and is out of scope for this documentation update.

The "真实 GPU 全链路未验证" and "缺少运行时界面截图" items above continue to be true after 2026-09-17 and remain placeholders for the maintainer's own validation, **not** claims about this published code.

