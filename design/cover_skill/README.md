# Cover Skill 设计包（Phase 1）

本目录仅含**设计文档与接口契约**，未修改任何业务代码。

| 文件 | 说明 |
|------|------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 三层架构、GUI 共存、演进路线 |
| [skill/SKILL.md](./skill/SKILL.md) | Hermes / Agent Skill 契约 |
| [interfaces/cover_api.schema.json](./interfaces/cover_api.schema.json) | JSON Schema DTO |
| [interfaces/openapi.yaml](./interfaces/openapi.yaml) | Cover Service OpenAPI |
| [interfaces/python_protocols.md](./interfaces/python_protocols.md) | Adapter/Service Protocol 与字段映射 |
| [migration_plan.md](./migration_plan.md) | 下一阶段 GUI → CoverService 切换步骤（亦见仓库根目录同名文件） |

**硬约束：** Pipeline / GUI / CLI 保持现有调用方式；Hermes 仅经 Skill → Service → Adapter。

**P1 骨架代码：** `src/aivoice_studio/cover/`（domain / service / adapter / contracts）。
