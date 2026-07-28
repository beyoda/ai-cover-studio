# CoverService Skill 就绪度审查

> Phase: P3 — 只读审查，**不修改代码**  
> 对象：`src/aivoice_studio/cover/service/cover_service.py` 及 Cover 层配套 DTO  
> 对照：`AIVOICE_SKILL_SPEC.md` Skill 化要求

---

## 审查结论（摘要）

| 检查项 | 现状 | 判定 |
|--------|------|------|
| 单一入口 | GUI 与设计上的 Hermes 均可指向 `CoverService.run` | **基本满足**（同步路径） |
| 隐藏内部实现 | Service/Adapter 不向调用方暴露 UVR/SVC/ffmpeg | **满足** |
| 未来异步任务 | 仅有阻塞 `run`；无 `submit` / 队列 | **不满足（缺口）** |
| 状态查询 | 无 `get_job` / job store | **不满足（缺口）** |

**总评：** CoverService 已具备 **同步 Skill 最小闭环**（`run(CoverRequest)→CoverResult`），适合作为 Hermes `aivoice.cover.run` 的后端。  
**尚不具备** Skill 规格中的异步任务与状态查询；需在后续实现阶段扩展 Service，**不必改 Pipeline**。

---

## 1. 是否单一入口

### 现状

```text
CoverService.run(request, on_progress=None) → PipelineAdapter.run → Pipeline
```

- Cover 层内：业务执行经 Service → Adapter，**单一编排入口**。  
- GUI（P2）：已改为 `CoverService().run(...)`。  
- CLI / Flask / Feishu：**仍直连** `build_pipeline`（历史入口，非 CoverService）。

### 对 Skill 的含义

- Hermes 路径只要强制只调 CoverService（或未来 HTTP façade 背后仍是 CoverService），即满足 Skill「单一入口」。  
- 全仓库「唯一调用 Pipeline」尚未达成（CLI/API 旁路仍在）——与 Skill 化正交，属后续统一入口工作。

### 判定

**对 Hermes Skill：满足（约定只走 CoverService）。**  
**对全应用：部分满足。**

---

## 2. 是否隐藏内部实现

### 现状

调用方可见：

- `CoverRequest` / `CoverResult` / `ProgressEvent`  
- `CoverService.run`

调用方不可见（封装在 Adapter/Pipeline 后）：

- `audio-separator` 命令模板  
- so-vits-svc `workenv`  
- ffmpeg 滤镜  
- `JobContext`（Pipeline）细节  

Service 本身无 UVR/SVC 业务逻辑，仅转发 Adapter —— 符合「编排壳」。

### 判定

**满足。** Skill 不应再下沉到 `modules.*`。

---

## 3. 是否支持未来异步任务

### Skill 需求

- `submit` → 立即返回 `job_id`  
- 后台执行 `Adapter.run`  
- 可选队列 / GPU 串行

### 现状

```python
def run(self, request, *, on_progress=None) -> CoverResult:
    return self._adapter.run(request, on_progress=on_progress)
```

- 纯同步阻塞至 Pipeline 结束。  
- 无 job 表、无线程/进程队列、无 `submit` API。  
- 领域层已有 `JobContext`（cover 域，含 `job_id`）与 `request_id` 字段，但 **Service 未使用其做异步生命周期**。

### 判定

**当前不满足异步。**  
**可演进：** 在 CoverService 增加 job store + worker 线程，内部仍调同一 `PipelineAdapter.run`；Pipeline 无需改。

---

## 4. 是否支持状态查询

### Skill 需求

- `status(job_id)` → `queued|running|succeeded|failed` + 最新 `ProgressEvent` + 可选 `CoverResult`

### 现状

- 无持久化/内存 job 注册表。  
- 进度仅通过 **同步回调** `on_progress` 推送；调用方不持有可查询句柄。  
- 结束后只有返回的 `CoverResult`；无法事后按 `job_id` 再取。

### 判定

**不满足。**  
同步 `run` 场景下 Hermes 可不依赖 status；长任务/可取消场景需要后续补齐。

---

## 5. 其它就绪观察

| 项 | 观察 |
|----|------|
| 进度模型 | `ProgressEvent` + `Stage` 已与 Pipeline 对齐，Skill 可直接用 |
| 错误模型 | 阶段失败多为 `CoverResult.success=False`；意外异常向上抛 —— 与 GUI 一致 |
| 健康检查 | Service **无** `health()` / 模型列表 API；Skill 的 `health`/`models` 需后续加在 Service 或 HTTP 层 |
| HTTP façade | 设计有 openapi 草案；**代码未实现** —— Hermes 跨进程前需补 |
| 依赖注入 | `CoverService(adapter=...)` 可测，利于 Skill 宿主测试 |

---

## 6. 缺口与建议优先级（仅建议，本阶段不实现）

| 优先级 | 缺口 | 建议落点 |
|--------|------|----------|
| P0（同步 Hermes） | 无 HTTP/CLI 对外暴露 | 薄封装调用现有 `CoverService.run` |
| P0 | 无 `health` / `models` | CoverService 或 HTTP 层只读方法 |
| P1 | 无异步 job | CoverService 扩展，不改 Pipeline |
| P1 | 无 status 查询 | 同上 job store |
| P2 | CLI/Flask 仍旁路 | 可选统一到 CoverService |

---

## 7. 结论

CoverService **可以**作为 AIVOICE Hermes Skill 的同步执行后端：

- 单一编排入口（对 Skill 约定而言）  
- 内部实现已隐藏  
- DTO 与进度/结果模型已就绪  

CoverService **尚不能**单独满足完整 Skill 规格中的：

- 异步提交  
- 任务状态查询  
- 一等公民的 health/models（需轻微扩展或 HTTP 层）

P3 仅冻结契约与本审查；**不修改 CoverService / Pipeline / GUI**。  
后续实现应以「扩展 CoverService 表面」为主，保持 Adapter 为唯一 Pipeline 调用点（Hermes/GUI 路径）。
