# Voice Asset Registry Design

> Phase: AIVOICE v1.1-1（**只设计，不改代码**）  
> Date: 2026-07-26  
> 前置：`aivoice_model_audit.md`（v1.1-0）  
> 目标：将「checkpoint 文件名管理」升级为「音色资产管理（Voice Asset）」

---

## 1. 设计目标与非目标

### 目标

| 目标 | 说明 |
|------|------|
| 产品入口统一为音色 | 调用方使用 `voice_id` / `speaker`（如 `example_voice`），而非裸 `G_27200` |
| 一音色一资产 | 每个 Voice Asset 绑定 **独立** `checkpoint + config` |
| 兼容现网 | 保留 `model_name`；GUI / Pipeline 在迁移期可继续运行 |
| 可枚举 | Registry 可列出可用音色供 GUI / Hermes |

### 非目标（本设计明确不做）

- **不是**「单 checkpoint + 多 `spk`」切换架构  
- **不以** `config.json` 内 `spk` 字段作为主切换入口  
- 不改 UVR / Mixer / 推理命令模板语义  
- 本阶段不实现代码、不搬迁 `.pth` 文件

### 核心映射

```text
speaker / voice_id
        ↓
   Voice Registry
        ↓
   Voice Asset
        ↓
 checkpoint (.pth)  +  config (.json)
```

示例（当前资产，见 §3）：

```text
example_voice  →  G_27200.pth + config1.json
example_voice_b    →  G_16000.pth + config_example.json
```

---

## 2. Voice Asset 数据结构

### 2.1 逻辑实体：`VoiceAsset`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `voice_id` | string | 是 | 稳定 ID；小写 slug；API / Hermes / 内部主键（如 `example_voice`、`example_voice_b`） |
| `display_name` | string | 是 | GUI 展示名（如 `示例歌手`、`ExampleVoiceB`） |
| `checkpoint` | string | 是 | 相对 `models_dir` 的文件名，或绝对路径（如 `G_27200.pth`） |
| `config` | string | 是 | 相对 `models_dir` 的配置文件名（如 `config1.json`） |
| `enabled` | bool | 否 | 默认 `true`；禁用后不出现在列表 |
| `tags` | string[] | 否 | 可选标签（`male` / `cantonese` 等） |
| `default_pitch` | int | 否 | GUI 可选默认音高提示 |
| `inference_speaker` | string \| null | 否 | 传给 so-vits `-s` 的值；**不是**音色切换主键，仅为该资产配套推理参数 |
| `aliases` | string[] | 否 | 兼容旧名：`G_27200`、`示例歌手` 等可解析到本 `voice_id` |
| `notes` | string | 否 | 运维备注 |

说明：

- **切换音色 = 换整套 Asset（checkpoint + config）**，不是改 `spk` map。  
- `inference_speaker` 仅满足现有 CLI `-s` 要求；若缺省，实现期可从该资产 `config` 的 `spk` **只读取第一个 key** 作为默认，但仍不把 `spk` 当作 Registry 切换面。

### 2.2 逻辑实体：`VoiceRegistry`

| 职责 | 说明 |
|------|------|
| `get(voice_id) → VoiceAsset` | 精确查找；找不到则错误 |
| `resolve(ref) → VoiceAsset` | 接受 `voice_id` / alias / 旧 `model_name` |
| `list() → VoiceAsset[]` | 仅 `enabled=true` |
| `resolve_paths(asset) → (ckpt_path, cfg_path)` | 相对 `svc.models_dir` 拼绝对路径并校验存在 |

建议放置（实现期）：

- 数据文件：`config/voices.json`（或 `config/voices/voices.json`）  
- 加载器：`aivoice_studio.modules.svc.voice_registry.VoiceRegistry`（设计名）

### 2.3 与现有对象关系

```text
VoiceAsset.checkpoint  ──►  取代「仅靠 model_name + 启发式找 config」
VoiceAsset.config      ──►  取代 ModelManager 对 config1.json 的全局偏好
model_name (旧)        ──►  alias / 兼容字段，解析进 VoiceAsset
```

Pipeline 最终仍需要本地路径；Registry 只负责 **解析**，不常驻加载权重。

---

## 3. 当前模型资产（权威清单）

> 产品确认：两个**独立** SVC Voice Asset（非单模多 speaker）。

| voice_id | display_name | checkpoint | config |
|----------|--------------|------------|--------|
| `example_voice_b` | ExampleVoiceB | `G_16000.pth` | `config_example.json` |
| `example_voice` | 示例歌手 | `G_27200.pth` | `config1.json` |

资产根目录（与现网一致）：

```text
C:\path\to\repo\tools\so-vits-svc\logs\44k\
```

