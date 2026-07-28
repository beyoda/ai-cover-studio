# Hermes Skill Integration Review（v1.1-2 第一阶段）

> Phase: AIVOICE v1.1-2 — **只读审查 + Skill 设计**  
> Date: 2026-07-26  
> 约束：本阶段 **不修改 AIVOICE 代码**；**不修改 Pipeline**  
> 本机 Hermes：`hermes_home = ~/AppData/Local/hermes`（即 `<user>\AppData\Local\hermes`）

---

## 1. 结论摘要

| 项 | 结论 |
|----|------|
| Hermes Skill 本质 | **过程文档（SKILL.md）+ 渐进披露**，不是独立 RPC 服务 manifest |
| 「Manifest」形态 | YAML frontmatter（`name` / `description` / …），兼容 [agentskills.io](https://agentskills.io) |
| 调用方式 | `/aivoice-cover` 斜杠命令、自然语言触发、或 `skills_list` → `skill_view` |
| 参数如何进业务 | Agent 读 Skill 后，用 **terminal / code_execution** 跑 Skill 自带 `scripts/`（或后续本地 HTTP） |
| AIVOICE 推荐路径 | Skill → 薄封装脚本 → **`CoverService.submit()`** → 返回 `{job_id, status}` |
| 最大风险 | JobStore **进程内内存**：跨进程二次 `status(job_id)` 会丢任务，需同进程轮询或常驻服务 |

---

## 2. 当前 Hermes 机制（本机实测）

### 2.1 安装结构

| 路径 | 角色 |
|------|------|
| `<user>\AppData\Local\hermes\` | **HERMES_HOME**（`hermes dump` 确认） |
| `...\hermes\skills\` | Skill **主目录 / 真源**（bundled 种子 + hub + 用户创建） |
| `...\hermes\hermes-agent\` | Agent 源码 / CLI（本机亦有 `D:\AI\hermes\hermes-agent` 镜像树） |
| `D:\AI\hermes\skills\` | 开发/镜像 skills 树（与 bundled 对应） |
| `hermes.exe` | `...\hermes-agent\venv\Scripts\hermes.exe` |

`config.yaml` 中已有 `skills:` 段（当前未见 `external_dirs`）；已安装技能约 **78** 个。

技能目录示例：

```text
%HERMES_HOME%/skills/
  media/heartmula/SKILL.md
  media/songsee/SKILL.md
  media/gif-search/SKILL.md
  yuanbao/SKILL.md
  software-development/hermes-agent-skill-authoring/SKILL.md
  .bundled_manifest
  .hub/
```

### 2.2 Skill「Manifest」格式（实际是 Frontmatter）

Hermes **没有**单独的 `manifest.json` 作为 Skill 契约主格式。权威格式是 **`SKILL.md` 顶部 YAML**：

```yaml
---
name: aivoice-cover                 # ≤64，小写+连字符
description: Use when ...           # ≤1024；触发条件
version: 1.0.0
author: ...
license: MIT
platforms: [windows]                # 可选；省略=全平台
metadata:
  hermes:
    tags: [aivoice, cover, svc]
    related_skills: []
    category: media                 # 可选
    requires_toolsets: [terminal]   # 可选
---
```

校验来源：`tools/skill_manager_tool.py`（authoring skill 文档引用）。

配套目录（可选）：

```text
aivoice-cover/
  SKILL.md              # 必需
  scripts/              # Agent 可执行的辅助脚本（推荐放 submit 封装）
  references/           # 长文档 / API 表
  templates/ | assets/
```

`.bundled_manifest` 仅跟踪 **bundled 种子哈希**，不是调用契约。

### 2.3 加载与调用方式

```text
Level 0  skills_list()     → name + description（索引，省 token）
Level 1  skill_view(name)  → 完整 SKILL.md
Level 2  skill_view(name, "scripts/...") → 附属文件
```

用户侧：

| 方式 | 行为 |
|------|------|
| `/aivoice-cover ...` | 斜杠命令加载 Skill，余下为指令 |
| 自然语言 | Agent 根据 description 自行 `skill_view` |
| `hermes skills list/install/...` | CLI 管理安装与启用 |

**重要：** Skill 本身 **不注册** 名为 `aivoice.cover.submit` 的原生 Tool。  
Agent 按 SKILL.md **过程**调用已有工具（`terminal`、`code_execution` 等）。  
对比：`yuanbao` Skill 依赖 **另行注册** 的 `yb_*` tools——那是插件/工具层，不是纯 SKILL.md。

### 2.4 参数传递方式

| 层 | 如何传参 |
|----|----------|
| 用户 → Hermes | 自然语言或斜杠后的自由文本 |
| Hermes → Skill | 无强类型绑定；模型按 SKILL 说明抽取字段 |
| Skill → AIVOICE | **约定**：调用 `scripts/` 或 HTTP，传入 JSON/CLI flags |

因此 AIVOICE 侧必须提供 **稳定、可脚本化的入口**（推荐 `scripts/submit.py` 读 JSON stdin / `--json`），避免 Agent 手写一长串 `python -c`。

### 2.5 外部 Skill 目录（可选放置策略）

`config.yaml`：

```yaml
skills:
  external_dirs:
    - <repo-root>/hermes_skill
```

- 与 `%HERMES_HOME%/skills` 一并扫描  
- 同名时 **本地 HERMES_HOME 优先**  
- 外部目录可写时，agent 的 `skill_manage` 也可能改文件  

---

## 3. AIVOICE Skill 设计（本阶段仅设计）

### 3.1 目标调用链

```text
Hermes Agent
    │  skill_view("aivoice-cover")
    ▼
AIVOICE Skill（SKILL.md + scripts/）
    │  terminal / code_execution
    ▼
薄封装（不改 Pipeline）
    │  CoverRequest 组装
    ▼
CoverService.submit(request)   # 已有 P4 API
    │
    ▼
返回 { job_id, status }
```

后续（同 Skill 过程，非本审查实现）：

```text
CoverService.status(job_id)  → 轮询至 completed/failed
CoverService.result(job_id)  → mp3_path / error
```

### 3.2 Skill 放置位置（推荐）

| 方案 | 路径 | 适用 |
|------|------|------|
| **A. 用户本地（默认推荐）** | `%HERMES_HOME%/skills/media/aivoice-cover/` | 最快接入本机 Hermes；不碰 AIVOICE 包代码 |
| **B. 仓库旁路 + external_dirs** | `<repo-root>\hermes_skill\media\aivoice-cover\` | Skill 与 AIVOICE 版本同仓演进；Hermes 只读挂载 |
| **C. 打进 hermes-agent bundled** | `hermes-agent/skills/media/...` | 需改 Hermes 仓库；**非本阶段** |

分类：放在 **`media/`**（与 `heartmula` / `songsee` 同类）。

> 本阶段 **不创建** 上述目录、**不改** AIVOICE；仅锁定位置与契约。

### 3.3 对外参数（Hermes / Skill 契约）

Agent 抽取后交给脚本的 JSON：

```json
{
  "input": "<repo-root>\\test_songs\\示例歌手 - 示例曲目.mp3",
  "voice_id": "example_voice",
  "pitch": 0,
  "options": {
    "reverb": "关闭",
    "export_mp3": true,
    "f0_method": "rmvpe",
    "accompaniment": "",
    "request_id": null
  }
}
```

| 字段 | 必填 | 映射到现网 |
|------|------|------------|
| `input` | 是 | `CoverRequest.input_audio` |
| `voice_id` | 是 | 目标语义；**Registry 未落地前** Skill/脚本用别名表 → `model_name`（见下） |
| `pitch` | 否 | `CoverRequest.pitch`（默认 0） |
| `options.*` | 否 | `reverb` / `export_mp3` / `f0_method` / `accompaniment` / … |
| （隐式） | — | `client="hermes"` |

**临时 `voice_id` → `model_name`（与 v1.1-1 资产表一致，待 Registry 实现后删除硬表）：**

| voice_id | model_name（兼容字段） |
|----------|------------------------|
| `example_voice` | `G_27200` |
| `example_voice_b` | `G_16000` |

> 注意：仅填 `model_name` **不能**保证正确 config 配对（审计结论）；真正正确配对依赖后续 Voice Registry。Skill 设计已预留 `voice_id`；实现期应尽快接 Registry，避免 Agent 长期依赖错误启发式。

### 3.4 返回值（submit 瞬间）

```json
{
  "job_id": "b7b3ef418107",
  "status": "queued"
}
```

或已开始执行时：

```json
{
  "job_id": "b7b3ef418107",
  "status": "running"
}
```

与现网 API 对齐方式：

```text
job_id = CoverService.submit(request)     # → str
view   = CoverService.status(job_id)      # 立即再查一次
return { "job_id": job_id, "status": view.status.value }
```

`CoverService.submit` **只返回** `str`；`{job_id,status}` 由 **Skill 脚本包装**，无需改 Pipeline / 不必改 CoverService（可选增强另议）。

### 3.5 SKILL.md 过程草案（供下阶段实现）

1. 确认 `input` 为本机可读音频路径。  
2. 确认 `voice_id ∈ {example_voice, example_voice_b}`（或将来 `voices` 列表）。  
3. 调用 `scripts/aivoice_submit.py`（使用 AIVOICE `.venv` + `PYTHONPATH=src`）。  
4. 向用户回报 `job_id` + `status`；说明翻唱约 1–3 分钟。  
5. **同一 Python 进程内**轮询 `status`（或调用常驻服务），至 `completed`/`failed`。  
6. `completed` 时 `result` → 报告 `mp3_path`（Hermes 可对绝对路径做媒体投递）。  
7. 禁止直接拼 `audio-separator` / `inference_main.py` / 直调 Pipeline。

### 3.6 建议的 Skill 目录草图（未创建）

```text
media/aivoice-cover/
  SKILL.md
  scripts/
    aivoice_submit.py    # stdin JSON → submit → {job_id,status}
    aivoice_status.py    # job_id → status view
    aivoice_result.py    # job_id → CoverResult JSON
  references/
    voices.md            # example_voice/example_voice_b 说明
    troubleshooting.md
```

解释器固定为：

```text
<repo-root>\.venv\Scripts\python.exe
```

工作目录：`<repo-root>`，`PYTHONPATH=src`。

---

## 4. 调用流程（端到端）

```text
用户: 「用示例歌手音色翻唱 示例曲目.mp3」
        │
        ▼
Hermes 匹配 description → skill_view(aivoice-cover)
        │
        ▼
Skill 指示：组装
  { input, voice_id: "example_voice", pitch: 0, options: {...} }
        │
        ▼
terminal: .venv\python.exe scripts/aivoice_submit.py < json
        │
        ▼
脚本内:
  CoverRequest(input_audio=..., model_name="G_27200"|speaker 将来,
               pitch=..., client="hermes")
  job_id = CoverService.submit(request)
  status = CoverService.status(job_id).status
  print({job_id, status})
        │
        ▼
Hermes 展示 job_id；按 Skill 继续同进程/服务轮询
        │
        ▼
completed → result.mp3_path → 用户
```

与 GUI 关系：

```text
GUI ──► CoverService.run()     （同步，不变）
Hermes ─► CoverService.submit() （异步 Job API）
              │
              └──► 同一 PipelineAdapter → Pipeline（不修改）
```

---

## 5. 风险

| 风险 | 等级 | 说明 | 缓解 |
|------|------|------|------|
| **Job 内存不跨进程** | **高** | `JobStore` 在进程内；Hermes 两次独立 `python` 调用会丢 job | Skill 要求 **单进程 submit+poll**；或实现本地 HTTP 常驻（设计已有，**不改 Pipeline**） |
| **voice_id 未进 CoverRequest** | 中 | 现网仅有 `model_name`；Registry 未实现 | Skill 临时别名表；尽快做 v1.1 Registry Phase 1 |
| **错误 config 配对** | 中 | `G_16000` 若仍走启发式可能绑错 config | 提交前接 Registry；或脚本内显式路径（仍属 SVC 层，非 Pipeline 业务改） |
| **长耗时 vs Agent timeout** | 中 | 翻唱 ~139s；code_execution timeout 默认可见 300s | 异步回报 job_id；轮询间隔拉长；勿用同步 `run()` 堵死网关 |
| **Agent 绕过 Skill 直调 CLI** | 中 | 模型可能 invent 命令 | SKILL 写明禁止；description 强调唯一入口 |
| **Hermes 与 AIVOICE venv 分离** | 中 | Hermes venv ≠ AIVOICE `.venv` | 脚本写死 AIVOICE python 路径 |
| **媒体投递** | 低 | 网关识别绝对路径投递音频 | Skill 终态输出 `mp3` 绝对路径；可选 `[[audio_as_voice]]` |
| **把 Skill 误当成原生 Tool** | 低 | 期待 `aivoice.cover.submit` 工具名 | 文档澄清：Skill=过程；真正调用是 scripts/HTTP |
| **修改 AIVOICE / Pipeline 冲动** | — | 本阶段禁止 | 封装只放 Hermes skill 树或 `hermes_skill/` 旁路 |

---

## 6. 与既有文档关系

| 文档 | 关系 |
|------|------|
| `AIVOICE_SKILL_SPEC.md` | 逻辑操作名（`aivoice.cover.*`）；本审查落实为 Hermes SKILL.md + scripts |
| `hermes_integration_design.md` | 推荐 HTTP façade；本阶段优先 **Skill+脚本**，HTTP 作跨进程 Job 的升级项 |
| `voice_registry_design.md` | `voice_id` 权威语义；Skill 参数已对齐 |
| `p4_service_report.md` | `submit`/`status`/`result` 已存在，可供封装 |

---

## 7. 下阶段建议（不在本次执行）

1. 在 `%HERMES_HOME%/skills/media/aivoice-cover/` **或** `<repo-root>\hermes_skill\...` 落盘 SKILL.md + scripts（仍可不改 `src/aivoice_studio`）。  
2. 用 `示例曲目.mp3` + `voice_id=example_voice` 做 Hermes 实机冒烟（同进程轮询）。  
3. 评估是否需要最小 HTTP Job 服务以支持「先返回 job_id、稍后再查」。  

---

## 8. 本阶段结束

- 已确认本机 Hermes Skill 加载机制与放置约定。  
- 已设计 AIVOICE Skill → `CoverService.submit()` 的参数/返回与流程。  
- **未修改** AIVOICE 代码与 Pipeline。  
- **停止。**
