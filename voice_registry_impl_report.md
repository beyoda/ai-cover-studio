# Voice Registry Implementation Report（v1.1-3A）

> Date: 2026-07-26  
> Goal: `voice_id` → Voice Registry → checkpoint + config  
> Constraints: **未改** Pipeline / PipelineAdapter / GUI / UVR / SVC 推理源码 / Hermes 调用方式（仍跑同一 `aivoice_cover.py`）

---

## 1. 结论

音色资产已由 **`config/voices.json` + `VoiceRegistry`** 统一管理。Hermes Skill 不再内硬编码 `VOICE_ASSETS` 表；通过 Registry 解析后构造 `CoverRequest`，并以 Skill 进程内 path patch 绑定 `-m/-c`（不改 SVC/Adapter 源码）。

**pytest：43 passed**（含新增 `test_voice_registry.py`）。

---

## 2. 交付物

| 路径 | 说明 |
|------|------|
| `config/voices.json` | example_voice / example_voice_b 资产清单 |
| `src/aivoice_studio/cover/voice_registry.py` | `VoiceAsset` / `VoiceRegistry` / `get_voice_registry` |
| `src/aivoice_studio/cover/voice_request.py` | `build_cover_request_for_voice`（CoverRequest 构造） |
| `src/aivoice_studio/cover/__init__.py` | 导出 Registry API |
| `hermes_skill/.../aivoice_cover.py` | 改用 Registry |
| `hermes_skill/.../param_parse.py` | `normalize_voice_id` 优先 Registry |
| `hermes_skill/.../SKILL.md` | 文档指向 Registry |
| `tests/test_voice_registry.py` | 单元测试 |

---

## 3. voices.json（权威映射）

```text
example_voice → G_27200.pth + config1.json（示例歌手）
example_voice_b   → G_16000.pth + configcos.json（ExampleVoiceB）
```

别名示例：`G_27200` / `示例歌手` / `ExampleVoice` → example_voice；`G_16000` → example_voice_b。

---

## 4. 调用链（本阶段）

```text
voice_id
  → VoiceRegistry.resolve()
  → VoiceAsset (checkpoint + config)
  → build_cover_request_for_voice() → CoverRequest.model_name = stem
  → Skill monkeypatch SVC path helpers（进程内）
  → CoverService.submit() → … → Pipeline（未改）
```

---

## 5. 明确未做

- GUI 下拉改 display_name  
- PipelineAdapter / SVC 源码内嵌 Registry  
- 去掉 Skill 层 path patch（需后续批准改 Adapter/SVC）  

---

## 6. 回滚

1. 恢复 Skill 内硬编码表（或回退 `aivoice_cover.py`）  
2. 删除/忽略 `config/voices.json` 与 `cover/voice_registry.py`  
3. Pipeline/GUI 无需回滚（未改）

---

## 7. 阶段结束

v1.1-3A Voice Registry **实现完成**。
