# Voice Registry Integration Report（v1.1-3B）

> Date: 2026-07-26  
> Goal: Voice Registry 成为 AIVOICE **对外统一音色入口**  
> 禁止项遵守：未改 Pipeline / GUI / SVC 推理源码 / UVR / 模型文件；未接 Telegram / Worker

---

## 1. 结论

**PASS。**  

```text
Skill → voice_id → Voice Registry → VoiceAsset
      → model_path + config_path（经 SVCConfig 字段注入）
      → CoverRequest → PipelineAdapter → Pipeline
```

`model_name` 仍兼容；`voice_id` 优先。Hermes 可通过 `--list-voices` 从 Registry 查询音色（禁止写死）。

**pytest：50 passed**

---

## 2. 任务完成情况

| 任务 | 状态 |
|------|------|
| 1. Registry / voices.json 正式化 | ✅ `display_name` + `metadata` + checkpoint/config |
| 2. API：`get_voice` / `list_voices` / `validate_voice` | ✅ 未知音色 → `unknown voice` |
| 3. Skill 去硬编码，只出 `voice_id` | ✅ |
| 4. CoverRequest `voice_id` + 可选 `model_name` | ✅ Adapter 解析 |
| 5. Hermes 查询「有哪些声音」 | ✅ `--list-voices` + SKILL.md |
| 集成测试 | ✅ `tests/test_voice_registry_integration.py` |

---

## 3. 关键架构

```text
CoverRequest(voice_id=...) 优先
CoverRequest(model_name=G_27200) 兼容 → Registry alias → example_voice 资产

PipelineAdapter:
  resolve_request_voice()
  pipeline.svc.config.model_path = <ckpt abs>
  pipeline.svc.config.config_path = <cfg abs>
  JobContext.model_name = stem
  Pipeline.run(...)   # 未改
```

路径注入使用 **既有** `SVCConfig.model_path` / `config_path`，不改 SVC 推理函数体。

---

## 4. 资产表（`config/voices.json` v2）

| voice_id | display_name | checkpoint | config | metadata |
|----------|--------------|------------|--------|----------|
| example_voice | 示例歌手 | G_27200.pth | config1.json | zh / pop |
| example_voice_b | ExampleVoiceB | G_16000.pth | configcos.json | zh / pop |

`models_dir`: `tools/so-vits-svc/logs/44k`（相对项目根；**未搬迁**模型文件）。

---

## 5. 主要改动文件

- `config/voices.json`
- `src/aivoice_studio/cover/voice_registry.py`
- `src/aivoice_studio/cover/voice_resolve.py`
- `src/aivoice_studio/cover/voice_request.py`
- `src/aivoice_studio/cover/domain/request.py`
- `src/aivoice_studio/cover/adapter/pipeline_adapter.py`
- `hermes_skill/media/aivoice-cover/SKILL.md`
- `hermes_skill/media/aivoice-cover/scripts/aivoice_cover.py`（`--list-voices`）
- `tests/test_voice_registry.py`
- `tests/test_voice_registry_integration.py`

---

## 6. 测试覆盖

1. example_voice → 正确 G_27200.pth + config1.json  
2. example_voice_b → 正确 G_16000.pth + configcos.json  
3. unknown voice  
4. Hermes Skill `--list-voices` 读 Registry  
5. 旧 `model_name=G_27200` 仍解析到 example_voice 资产  
6. Adapter 绑定 Registry 路径；`voice_id` 优先于冲突的 `model_name`

---

## 7. 阶段结束

v1.1-3B **完成并停止。** 等待下一阶段指令。
