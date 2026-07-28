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
