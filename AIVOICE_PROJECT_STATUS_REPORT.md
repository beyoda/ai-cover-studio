# AIVOICE / ai-cover-studio — 项目现状与改进报告

> 日期：2026-07-27  
> 目的：给外部评审（含 GPT）一份可独立阅读的现状快照 + 改进建议入口  
> 范围：Windows 本地 AI 翻唱（UVR → so-vits-svc → ffmpeg）+ Hermes Skill + 飞书 Gateway  
> 最近一次真实成功：`ExampleVoiceB` 翻唱「示例歌手 / ExampleArtist《示例曲目》」，全流程约 **88s**

---

## 1. 一句话定位

本地 AI 翻唱工作室：把任意歌曲换成指定音色（当前 Registry：`example_voice` / `example_voice_b`），产出 `cover.mp3`。  
主入口已从「仅 GUI」扩展到 **Hermes Agent Skill + 飞书私聊**，音乐输入支持本地路径、直链、**GD音乐台搜歌选曲**。

---

## 2. 系统架构（当前）

```text
飞书用户
  → Hermes Gateway (websocket)
  → Hermes Agent + aivoice-cover Skill
  → aivoice_cover.py
       ├─ Voice Registry (config/voices.json)
       ├─ MusicSource (local / URL / GDStudio search+track_id)
       └─ CoverService → Pipeline
            UVR (audio-separator, DirectML) → SVC (so-vits-svc CUDA workenv)
            → VocalFX → Mixer → Export MP3
```

| 层 | 路径 / 组件 | 备注 |
|---|---|---|
| 核心流水线 | `src/aivoice_studio/core/pipeline.py` + `modules/{uvr,svc,mixer}` | 子进程编排，不宜大改 |
| Cover API | `cover/service` + `CoverRequest` | Skill / 未来 Worker 的稳定边界 |
| 音色 | `config/voices.json` + `cover/voice_registry.py` | 禁止硬编码 checkpoint |
| 曲源 | `cover/music_source/` | Local / GDStudio；歌名 → 候选列表 |
| Hermes Skill | `hermes_skill/media/aivoice-cover/` | 经 `external_dirs` 挂载，与仓同版本 |
| 桌面 GUI | `ui/main_window.py` | 仍可用；与飞书路径并行 |
| Profiling | `profiling/` | 每单可出 stage 耗时与 GPU 采样 |

配置要点：

- `config/uvr.yaml` → `scripts/uvr_directml.py`（CLI 无 `--use_directml`，故薄封装）
- `config/svc.yaml` → 独立 `tools/so-vits-svc/workenv`（CUDA Torch）
- Hermes：`skills.external_dirs = <repo-root>/hermes_skill`

---

## 3. 已完成能力（按里程碑）

### 3.1 核心翻唱

- [x] UVR 人声分离 + SVC 音色转换 + ffmpeg 混音导出  
- [x] Voice Registry（`example_voice`↔`G_27200/config1`，`example_voice_b`↔`G_16000/configcos`）  
- [x] ExampleVoiceB 配置修复：`configcos.json` 的 `speech_encoder` 改为 `vec768l12`（对齐权重 768，消除旧 256/768 mismatch）  
- [x] 子进程环境隔离：`scrubbed_subprocess_env()` 清掉 Hermes 注入的 `PYTHONPATH`（避免 SVC typing_extensions 崩）

### 3.2 曲源 MusicSource

- [x] 本地文件 / 公开直链  
- [x] GD音乐台公开 API 搜歌 + 聊天选曲（`choice_needed` / `--search` / `track_id`）  
- [x] 歌名变体扩写（「示例歌手 - 示例曲目」「示例歌手的示例曲目」）+ 艺人别名（示例歌手→ExampleArtist）+ 排序  
- [x] 美观候选文案 `pretty`（序号 / 艺人 / 专辑 / id）

### 3.3 Hermes + 飞书

