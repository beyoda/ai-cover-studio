# AIVOICE v1.1-0 — SVC Voice Model Capability Audit

> 阶段：v1.1-0（只读检查，**未改代码**）  
> 日期：2026-07-26  
> 问题：当前 v1.0 **是否已经支持多声音模型切换？**

---

## 结论（摘要）

| 问题 | 判定 |
|------|------|
| 能否在多个 **checkpoint（.pth）** 间切换？ | **已支持**（`model_name` 贯通 GUI → CoverService → Pipeline → SVC） |
| 代码是否硬编码 `G_27200.pth` / `config1.json` 路径？ | **否**（未写死 `.pth`）；**是软偏好**：无 `{model}.json` 时优先共用 `config1.json` |
| 能否按请求切换 **speaker / voice**？ | **不支持**（speaker 来自全局 `config/svc.yaml`，CoverRequest/JobContext 无该字段） |
| 「示例歌手」模型文件在哪？ | **无名为「示例歌手」的 .pth**；说话人 ID `example_voice` 仅出现在 `config.json`；当前运行未用该 config / speaker |
| v1.0 是否算「多声音模型切换」完备？ | **半支持**：多 checkpoint 切换 ✅；多音色/说话人语义切换 ❌ |

---

## 1. SVC 推理入口

### 1.1 入口与配置

| 项 | 位置 |
|----|------|
| 实现 | `src/aivoice_studio/modules/svc/svc_runner.py` → `SVCService.infer` |
| 组装 | `src/aivoice_studio/factory.py` ← `config/svc.yaml` |
| 模型目录 | `svc.models_dir` = `<repo-root>\tools\so-vits-svc\logs\44k` |
| 模式 | `mode: so-vits-svc` |

命令模板（`config/svc.yaml`）：

```text
{python} {script} -m {model_path} -c {config_path} -n {input_name}
  -t {pitch} -s {speaker} -f0p {f0_method} -wf {output_format}
```

### 1.2 checkpoint（.pth）来源

`_infer_so_vits_svc` → `_configured_model_path`：

1. 若 `SVCConfig.model_path` 非空 → 用配置里的固定路径  
2. 否则 → `ModelManager.get_model(model_name)` →  
   `{models_dir}/{model_name}.pth`

当前 `svc.yaml`：**未配置** `model_path`，因此 **按请求传入的 `model_name` 动态选 .pth**。

磁盘上现有 checkpoint：

| 文件 | 路径 |
|------|------|
| `G_16000.pth` | `tools/so-vits-svc/logs/44k/G_16000.pth` |
| `G_27200.pth` | `tools/so-vits-svc/logs/44k/G_27200.pth` |

P4 真实验证命令（摘自 profiling）使用的是：

```text
-m ...\logs\44k\G_16000.pth -c ...\logs\44k\config1.json -s output
```

### 1.3 config（.json）来源

`_configured_config_path`：

1. 若 `SVCConfig.config_path` 非空 → 固定配置  
2. 否则 → `ModelManager._find_config(model_name)`：

| 优先级 | 规则 |
|--------|------|
| 1 | `{model_name}.json`（精确匹配） |
| 2 | **`config1.json`**（注释写明供 G_16000 / G_27200 共用） |
| 3 | `config.json` |
| 4 | 目录内任意 `.json` |

当前 `svc.yaml`：**未配置** `config_path`。  
且目录中 **不存在** `G_16000.json` / `G_27200.json`，故实际落到 **共用 `config1.json`**。

### 1.4 是否硬编码 `G_27200.pth` / `config1.json`？

| 对象 | 硬编码？ | 说明 |
|------|----------|------|
| `G_27200.pth` | **否** | 无写死路径；仅文档/注释提及 |
| `G_16000` | 默认名 | `default_model: G_16000`；GUI/CLI 可改 |
| `config1.json` | **软硬编码偏好** | ModelManager 在无精确 `{model}.json` 时优先选它（不是写死绝对路径字符串，但是固定文件名偏好） |
| `speaker` | **全局固定** | `svc.yaml` → `speaker: output` |

**结论：** 推理入口 **没有** 把 checkpoint 钉死为 `G_27200.pth`；config 侧则 **实质固定为 `config1.json`（对当前两枚 G_* 模型）**。

### 1.5 speaker 行为

```text
speaker = self.config.speaker or model_name
```

`svc.yaml` 已设 `speaker: output` → **始终 `-s output`**，与 GUI 所选 `model_name` 无关。

---

## 2. Pipeline / Adapter 参数

### 2.1 字段对照

| 层 | model / model_name | speaker | voice |
|----|--------------------|---------|-------|
| `CoverRequest` | ✅ `model_name: str` | ❌ | ❌ |
| Pipeline `JobContext` | ✅ `model_name` | ❌ | ❌ |
| `PipelineAdapter` | ✅ 映射 `request.model_name` | ❌ | ❌ |
| `Pipeline` → `svc.infer(...)` | ✅ 传 `model_name` | ❌（不传） | ❌ |
| `SVCService.infer` | ✅ | 仅用全局 `SVCConfig.speaker` | ❌ |

### 2.2 含义

- **支持传递「模型名」（checkpoint stem）**：是。  
- **支持传递 `speaker` / `voice`**：否。  
- Cover / Job API 无法按任务选择说话人；多说话人模型场景未打通。

---

## 3. GUI

| 项 | 现状 |
|----|------|
| 控件 | 「音色模型」`QComboBox`（`main_window.py`） |
| 列表来源 | `ModelConfigMap.list_models()` → `models_dir` 下所有 `*.pth` stem |
| 当前可选 | `G_16000`、`G_27200`（与磁盘一致） |
| 默认 | `svc.default_model` → **`G_16000`**（非写死唯一模型） |
| 启动任务 | `_start()` 取 `self._model_combo.currentText()` → `PipelineWorker(model_name=...)` → `CoverRequest.model_name` |

