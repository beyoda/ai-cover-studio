# Hermes Local End-to-End Integration Report

> Phase: **AIVOICE v1.2-1**  
> Date: 2026-07-26  
> Scope: Hermes → aivoice-cover Skill → CoverService 真实闭环（入口集成）  
> 禁止项遵守：未改 Pipeline / PipelineAdapter 核心 / GUI / SVC / UVR / 模型文件

---

## 总评

**PASS** — Hermes 可发现 Skill；话术可解析为 `input` + `voice_id`；Skill 调用 CoverService 完成 Job；真实输出 `cover.mp3`。

验证脚本：`hermes_skill/media/aivoice-cover/scripts/validate_e2e.py`

---

## 1. Hermes 发现 Skill

| 项 | 结果 |
|----|------|
| `hermes skills list` | 含 `aivoice-cover`（media / local / enabled） |
| `external_dirs` | `<repo-root>/hermes_skill`（`config.yaml`） |
| `SKILL.md` | 可读；含 Examples / 调用脚本说明 |

**PASS**

---

## 2. Skill 调用

| 项 | 结果 |
|----|------|
| 脚本 | `scripts/aivoice_cover.py` |
| `--list-voices` | 返回 Registry `example_voice` + `example_voice_b` |
| Cover | `--json` → `CoverService.submit` → status 轮询 → `result` |

**PASS**

---

## 3. 参数解析

测试输入：

> 使用示例歌手声音翻唱 示例歌手 - 示例曲目.mp3

解析结果：

```json
{
  "input": "示例歌手 - 示例曲目.mp3",
  "voice_id": "example_voice"
}
```

（同时保留 `source` / `source_query` 同值；相对文件名经 `test_songs/` 解析。）

| 附加话术 | 结果 |
|----------|------|
| 用ExampleVoiceB翻唱这首歌 | `voice_id=example_voice_b` |
| 升两个key | `pitch=2`（既有解析） |
| 有哪些声音 | `--list-voices` |

**PASS**

---

## 4. CoverService 执行

| 项 | 值 |
|----|-----|
| `voice_id` | `example_voice` |
| 输入 | `<repo-root>\test_songs\示例歌手 - 示例曲目.mp3` |
| Job ID | `6ee27df85c87` |
| 流程 | submit → status 轮询 → result |

**PASS**（未改 CoverService 核心逻辑；仅 Skill 侧调用）

---

## 5. Job 完成

| 项 | 值 |
|----|-----|
| status | `completed` |
| duration | `34s`（含 UVR cache 命中可能） |

**PASS**

---

## 6. 音频输出

最终 Skill stdout：

```json
{
  "status": "completed",
  "song": "示例曲目",
  "voice": "示例歌手",
  "pitch": 0,
  "duration": "34s",
  "output_path": "<repo-root>\\outputs\\6ee27df85c87\\cover.mp3"
}
```

文件存在且可读。

**PASS**

---

## 变更摘要（仅允许范围）

| 文件 | 变更 |
|------|------|
| `hermes_skill/.../SKILL.md` | v1.2.1-e2e；Examples；成功返回格式 |
| `hermes_skill/.../aivoice_cover.py` | 输出 `song` / `voice` / `pitch` / `duration` / `output_path` |
| `hermes_skill/.../param_parse.py` | 「使用…翻唱 …mp3」→ `input` + `voice_id` |
| `hermes_skill/.../validate_e2e.py` | 发现 / 解析 / 真翻唱验证 |
| `music_source/local.py` | 相对文件名在 `test_songs/` 查找（Source 层） |

---

## 未做

- Telegram 接入  
- Worker  
- GPU 优化  
- 交互式 Hermes chat 全自动会话（以 Skill 契约 + 同进程 CoverService 实跑验收）
