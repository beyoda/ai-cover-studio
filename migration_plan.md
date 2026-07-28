# Voice Registry Migration Plan

> Phase: AIVOICE v1.1-1（**只设计，不改代码**）  
> Date: 2026-07-26  
> Companion: `voice_registry_design.md`  
> 约束：**迁移全程保持现有 GUI 与 Pipeline 可运行**  
> 说明：本文取代仓库根目录旧版「GUI→CoverService」迁移叙述；该历史计划见 `design/cover_skill/migration_plan.md`（P2 已完成）。

---

## 1. 迁移目标

```text
调用方主语义：

  model_name: "G_27200"
        ↓
  speaker / voice_id: "example_voice"
        ↓
  Registry → G_27200.pth + config1.json
```

权威资产（迁移后必须生效）：

| voice_id | display_name | checkpoint | config |
|----------|--------------|------------|--------|
| `example_voice_b` | ExampleVoiceB | `G_16000.pth` | `configcos.json` |
| `example_voice` | 示例歌手 | `G_27200.pth` | `config1.json` |

---

## 2. 原则

| 原则 | 做法 |
|------|------|
| 加法优先 | 先加 Registry / `speaker`，不删 `model_name` |
| 边界解析 | 在 Adapter 或 SVC 入口解析；少动 `Pipeline.run` 步骤 |
| 可回滚 | `voices.json` 可禁用；feature flag 可退回旧 ModelManager |
| 行为可测 | 每阶段保留 pytest；GUI mock 翻唱不回归 |
| 一音色一资产 | 禁止用 `config.spk` 自动拆多音色 |

---

## 3. 阶段划分

### Phase 0 — 文档与资产冻结（本阶段已完成设计）

- [x] `voice_registry_design.md`  
- [x] `migration_plan.md`  
- [ ] （实现期）核对磁盘文件存在：`G_16000.pth`、`G_27200.pth`、`configcos.json`、`config1.json`

**出口：** 产品确认两行资产表无误。

---

### Phase 1 — 引入 Registry，静默修正配对（GUI 外观不变）

**目的：** 先修「错误 config 配对」，用户仍选 `G_16000` / `G_27200`。

1. 新增 `config/voices.json`（内容按设计文档 §4，含 aliases）。  
2. 实现 `VoiceRegistry.load` / `resolve` / `resolve_paths`。  
3. 在 **SVC 推理取路径处**（推荐 `SVCService` so-vits 分支或 Adapter 预解析）调用 Registry：  
   - 输入仍为现有 `model_name`  
   - `G_16000` → example_voice_b 资产 → `configcos.json`  
   - `G_27200` → example_voice 资产 → `config1.json`  
4. Feature flag（建议）：`svc.use_voice_registry: true`（默认 true 或先 false 灰度）。  
5. **不改** GUI Combo 文案；**不改** `CoverRequest` 必填性。

**Pipeline：** 继续接收 `JobContext.model_name`；内部路径改由 Registry 给出。

**验收：**

- 选 `G_27200` 实际加载 `G_27200.pth` + `config1.json`  
- 选 `G_16000` 实际加载 `G_16000.pth` + `configcos.json`  
- GUI 仍能生成翻唱；现有测试通过  

**回滚：** flag=false → 恢复旧 `ModelManager` 启发式。

---

### Phase 2 — `CoverRequest` 加法：`speaker`

1. `CoverRequest` 增加可选 `speaker: str | None = None`。  
2. 解析规则：`ref = speaker or model_name`（speaker 优先）。  
3. `model_name` 改为可选（实现时注意：dataclass 兼容——迁移期可保持 `model_name` 必填但允许与 speaker 二选一校验放在 Service 层）。  
4. GUI / bridge：**暂可只填 model_name**，行为与 Phase 1 相同。  
5. Hermes / Job API 文档允许传 `speaker: "example_voice"`。

**验收：**

- `CoverRequest(speaker="example_voice", model_name=None)` 或 `model_name=""` 可跑通（若采用 Service 层校验）  
- 旧 `CoverRequest(model_name="G_27200")` 仍可跑通  

**回滚：** 忽略 `speaker` 字段即可。

---

### Phase 3 — GUI 展示名切换（可运行前提下改 UX）

