# Hermes Skill Prototype Report（v1.1-2 Phase 2）

> Date: 2026-07-26  
> Goal: 第一次 Hermes → AIVOICE 翻唱闭环（原型）  
> Constraints: **未改** Pipeline / GUI / CoverService 核心 / CoverRequest / SVC 源码参数

---

## 1. 结论

| 检查项 | 结果 |
|--------|------|
| Skill 目录落盘 | ✅ `<repo-root>\hermes_skill\media\aivoice-cover\` |
| Hermes `external_dirs` | ✅ `config.yaml` → `<repo-root>/hermes_skill` |
| Hermes 能发现 Skill | ✅ `hermes skills list` 显示 `aivoice-cover`（media / local / enabled） |
| Skill 脚本独立运行 | ✅ |
| 真实翻唱 `voice_id=example_voice` | ✅ `completed` |
| 输出 MP3 可探测 | ✅ ffprobe：`format_name=mp3`，`duration≈217.6s`，`bit_rate≈320k` |
| GUI 回归（现有测试） | ✅ `test_gui_cover_entry` 等在全量套件内通过 |
| 全部测试 | ✅ **35 passed** |
| 未改 AIVOICE 核心代码 | ✅ 仅 Skill 旁路 + Hermes 配置 |

---

## 2. 交付物

```text
<repo-root>\hermes_skill\media\aivoice-cover\
  SKILL.md
  scripts\
    aivoice_cover.py
    _request_eason_chun.json   # 本次验证请求样例
```

Hermes 配置（本机，非 AIVOICE 源码）：

```yaml
# <user>\AppData\Local\hermes\config.yaml
skills:
  creation_nudge_interval: 15
  external_dirs:
    - <repo-root>/hermes_skill
```

**未**写入 Hermes bundled skills。

---

## 3. Skill 行为摘要

### 3.1 `SKILL.md`

- 能力：本地 AIVOICE 翻唱  
- 触发：翻唱 / AI cover / 换声；音色 example_voice / example_voice_b  
- 入参：`input` / `voice_id` / `pitch` / `options`  
- 强调单进程脚本，禁止拆 submit/status 多进程  

### 3.2 `aivoice_cover.py`（Skill 层映射）

| voice_id | model_name（CoverRequest） | checkpoint | config |
|----------|----------------------------|------------|--------|
| `example_voice` | `G_27200` | `G_27200.pth` | `config1.json` |
| `example_voice_b` | `G_16000` | `G_16000.pth` | `configcos.json` |

实现方式：

1. 组装现有 `CoverRequest(model_name=...)`  
2. **进程内** monkeypatch `SVCService._configured_model_path` / `_configured_config_path`（仅 Skill 脚本，不改仓库源码）  
3. `CoverService.submit()` → 同进程 `status()` 轮询 → `result()`  
4. stdout 单行 JSON：`{status, job_id, output_path, error}`  

---

## 4. 真实验证（示例曲目.mp3 / example_voice）

### 命令

```text
<repo-root>\.venv\Scripts\python.exe ^
  hermes_skill\media\aivoice-cover\scripts\aivoice_cover.py ^
  --json-file hermes_skill\media\aivoice-cover\scripts\_request_eason_chun.json
```

### 结果

```json
{
  "status": "completed",
  "job_id": "95a9c766ce1b",
  "output_path": "<repo-root>\\outputs\\95a9c766ce1b\\cover.mp3",
  "error": null
}
```

### 运行证据

| 项 | 值 |
|----|-----|
| voice 解析 | `example_voice` → `G_27200.pth` + `config1.json` |
| SVC 命令 | `-m ...\G_27200.pth -c ...\config1.json` |
| UVR | cache hit（跳过分离，墙钟约 **37s**） |
| 产物 | `outputs\95a9c766ce1b\cover.mp3`（约 8.7 MB） |
| ffprobe | mp3 / ~217.6 s / ~320 kbps |

---

## 5. 回归

```text
pytest tests -q
35 passed
```

含 GUI cover entry 契约测试；未改 GUI / Pipeline / CoverService 源码。

---

## 6. 已知限制（原型）

| 限制 | 说明 |
|------|------|
| JobStore 仍进程内 | 已用单脚本保持生命周期；跨进程轮询仍不可行 |
| voice 映射在 Skill | Registry 未落地；后续应迁入 AIVOICE Registry |
| `hermes skills inspect` | 对本 Skill 报 “not found in any source”；**list 已可见**（hub inspect 路径差异，不影响 slash/`skills_list`） |
| 非交互 Hermes chat 全链路 | 本阶段以「发现 + 脚本闭环」验证；完整 `/aivoice-cover` 对话冒烟可作下一阶段 |

---

## 7. 回滚

1. 从 `config.yaml` 删除 `skills.external_dirs` 条目  
2. 删除或移走 `<repo-root>\hermes_skill\media\aivoice-cover\`  
3. AIVOICE 业务代码无需回滚（未改）

---

## 8. 阶段结束

v1.1-2 Phase 2 原型闭环完成。**停止。**