注意（相对 v1.1-0 审计）：

- 审计曾观察到「无精确 `{model}.json` 时优先 `config1.json`」——这会把 `G_16000` 错绑到错误 config。  
- Registry 落地后，**以本表配对为准**，禁止再用「扫目录猜 config」作为主路径。

---

## 4. `voices.json` 格式

### 4.1 建议 Schema

```json
{
  "version": 1,
  "models_dir": "C:\\path\\to\\repo\\tools\\so-vits-svc\\logs\\44k",
  "default_voice_id": "example_voice",
  "voices": [
    {
      "voice_id": "example_voice_b",
      "display_name": "ExampleVoiceB",
      "checkpoint": "G_16000.pth",
      "config": "config_example.json",
      "enabled": true,
      "aliases": ["G_16000", "example_voice_b"],
      "inference_speaker": null,
      "tags": [],
      "notes": "Independent voice asset; checkpoint G_16000 + config_example"
    },
    {
      "voice_id": "example_voice",
      "display_name": "示例歌手",
      "checkpoint": "G_27200.pth",
      "config": "config1.json",
      "enabled": true,
      "aliases": ["G_27200", "example_voice", "示例歌手"],
      "inference_speaker": null,
      "tags": [],
      "notes": "Independent voice asset; checkpoint G_27200 + config1"
    }
  ]
}
```

### 4.2 校验规则（实现期）

1. `voice_id` 全局唯一、非空、建议 `[a-z0-9_]+`。  
2. 每个 `checkpoint` / `config` 在 `models_dir` 下存在（或绝对路径存在）。  
3. `aliases` 全局唯一（不可两个 voice 争抢同一 alias）。  
4. `default_voice_id` 必须指向已启用 voice。  
5. **禁止**仅凭 `config.spk` 自动生成多个 VoiceAsset（与本架构冲突）。

### 4.3 `models_dir` 解析

- 优先 `voices.json.models_dir`  
- 否则回退 `config/svc.yaml` → `svc.models_dir`  
- 相对路径相对项目根解析

---

## 5. `model_name` 兼容方案

### 5.1 原则

**迁移期双写、单解析：**

| 调用方输入 | Registry 行为 |
|------------|----------------|
| `voice_id=example_voice` / `speaker=example_voice` | 直接 `get("example_voice")` |
| `model_name=G_27200` | `resolve("G_27200")` → alias → `example_voice` |
| `model_name=G_16000` | → `example_voice_b` |
| 同时传 `speaker` + `model_name` | **`speaker` / `voice_id` 优先**；`model_name` 仅作审计/回退 |
| 只传未知 `model_name` | 兼容模式：若 `{name}.pth` 存在则合成临时 Asset（config 仍建议强制 Registry；严格模式可直接报错） |

### 5.2 推荐兼容策略（默认）

```text
ref = speaker or voice_id or model_name
asset = registry.resolve(ref)
paths = registry.resolve_paths(asset)
# SVC 使用 asset.checkpoint + asset.config
# CoverResult / 历史记录可同时写下：
#   voice_id, display_name, model_name(=checkpoint stem)
```

### 5.3 `model_name` 字段语义演进

| 阶段 | `model_name` 含义 |
|------|-------------------|
| v1.0 | checkpoint stem（`G_16000`） |
| v1.1 迁移期 | 仍可传入；内部解析为 VoiceAsset |
| v1.1+ 稳定期 | 可选废弃为「只读镜像」=`Path(checkpoint).stem`；对外主推 `speaker`/`voice_id` |

**不删除** `model_name` 字段，避免 GUI / 旧 Skill / 测试瞬间全挂。

---

## 6. `CoverRequest` 变化方案

### 6.1 建议字段（加法，不破坏）

```text
CoverRequest:
  input_audio: str
  model_name: str | None = None      # 兼容；可空（当 speaker 有值）
  speaker: str | None = None         # 推荐：= voice_id（如 example_voice / example_voice_b）
  # 可选别名（二选一实现，勿三者并存混淆）：
  # voice_id: str | None = None      # 若引入，与 speaker 同义，文档只保留一个主名

  pitch, reverb, f0_method, ...      # 不变
```

### 6.2 校验（Adapter 入口）

```text
if not speaker and not model_name:
    error "speaker or model_name required"
asset = registry.resolve(speaker or model_name)
# 规范化写入下游：
#   job.model_name = checkpoint_stem   # 保持 Pipeline 现有字段
#   job.voice_id = asset.voice_id      # 新增（可选，见迁移计划）
#   job.svc_config_path / skip 启发式
```

### 6.3 Pipeline `JobContext`

最小侵入选项：

