# Cover 层 Architecture Review（P1.5）

> 只读审查。本阶段**未因审查结果修改代码**。  
> 审查对象：`src/aivoice_studio/cover/`

---

## 原则对照

### 1. CoverService 不包含业务逻辑 — **通过**

`CoverService.run` 仅：

```text
return self._adapter.run(request, on_progress=on_progress)
```

无分支业务、无重试、无路径改写、无模型选择逻辑。

### 2. PipelineAdapter 是唯一调用 Pipeline 的地方 — **在 Cover 层内通过**

| 范围 | 结论 |
|------|------|
| `aivoice_studio.cover.*` | 仅 `adapter/pipeline_adapter.py` 调用 `build_pipeline` / 使用 Pipeline |
| 全仓库 | GUI / CLI / Flask / Feishu **仍**直连 `build_pipeline`（P1 设计如此，待 GUI 迁移） |

**说明：** 原则按「Cover 架构边界」解读为通过；按「全应用唯一入口」解读则**尚未达成**，属预期债务，见 `gui_migration_checklist.md`，**不是 P1.5 缺陷**。

### 3. Domain 不依赖 GUI — **通过**

`cover/domain/*` 仅标准库 + 本包 DTO。无 PyQt、无 `ui.*` 导入。

### 4. Contracts 不依赖具体实现 — **通过**

`cover/contracts/protocols.py` 只依赖 `domain` 中的 `CoverRequest` / `CoverResult` / `ProgressEvent`。  
未 import `PipelineAdapter` / `CoverService` / `factory`。

### 5. 依赖方向 — **基本通过（有一处风格备注）**

实际依赖：

```text
domain          （无向上依赖）
contracts       → domain
service         → domain, contracts, adapter(concrete default)
adapter         → domain, contracts, factory/pipeline（Infrastructure）
```

与目标：

```text
Domain ← Service ← Adapter ← Infrastructure
```

一致之处：Domain 在内层；Adapter 是唯一碰 Pipeline 的 Cover 组件。

**备注（非违规，建议后续收敛）：**

- `CoverService.__init__` 默认 `PipelineAdapter()` 依赖**具体类**，而非只依赖 `PipelineAdapterProtocol`。  
  已支持构造注入，测试可替换 mock；P1 可接受。  
  后续可将 type hint 改为 Protocol，默认工厂放在 composition root。
- `cover/__init__.py` 再导出 `CoverService`，导致 `import aivoice_studio.cover` 拉取 adapter。  
  不影响 GUI；若要更严分层，可改为子模块显式导入。

---

## 其它观察（不修改）

| 项 | 级别 | 说明 |
|----|------|------|
| Cover `JobContext` vs Pipeline `JobContext` | info | 同名异义；Adapter 已用别名 `PipelineJobContext` |
| `PipelineAdapter.mock_mode` | info | 测试缝；`CoverService` 未暴露，避免业务入口渗入测试参数 — 合理 |
| 失败语义 | info | Pipeline 阶段失败多为 `JobResult(success=False)`，Adapter 映射到 `CoverResult`，与 GUI 现网一致；意外异常不吞（contract 已测） |

---

## 结论

- **未发现需要立即改代码的原则性违规。**
- Cover 骨架符合 P1「旁路新架构、GUI 仍直连」的约定。
- 全应用「唯一 Pipeline 入口」需等 GUI（及可选 CLI/API）迁移后关闭。

本文件为审查交付物；按任务要求发现问题仅记录、**不改代码**。