- [x] Skill 发现与启用（`aivoice-cover`）  
- [x] 飞书 websocket Gateway E2E（需 `im:message.p2p_msg:readonly`；`NO_PROXY` 绕过本机 Clash）  
- [x] Skill 硬规则：禁止盲搜代码、选歌与 UVR 状态分离、提交后先 ACK  
- [x] 纠正 Hermes `MEMORY.md` 中过时结论（「不支持按歌名」「ExampleVoiceB 768/256 必挂」）

### 3.4 加速（本机 RTX 4060 Laptop）

- [x] UVR 从 **CPU onnxruntime** 改为 **DirectML**（`onnxruntime-directml` + `torch-directml`）  
- [x] 效果对照（同机）：  
  - 此前长曲 UVR ≈ **340s+**、GPU≈0%  
  - 「示例曲目」成功单：UVR ≈ **22s**（GPU util 峰值 94%），全流程 ≈ **82–88s**  
  - 当前瓶颈已从 UVR 转到 **SVC（约 70% 总时长）**

---

## 4. 最近一次成功样例（示例曲目 / ExampleVoiceB）

| 项 | 值 |
|---|---|
| 用户意图 | 用 example_voice_b 翻唱示例歌手的示例曲目 |
| 选曲 | GD：示例曲目 · ExampleArtist（示例歌手英文名） |
| 音色 | ExampleVoiceB / `G_16000` / `configcos.json` |
| 总时长 | ~88s（profiling 单约 82s） |
| 输出 | `outputs/<job_id>/cover.mp3` |
| UVR | DirectML，~22s |
| SVC | CUDA workenv，~58s |

---

## 5. 已知问题与技术债

### 5.1 产品 / Agent 体验

1. **同步阻塞**：Hermes 用 terminal `wait` 卡满整单；无「已排队 → 完成后推送」的 Worker。短闲聊快，真翻唱仍占会话。  
2. **Agent 易被旧上下文带偏**：曾坚持「曲库不支持按歌名 / ExampleVoiceB 必崩」；需 `/new` + 修正 MEMORY；Skill 无法 100% 约束模型。  
3. **选歌与后台进程串台**：旧 `--search` 进程 exit 2 的输出可能被误当成当前任务状态。  
4. **GD API 不稳**：偶发空结果 / 超时；变体搜索缓解但仍依赖第三方。版权/地域可能导致无播放 URL。  
5. **艺人名不一致**：口语「示例歌手」vs 曲库「ExampleArtist」；别名表需人工维护。

### 5.2 工程 / 运行时

1. **双 Python 环境**：AIVOICE `.venv`（DirectML UVR）vs SVC `workenv`（CUDA）。维护成本高；CUDA Torch 官方轮子大，国内下载慢，故 UVR 走 DirectML 而非 `onnxruntime-gpu`。  
2. **`gpu_serial` 配置存在但未真正实现**队列串行。  
3. **自定义伴奏「跳过 UVR」** 等 UI 文案与 Pipeline 行为可能仍不完全对齐（历史架构债）。  
4. **绝对路径** 散落在 YAML / Skill / bat（本机绑定强）。  
5. **测试覆盖**：MusicSource / Registry 有单测；飞书全链路、DirectML、真实 SVC 多为手工 E2E。  
6. **安全**：飞书调试曾开 `FEISHU_ALLOW_ALL_USERS`；密钥在本机 `.env`（勿入库）。

### 5.3 音质 / 模型

1. 仅 2 个音色；无训练/微调流水线文档化入口。  
2. pitch / reverb 能力有，但飞书侧多轮调参 UX 仍浅。  
3. UVR 模型固定 `UVR_MDXNET_Main.onnx`；未做模型对比评测。

---

## 6. 建议改进方向（供 GPT 评审排序）

以下按「价值 / 风险 / 工作量」给评审方，不要求照单全收。

### P0 — 体验与可靠性

| 建议 | 为什么 | 粗略做法 |
|---|---|---|
| Cover Job Worker + 异步回传 | 飞书不必挂死 1–10 分钟 | Skill 只 `submit`，Gateway/cron 完成后发 `cover.mp3` |
| 会话状态机：search → pick → cover | 减少 Agent 自由发挥 | Skill 显式子命令或 JSON state；禁止无 `--search` 直接瞎猜失败话术 |
| GD 失败降级策略 | API 空/超时 | 缓存最近候选；超时重试；明确「换歌名/艺人名」提示 |
| 一单互斥锁 | 双开 cover 抢 GPU | 文件锁 / `gpu_serial` 真正落地 |

