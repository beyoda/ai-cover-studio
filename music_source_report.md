# Music Source Integration Report

> Phase: **AIVOICE v1.1-4**  
> Date: 2026-07-26  
> Scope: MusicSource 抽象 + Local / GDStudio 安全适配 + Skill 解析；**未**改 Pipeline / SVC / UVR / GUI / CoverService 执行核

---

## 1. 目标与约束

| 项 | 结果 |
|----|------|
| 不再只接受本地路径 | ✅ Skill / 解析层可走 `MusicSource` → `AudioAsset.path` → `CoverRequest.input_audio` |
| 禁止改 Pipeline / SVC / UVR / GUI / CoverService 核心 | ✅ 未触及 |
| 禁止 Telegram / Worker / GPU | ✅ 未做 |
| GDStudio：不绕过限制、不模拟登录、不破解 | ✅ 仅公开直链下载；歌名明确失败 |

---

## 2. 架构

```text
MusicSource.resolve(query)
        ↓
    AudioAsset { path, title, source, metadata }
        ↓
CoverRequest.input_audio = path
        ↓
CoverService / Pipeline（不感知来源）
```

| 实现 | 路径 | 说明 |
|------|------|------|
| `MusicSource` Protocol | `src/aivoice_studio/cover/music_source/base.py` | `resolve(query) → AudioAsset` |
| `AudioAsset` / `MusicSourceError` | `.../types.py` | DTO + 失败类型 |
| `LocalFileSource` | `.../local.py` | 本地路径 → Asset |
| `GDStudioSource` | `.../gdstudio.py` | 安全适配：仅 http(s) 直链音频 |
| `resolve_to_audio_asset` | `.../resolve.py` | Skill/API 统一入口（`input` / `source` / `provider`） |

未来可插：网易云 / YouTube Source，同样只产出本地 `AudioAsset`。

---

## 3. 任务完成情况

### 任务1：MusicSource 接口

- `resolve(query: str) -> AudioAsset`
- Asset 字段：`path` / `title` / `source` / `metadata`

### 任务2：LocalFileSource

- 支持如 `D:\music\song.mp3`
- 缺失文件 / 非法后缀 → `MusicSourceError`（明确失败）

### 任务3：GDStudioSource（安全下载适配）

| 输入 | 行为 |
|------|------|
| 公开直链（带音频后缀的 http/https URL） | 下载到 `workdir/music_source/gdstudio/{hash}/` → Asset |
| 纯歌名 / 无许可 URL | **明确失败**（不搜索、不登录、不刮页） |
| HTTP 错误 | 失败文案注明未尝试 auth bypass |

### 任务4：Skill 升级

| 项 | 变更 |
|----|------|
| `param_parse.parse_source_and_voice` | 「用示例歌手声音翻唱晴天」→ `{source:"晴天", voice_id:"example_voice"}` |
| `extract_cover_params_from_utterances` | 输出 `source` / `source_query` + `voice_id` |
| `aivoice_cover.py` | 解析前调用 `resolve_to_audio_asset`；保留 `input` 旧路径 |
| `SKILL.md` | v1.1.4-music-source；NL 与 Music Source JSON 说明 |

### 任务5：验证

`tests/test_music_source.py`：

1. 本地文件解析  
2. source 失败（歌名 / GDStudio / 缺失路径）  
3. `voice_id` + `source` 组合（NL + `build_cover_request_for_voice`）  
4. 旧 `input` 路径调用保持  

---

## 4. 测试结果

```text
tests/test_music_source.py  → 4 passed
full suite                   → 54 passed
```

---

## 5. 刻意未做

- 歌名自动搜索下载  
- Hermes 自然语言整条链路到 Telegram  
- Worker / GPU / Pipeline 内嵌下载  
- 网易云 / YouTube Source 实现  

---

## 6. 使用示例

**旧路径（仍可用）：**

```json
{ "input": "D:\\music\\song.mp3", "voice_id": "example_voice" }
```

**NL 解析目标：**

```json
{ "source": "晴天", "voice_id": "example_voice" }
```

当前阶段：`source="晴天"` 会失败并返回清晰错误；需本地路径或 `provider=gdstudio` + 公开直链。
