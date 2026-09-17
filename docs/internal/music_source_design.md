# Music Source Design

> Phase: AIVOICE v1.1-2.5（**只设计，不实现**）  
> Date: 2026-07-26  
> 目的：为未来「说歌名 → 拉音频 → 翻唱」预留抽象，而不把下载逻辑塞进 Pipeline

---

## 1. 当前输入方式

| 项 | 现状 |
|----|------|
| 唯一入口 | 本机绝对路径字符串 |
| CoverRequest | `input_audio: str` |
| Hermes Skill | JSON 字段 `input` → 路径 |
| 示例 | `C:\path\to\test_songs\<song>.mp3` |

Hermes / GUI / Job API 均假设音频**已经在磁盘上**。

---

## 2. 未来来源抽象：`MusicSource`

```json
{
  "type": "local",
  "path": "C:\\path\\to\\songs\\xxx.mp3"
}
```

未来扩展：

```json
{
  "type": "url",
  "provider": "gdstudio",
  "query": "示例歌手 示例曲目",
  "url": "https://...",
  "track_id": "..."
}
```

可选字段：`title` / `artist` / `prefer_quality`。

### 解析流水线（Skill 或独立模块，**不进 Pipeline**）

```text
用户意图 / MusicSource
        ↓
  MusicSourceResolver
        ↓
  Downloader（按 provider）
        ↓
  Temporary Audio File（workdir/downloads/...）
        ↓
  CoverService.submit(CoverRequest.input_audio = temp path)
        ↓
  Pipeline（UVR → SVC → Export）  ← 不感知来源
```

**硬规则：** GDStudio / 任意下载器 **不得** import 或修改 UVR / SVC / Export / Pipeline。

---

## 3. GDStudio 适配方案（草案）

| 步骤 | 说明 |
|------|------|
| 1. 搜索 | Hermes 收集歌名 → `provider=gdstudio` 搜索 API / 页面 |
| 2. 选型 | 用户确认曲目或自动取第一条 |
| 3. 下载 | Downloader 写到 `workdir/music_source/{hash}/source.mp3` |
| 4. 校验 | 后缀、大小、可读；失败则 Skill 返回友好错误 |
| 5. 翻唱 | 仅把本地 path 交给现有 `aivoice_cover.py` / CoverService |
| 6. 清理 | 可选 TTL 删除临时文件（与 UVR cache 分离） |

配置建议（未来）：`config/music_sources.yaml`（endpoint、超时、缓存目录）— **不属于** `svc.yaml` / Pipeline。

---

## 4. 与 Hermes 结合方式

```text
用户：「帮我翻唱某某歌曲」
  → Skill：若无本地路径，进入 MusicSource 流程（未来）
  → 或当前 Beta：要求用户提供本机路径

用户已有路径：
  → 直接 MusicSource {type:local} → Cover
```

Skill 参数演进（未来）：

```json
{
  "source": { "type": "local", "path": "..." },
  "voice_id": "example_voice",
  "pitch": 0,
  "options": {}
}
```

兼容：继续接受顶层 `input` 作为 `source.type=local` 的简写。

---

## 5. 风险

| 风险 | 说明 | 缓解 |
|------|------|------|
| 版权 / ToS | 第三方下载合规 | 用户自担；文档声明；可开关 provider |
| 网络失败 | 超时、地区限制 | 重试 + 友好错误；不进入 Pipeline |
| 音质不一 | 影响 UVR/SVC | 记录 source meta；必要时提示 |
| 变量膨胀 | 与 Skill 稳定性耦合 | **本阶段故意不实现**；等 Beta 过后再做 v1.1-3 |
| 绕过抽象 | 下载逻辑渗入 Pipeline | Code review 闸门：Pipeline 只收 Path |

---

## 6. 非目标（本设计）

- 不实现 GDStudio 客户端  
- 不改 UVR / SVC / Export  
- 不改 CoverService 核心  

---

## 7. 建议落地阶段

**v1.1-3：** Music Source Layer + Voice Registry（在 Skill Beta 稳定之后）。

---

## 8. 本阶段状态

设计文档完成；**零实现**。