### P1 — 性能

| 建议 | 为什么 | 粗略做法 |
|---|---|---|
| 加速 SVC（已成主瓶颈） | 示例曲目单 SVC≈58s / 70% | 检查 half / 批大小 / f0 方法；或保持模型预热常驻 |
| UVR 模型缓存常驻 | 冷启动仍有加载 | 可选 long-lived separator 进程（慎：显存） |
| 可选真正 CUDA ORT | DirectML 已够用，CUDA 或更快 | 有稳定 cu12 镜像再换；勿破坏现网 DirectML |

### P2 — 产品扩展

| 建议 | 为什么 |
|---|---|
| 更多音色进 Registry | 用户只认「声音名字」 |
| 飞书：进度条/阶段推送（UVR/SVC/导出） | 体感透明 |
| 历史作品列表 + 一键重做（换 pitch） | GUI 已有部分，飞书未对齐 |
| 允许用户上传飞书音频文件作 source | 绕过 GD 版权限制 |

### P3 — 工程质量

| 建议 | 为什么 |
|---|---|
| 路径配置相对化 / 环境变量 | 可迁移到第二台机器 |
| 契约测试：Skill JSON schema | 防 Agent 乱传参 |
| 文档收敛：单一 README + 本报告，减少散落 `*_report.md` | 降低评审噪音 |
| 收紧飞书 allowlist | 调试完关掉 allow-all |

---

## 7. 明确「不要轻易动」的边界

团队约束（历史反复强调）：

- 不要重写 Pipeline / UVR / SVC / GUI 核心「为了好看」  
- 音色解析以 Registry 为准，禁止 Skill 硬编码 checkpoint  
- 不把 Telegram / 未设计的多 Worker 集群一次做完  
- GD 只走公开 API，不做登录破解 / 付费绕过  

改进应优先落在：**MusicSource、Voice Registry、CoverService 边界、Hermes Skill、异步 Job**。

---

## 8. 给 GPT 的评审提问（可直接粘贴）

请基于以上报告评估并给出优先级排序：

1. 若目标是「飞书日常可用的翻唱助手」，下一步最该做 Worker 异步，还是先扩音色 / 音质？  
2. UVR 已 DirectML、SVC 占 70%：SVC 加速的合理上限与风险（显存 8GB 笔记本）？  
3. Agent Skill 如何从「文档约束」升级到「难违反的状态机」，仍保持自然语言入口？  
4. GD音乐台作为曲源的长期风险（稳定性、版权）与替代方案？  
5. 双 venv（DirectML + CUDA SVC）是否应合并，还是维持隔离更安全？  
6. 对当前架构分层（Registry / MusicSource / CoverService / Skill）有无过度设计或缺口？

---

## 9. 关键文件索引

| 主题 | 文件 |
|---|---|
| 架构盘点 | `AIVOICE_ARCHITECTURE.md` |
| MusicSource | `music_source_report.md`、`src/aivoice_studio/cover/music_source/` |
| Voice Registry | `voice_registry_integration_report.md`、`config/voices.json` |
| Hermes Skill | `hermes_skill/media/aivoice-cover/SKILL.md` |
| 飞书设计 / E2E | `hermes_messaging_design.md`、`hermes_messaging_e2e_report.md` |
| 性能 | `profiling_report.md`（最新成功单） |
| UVR GPU 封装 | `scripts/uvr_directml.py`、`config/uvr.yaml` |

---

## 10. 总结判断（作者观点，供驳）

项目已经跨过「能在飞书里搜歌 → 选曲 → ExampleVoiceB 翻唱出成品」的可用性门槛；**最大体验缺口是同步等待与 Agent 记忆/话术漂移**，**最大性能缺口是 SVC**（UVR DirectML 已明显见效）。  
短期应用工程优先：**异步 Job + 更硬的选歌状态机 + 一单互斥**；模型侧再谈 SVC 加速与扩音色。