| 选项 | 做法 | 优点 |
|------|------|------|
| **A（推荐）** | Adapter 解析 Registry 后，仍只填现有 `model_name=stem`，并扩展 SVC 层按 registry 取 config | Pipeline 签名几乎不动 |
| **B** | `JobContext` 增加 `voice_id`、`svc_checkpoint`、`svc_config` | 更清晰；改动略大 |

设计推荐：**Adapter / SVC 边界消化 Registry**；Pipeline 业务步骤不变。若需可观测性，再加法加 `voice_id`。

### 6.4 `CoverResult`

建议追加只读字段（可选）：

- `voice_id`  
- `display_name`  
- 保留 `model_name`（checkpoint stem 或解析后的兼容值）

---

## 7. GUI 兼容方案

### 7.1 现状

- 下拉数据：`ModelConfigMap.list_models()` → `*.pth` stems（`G_16000` / `G_27200`）  
- 提交：`model_name = combo.currentText()`

### 7.2 目标 UX

| 显示 | 内部值 |
|------|--------|
| `示例歌手` | `voice_id=example_voice` |
| `ExampleVoiceB` | `voice_id=example_voice_b` |

### 7.3 兼容步骤（不打断可运行性）

1. **阶段 1（无感）**  
   - 仍显示 `G_*`；后台用 Registry 把 `G_27200`→`example_voice` 配对正确 config。  
   - GUI 代码几乎不动，只换「选模型后解析」路径。

2. **阶段 2（推荐）**  
   - Combo 改为 `display_name`，`userData`/`隐藏值` 存 `voice_id`。  
   - `CoverRequest(speaker=voice_id, model_name=None 或 stem)`。

3. **默认音色**  
   - 用 `voices.json.default_voice_id`（建议 `example_voice`）替代仅 `svc.default_model: G_16000`。  
   - 迁移期：`default_model` 可继续作为 alias 回退。

### 7.4 约束

- 迁移全程：**生成翻唱按钮路径保持可用**。  
- 不一次删除 `ModelConfigMap`；可先让 Registry 优先，扫盘作 fallback（或严格模式关闭 fallback）。

---

## 8. Hermes 调用方案

### 8.1 推荐参数（Skill 演进）

| 参数 | 必填 | 说明 |
|------|------|------|
| `input_audio` | 是 | 不变 |
| `speaker` | 推荐 | `example_voice` / `example_voice_b`（= `voice_id`） |
| `model_name` | 兼容 | 旧 Agent 仍可传 `G_27200`；服务端 resolve |
| 其余 | 同现网 | pitch / reverb / … |

示例：

```json
{
  "input_audio": "C:\\path\\to\\songs\\demo.mp3",
  "speaker": "example_voice",
  "pitch": 0,
  "client": "hermes"
}
```

等价兼容：

```json
{
  "input_audio": "C:\\path\\to\\songs\\demo.mp3",
  "model_name": "G_27200",
  "client": "hermes"
}
```

### 8.2 新工具面

| Operation | 语义 |
|-----------|------|
| `aivoice.cover.voices` | 列出 `voice_id` / `display_name` / enabled（取代或并存 `aivoice.cover.models`） |
| `aivoice.cover.models` | **兼容**：返回 checkpoint stems 或映射表；文档标注 deprecated |

### 8.3 异步 Job

`submit` / `status` / `result` 不变；请求体使用升级后的 `CoverRequest`。  
Job 快照应保存解析后的 `voice_id` + checkpoint/config 路径，便于审计。

---

## 9. SVC 运行时解析（概念）

```text
CoverRequest(speaker="example_voice")
    → VoiceRegistry.resolve("example_voice")
    → VoiceAsset(
         checkpoint=G_27200.pth,
         config=config1.json
       )
    → abs paths under models_dir
    → so-vits:
         -m <G_27200.pth>
         -c <config1.json>
         -s <inference_speaker or first spk key in that config>
```

**禁止：**

```text
speaker=example_voice  →  只改 -s example_voice，却仍用错误的 .pth/.json
```

音色切换必须同时切换 **checkpoint + config**。

---

## 10. 设计决策摘要

| 决策 | 选择 |
|------|------|
| 切换粒度 | Voice Asset = checkpoint + config |
| 主键 | `voice_id`（对外可称 `speaker`） |
| `spk` 字段 | 不作为 Registry 主入口；最多提供 `-s` 默认值 |
| 旧 `model_name` | 保留并作 alias |
| 当前资产 | `example_voice_b`↔G_16000+config_example；`example_voice`↔G_27200+config1 |
| Pipeline | 尽量不变；解析发生在 Adapter / SVC 边界 |

---

## 11. 本阶段结束

本文档为 **v1.1-1 设计**；**不修改代码**。  
迁移步骤见同目录（仓库根）`migration_plan.md`。
