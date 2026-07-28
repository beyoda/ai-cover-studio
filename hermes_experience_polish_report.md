# AIVOICE v1.2-2.5 Hermes Experience Polish — Report

> 日期：2026-07-27  
> 目标：把「能跑通的 Agent」打磨成「更好用的翻唱助手」  
> 范围：仅 Hermes Skill / scripts / 文案 / session；**未改** Pipeline / SVC / UVR / GUI / CoverService 执行逻辑 / 模型权重

---

## 1. 修改文件

| 文件 | 变更 |
|---|---|
| `hermes_skill/media/aivoice-cover/SKILL.md` | v1.2-2.5 流程：`--search` / `--pick` / session / 禁止 ExampleVoiceB 误警告 |
| `hermes_skill/media/aivoice-cover/scripts/aivoice_cover.py` | session、pick、阶段 UX、友好错误、voices pretty |
| `hermes_skill/media/aivoice-cover/scripts/param_parse.py` | NL：音色/pitch/搜歌 action、序号解析 |
| `hermes_skill/media/aivoice-cover/scripts/session_state.py` | **新增** `hermes_skill/runtime/sessions/{id}.json` |
| `hermes_skill/media/aivoice-cover/scripts/user_messages.py` | **新增** 用户文案 / 友好错误 / 阶段标签 |
| `hermes_skill/media/aivoice-cover/scripts/validate_experience.py` | **新增** 体验验收脚本 |
| `hermes_skill/runtime/.gitignore` | 忽略 session 运行时文件 |
| `config/voices.json` | `coa` 别名；去掉会泄露到 Agent 的 768 mismatch 笔记措辞 |
| `%LOCALAPPDATA%/hermes/memories/MEMORY.md` | 去掉「不支持按歌名 / ExampleVoiceB 必挂」旧结论 |

生成物（验收）：`hermes_skill/media/aivoice-cover/scripts/cover_request.json`

---

## 2. 体验变化

### 之前

- 用户回「1」→ LLM 自由猜 track_id / 或复读旧失败话术  
- 翻唱等待像「卡住」  
- ExampleVoiceB 仍被 MEMORY 警告 768/256  
- 错误可能暴露 HTTP / traceback 味道

### 现在

```text
--session-id SID --voice-id example_voice_b --search 示例歌手的示例曲目
  → pretty 候选列表 + stage=waiting_track_choice（落盘）

用户：1
--session-id SID --pick 1
  → 已选择 ACK
  → queued：「收到，任务已进入制作队列…」
  → [1/3] 人声分离 → [2/3] AI音色转换 → [3/3] 混音导出
  → 完成！+ cover.mp3 路径
```

- 数字选择走 **session `--pick`**，不依赖 LLM 猜  
- `--list-voices` 输出 Registry 驱动的「当前可用音色」  
- 错误统一 `user_message` 中文提示  

---

## 3. 测试结果

```text
pytest tests/test_music_source.py  → 8 passed
validate_experience.py             → ALL checks passed
```

验收覆盖：

1. NL「用example_voice_b翻唱示例歌手的示例曲目」→ `action=search`, `voice_id=example_voice_b`  
2. search → choice_needed  
3. `--pick 1 --dry-run` → `cover_request.json`，`voice_id=example_voice_b`，正确 `track_id`  
4. 本地文件 resolve 仍正常  
5. list-voices 无 mismatch /「建议换」话术  

---

## 4. 未修改范围（验收）

- Pipeline / PipelineAdapter  
- SVC 推理代码 / UVR 分离实现  
- GUI  
- CoverService **执行**逻辑（仍 `submit` + `status` 轮询；仅 Skill 侧文案与编排）  
- 模型文件（`.pth` / `.onnx`）  

---

## 5. 最终验收对照

| 标准 | 状态 |
|---|---|
| ExampleVoiceB 不再出现错误警告（Skill/MEMORY/list UX） | ✅ |
| 搜歌→选择→翻唱流程明确 | ✅ |
| 数字选择不依赖 LLM 猜测（session pick） | ✅ |
| 用户收到明确反馈（ACK + 1/3–3/3） | ✅ |
| 错误信息用户可理解 | ✅ |
| Voice Registry 仍是唯一音色来源 | ✅ |
| 测试通过 | ✅ |

---

## 6. 使用提示（飞书）

建议 `/new` 后按 SKILL 跑：

```text
bash -lc "unset PYTHONPATH; exec <repo-root>/.venv/Scripts/python.exe \
  <repo-root>/hermes_skill/media/aivoice-cover/scripts/aivoice_cover.py \
  --session-id <feishu_chat_id> --voice-id example_voice_b --search 示例歌手的示例曲目"
```

用户回序号后：

```text
... --session-id <feishu_chat_id> --pick 1
```

---

## 7. 下一阶段（不在本次）

**v1.3 Async Job Worker**：submit 后立即结束 Agent 轮次，成品主动推送——体验质变点。