**结论：GUI 不固定死某一个模型**；用户可在下拉框切换 checkpoint。  
默认偏向 `G_16000`，但可改为 `G_27200`。

README 亦写明：「选择音色模型（G_16000 / G_27200）」。

---

## 4. 当前模型加载流程

```text
GUI 下拉 / CLI --model / CoverRequest.model_name
        │
        ▼
CoverService → PipelineAdapter
        │  JobContext.model_name = request.model_name
        ▼
Pipeline.svc.infer(model_name=...)
        │
        ├─ model_path = models_dir / f"{model_name}.pth"
        │                 （除非 yaml 配了固定 model_path）
        ├─ config_path = {model}.json
        │               否则 → config1.json（当前实际路径）
        │               再否则 → config.json / 任意 json
        └─ speaker = svc.yaml.speaker（"output"）
                    或（仅当 yaml 为空）回退 model_name

so-vits-svc inference_main.py
  -m <pth> -c <json> -s <speaker>
```

---

## 5. 「示例歌手」模型位置

### 5.1 磁盘检索结果

- **未发现** 文件名含「示例歌手」/ `example_voice` / `ExampleVoice` 的 `.pth`。  
- 仅有：`G_16000.pth`、`G_27200.pth`（同目录 `logs/44k/`）。

### 5.2 与示例歌手相关的配置痕迹

| 文件 | `spk` 映射 | 是否被当前运行使用 |
|------|------------|-------------------|
| `tools/so-vits-svc/logs/44k/config.json` | **`"example_voice": 0`** | **否**（被 `config1.json` 优先挡住） |
| `tools/so-vits-svc/logs/44k/config1.json` | `"output": 0` | **是**（当前默认） |
| `tools/so-vits-svc/logs/44k/configcos.json` | `"output": 0` | 否（且 encoder 为 hubertsoft，与 G_* 的 vec768 不匹配） |

**解读：**

- 仓库内唯一明确的「示例歌手」符号是说话人名 **`example_voice`**（在 `config.json`）。  
- 实际推理用的是 **`config1.json` + `-s output`**，**没有**走 `example_voice`。  
- `G_16000` / `G_27200` 更像同一训练线不同步数的 checkpoint，**不是** GUI 上的「艺人显示名」；无法从文件名断言哪一个是「示例歌手模型」，仅能说音色资产位于：

```text
<repo-root>\tools\so-vits-svc\logs\44k\
  G_16000.pth
  G_27200.pth
  config1.json   ← 当前绑定
  config.json    ← 含 example_voice，但未接入运行路径
```

若业务上认定这些 G_* 即示例歌手声线，则「模型位置」即上述目录；**命名与 speaker 接线尚未产品化**。

---

## 6. 是否支持切换？

| 切换类型 | 支持？ | 证据 |
|----------|--------|------|
| 多 **checkpoint**（G_16000 ↔ G_27200） | **是** | GUI 下拉 + `model_name` 全链路 |
| 多 **speaker**（如 `output` ↔ `example_voice`） | **否** | speaker 全局 yaml；Request 无字段 |
| 友好 **voice** 名（「示例歌手」） | **否** | 无 voice 字段、无艺人别名表 |
| 新增第三个 `.pth` 即出现在 GUI | **是（资产级）** | `list_models()` 扫目录；需兼容 config/encoder |

**总评：** v1.0 **已支持多 checkpoint 切换**；**尚未支持多声音（speaker/voice）切换**。  
若「多声音」指不同艺人/说话人，则 **当前不算完整支持**。

---

## 7. 若不支持完整音色切换 — 最小改动方案（仅方案，不实现）

按侵入性从低到高：

### 方案 A — 配置级接通「example_voice」（最小运维改动）

适用：确认 `G_*` + `example_voice` 为同一模型说话人。

1. 将 `svc.yaml` 的 `speaker` 改为 `example_voice`，或  
2. 让 ModelManager 选中含 `"example_voice"` 的 `config.json`，且 `-s example_voice` 与 `spk` 一致。  
注意：`config1.json` 只有 `output`，改 speaker 为 `example_voice` 而不换 config 会推理失败。

**改动面：** 配置 / 文档为主，代码可不动。

### 方案 B — 按模型精确绑定 config（推荐小改）

1. 为 checkpoint 增加精确配置，例如：  
   `G_16000.json` / `G_27200.json`（或软链到正确 config）  
2. 保证每个 json 的 `spk` 与 yaml/请求中的 speaker 一致。  

**改动面：** 资产 + 可选去掉对 `config1.json` 的盲目优先（或保留作 fallback）。

### 方案 C — 请求级 `speaker`（真正「可切换声音」）

1. `CoverRequest` / `JobContext` 增加可选 `speaker: str | None`  
2. `Pipeline` → `svc.infer(..., speaker=...)`  
3. `SVCService` 优先用请求 speaker，否则回退 yaml  
4. GUI 增加说话人下拉（或从所选 config 的 `spk` keys 读取）  

**改动面：** Cover 层 + SVC + GUI；仍不必 Redis/Worker。

### 方案 D — Voice 产品别名（体验层）

增加映射表，例如：`"示例歌手" → { model_name: "G_16000", speaker: "example_voice", config: "..." }`，GUI 显示艺人名。  

**改动面：** UI/配置映射；底层仍走 B 或 C。

---

## 8. 本阶段结束

- 只读审计完成；**未实现任何代码改动**。  
- 输出文件：`aivoice_model_audit.md`  
- **停止。**