1. Combo 数据源改为 `registry.list()`。  
2. 显示 `display_name`（示例歌手 / ExampleVoiceB）；提交 `speaker=voice_id`。  
3. 可选：同时写入 `model_name=checkpoint_stem` 便于历史记录兼容。  
4. 默认选中 `default_voice_id`（`example_voice`）。  
5. 历史记录：优先存 `voice_id` + `display_name`；`model_name` 保留 stem。

**验收：**

- UI 可见「示例歌手」「ExampleVoiceB」  
- 选示例歌手 → 实际 G_27200 + config1  
- 选 ExampleVoiceB → 实际 G_16000 + configcos  
- 旧 history.json 仍能展示（缺 voice_id 时回退显示 model_name）  

**回滚：** Combo 改回 `list_models()` stems。

---

### Phase 4 — Hermes / Skill 契约对齐

1. 更新 Skill 文档：主推 `speaker`；`model_name` 标为兼容。  
2. 增加 `aivoice.cover.voices`；`models` 标记 deprecated。  
3. 示例请求改为 `speaker: "example_voice"`。  

**验收：** 契约测试 / 文档示例与 Registry 一致；旧 `model_name` 示例仍注明可用。

---

### Phase 5 — 清理（可选，勿与 Phase 1–3 捆绑）

仅在稳定后：

- 收紧「未知 model_name 扫盘猜 config」  
- 降低对 `ModelConfigMap` 启发式依赖  
- 评估 `svc.yaml` 全局 `speaker: output`：改为「每资产 `inference_speaker` / 从该资产 config 读取默认 `-s`」  

**不要**删除 `model_name` 字段（长期兼容更安全）。

---

## 4. 推荐落地顺序（一张图）

```text
Phase 1  Registry 静默纠偏（G_* → 正确 pth+json）
    ↓  GUI/Pipeline 外观不变，行为更正确
Phase 2  CoverRequest.speaker 加法
    ↓  API/Hermes 可先用 voice_id
Phase 3  GUI 显示「示例歌手 / ExampleVoiceB」
    ↓
Phase 4  Skill 文档与 voices 列表
    ↓
Phase 5  可选清理启发式
```

---

## 5. 兼容矩阵

| 客户端 | 迁移期输入 | 解析结果 |
|--------|------------|----------|
| 旧 GUI | `model_name=G_27200` | example_voice 资产 |
| 新 GUI | `speaker=example_voice` | example_voice 资产 |
| 旧 Hermes | `model_name=G_16000` | example_voice_b 资产 |
| 新 Hermes | `speaker=example_voice_b` | example_voice_b 资产 |
| 混传 | `speaker=example_voice` + `model_name=G_16000` | **example_voice**（speaker 优先） |

---

## 6. 风险与缓解

| 风险 | 缓解 |
|------|------|
| `configcos` encoder 与 checkpoint 不匹配 | Phase 0 用短音频真推理验收 example_voice_b / example_voice 各一次 |
| alias 冲突 | `voices.json` 加载时唯一性校验 |
| GUI 用户仍搜 G_* | aliases 保留；或显示名旁小字 checkpoint |
| Pipeline 大改导致回归 | 坚持 Adapter/SVC 边界解析；Pipeline 步骤不动 |
| 全局 yaml `speaker: output` 与资产不符 | Phase 1 起按资产 config 决定 `-s`，削弱全局 speaker |

---

## 7. 回滚总策略

1. `svc.use_voice_registry: false`  
2. 或移除/重命名 `config/voices.json` 并回退代码路径  
3. GUI 恢复 stem 列表  
4. **不**回滚用户已生成的 outputs（与 Registry 无关）

---

## 8. 明确不在本迁移做的事

- 不引入 Redis / DB / 常驻 Worker  
- 不把多 voice 做成同一 `.pth` 下的 `spk` 切换  
- 不修改 UVR Cache 键语义（仍按输入音频 + UVR 模型；与音色无关）  
- 本设计阶段 **不写代码、不提交 voices.json 实现**

---

## 9. 完成标准（实现期 Definition of Done）

1. `speaker=example_voice` → `G_27200.pth` + `config1.json`  
2. `speaker=example_voice_b` → `G_16000.pth` + `configcos.json`  
3. `model_name=G_27200` / `G_16000` 仍可用  
4. GUI 翻唱可运行；Pipeline 回归测试通过  
5. 文档与 Hermes 示例以 `speaker` 为主  

---

## 10. 本阶段结束

v1.1-1 **仅设计**：`voice_registry_design.md` + `migration_plan.md`。  
**停止；不实现。**
