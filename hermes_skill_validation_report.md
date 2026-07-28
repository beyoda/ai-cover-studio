# Hermes Skill Validation Report

> Phase: AIVOICE v1.1-2.5 Beta  
> Date: 2026-07-26  
> Scope: Skill UX / 触发 / 解析 / 错误 / 真翻唱；**未改** Pipeline / Adapter / CoverService 核心 / GUI / SVC / UVR  
> Companion: `music_source_design.md`

---

## 总评

**AIVOICE Skill 达到 Beta 可用状态。**

依据：Hermes 可发现 Skill；自然语言 → `voice_id` / pitch / reverb 规则可验证；错误友好；`example_voice` + 示例曲目.mp3 真翻唱成功；全量 pytest 35 passed。  
长任务仍为**单进程阻塞等待**（JobStore 限制），已用提交确认 + 阶段日志缓解，真正「提交后非阻塞通知」留待后续常驻服务。

未进入：Voice Registry / GPU / Worker / Cache 升级。

---

## 1. Skill 发现

**结果：PASS**

- `hermes skills list` 显示 `aivoice-cover`（media / local / enabled）
- `external_dirs`: `<repo-root>/hermes_skill`
- 未改 Hermes bundled skills

---

## 2. 自然语言触发

**结果：PASS**

- `SKILL.md` description / When to Use 覆盖：  
  「帮我把这首歌翻唱成示例歌手的声音」「用ExampleVoice声音翻唱」「用示例歌手音色唱」「使用example_voice模型」「用example_voice_b声音翻唱」等  
- 版本升为 `1.0.0-beta`  
- 说明：本阶段以 **Skill 契约 + 离线话术映射** 验收；未跑交互式 Hermes chat 会话（避免引入网关变量）

---

## 3. voice_id 解析

**结果：PASS**

离线用例（`param_parse.normalize_voice_id` / `validate_beta.py`）：

| 话术 | → voice_id |
|------|------------|
| 示例歌手 / ExampleVoice / example_voice / 使用example_voice模型 / 用ExampleVoice声音翻唱 / 用示例歌手音色唱 | `example_voice` |
| 用example_voice_b声音翻唱 / example_voice_b | `example_voice_b` |

全部 PASS。

---

## 4. pitch 解析

**结果：PASS**

| 话术 | → pitch |
|------|---------|
| 升两个key | 2 |
| 升2个调 | 2 |
| pitch +2 | 2 |
| 降一个key | -1 |

全部 PASS。

混响：

| 话术 / 值 | → options.reverb（脚本侧） |
|-----------|------------------------------|
| 不要混响 / 关闭reverb / `false` | `关闭` |
| 打开混响 / `true` | `录音棚` |

（验收稿中的 `reverb: false/true` 在脚本内归一为 AIVOICE 字符串，避免改 CoverRequest。）

---

## 5. 多轮交互

**结果：PASS**

- `SKILL.md` 强制：仅说「我要做一个翻唱」时**禁止**直接跑脚本，须询问路径 + 音色列表 + 可选 pitch/混响  
- 离线：`["我要做一个翻唱"]` 无 voice；加上「示例歌手」→ `voice_id=example_voice`  
- 交互式多轮 Hermes 会话：未实跑（同 §2）

---

## 6. 错误处理

**结果：PASS**

| 用例 | 期望 | 实际 |
|------|------|------|
| `D:\not_exist.mp3` | `status=failed`, `error` 含 `input file not found` | PASS |
| 非音频（`.py`） | `unsupported audio format` | PASS |
| stdout | 无 Python Traceback | PASS |

---

## 7. 长任务体验

**结果：PARTIAL**

| 期望（理想） | Beta 实际 |
|--------------|-----------|
| Hermes 不阻塞；提交后阶段通知再完成回调 | 单脚本内 `submit`+轮询至结束（进程阻塞至完成） |
| 提交时告知 job / 约 2 分钟 | ✅ stderr：`{"status":"queued","job_id":...}` + 中文提示 |
| 阶段：[UVR]/[SVC]/[Export] | ✅ stderr 阶段日志 |
| 完成后通知 | ✅ 最终 stdout JSON + stderr「翻唱完成」 |

**判定：** 体验层缓解 **PASS**；真·非阻塞架构 **未达成** → 总项标 **PARTIAL**。  
真异步需常驻 Job HTTP（明确不在本阶段做）。

---

## 8. 音乐来源扩展设计

**结果：完成**

文档：`music_source_design.md`  
- 当前仅本地路径  
- `MusicSource` 抽象 + Downloader → 临时文件 → CoverService  
- GDStudio 适配草案与风险  
- **未实现**下载（有意推迟到 v1.1-3）

---

## 9. 真实翻唱验收

| 项 | 值 |
|----|-----|
| 歌曲 | `示例歌手 - 示例曲目.mp3` |
| voice_id | `example_voice` |
| pitch | 0 |
| 结果 | `completed` |
| job_id（本次 validate） | `7a575af3aa1f` |
| output | `<repo-root>\outputs\7a575af3aa1f\cover.mp3` |
| queued ack | stderr 可见 |
| pytest | **35 passed** |

---

## 10. 本阶段改动面（仅允许项）

| 路径 | 变更 |
|------|------|
| `hermes_skill/media/aivoice-cover/SKILL.md` | Beta 触发 / 多轮 / 解析 / UX |
| `.../scripts/aivoice_cover.py` | 错误文案、格式检查、reverb 归一、阶段日志、queued ack |
| `.../scripts/param_parse.py` | 新增 NL 映射辅助 |
| `.../scripts/validate_beta.py` | 新增离线验收 |
| `music_source_design.md` | 新增设计 |
| `hermes_skill_validation_report.md` | 本报告 |

**未改：** Pipeline / Adapter / CoverService 核心 / GUI / SVC / UVR / 模型加载。

---

## 11. 完成声明

```text
AIVOICE Skill 达到 Beta 可用状态
```

停止。等待下一阶段指令（建议：v1.1-3 Music Source + Voice Registry）。
