# AIVOICE v1.3-0.3.3 — Real End-to-End Worker Smoke Test Design

> 日期：2026-07-27  
> 性质：**设计**（不写验收代码、不改产品代码）  
> 前置：  
> - Minimal Execution 已落地（`CoverService.run(job_id=…)` + `executor` + runtime）  
> - 报告：`worker_minimal_execution_report.md`（目前仅 mock 验收）  

**目的：** 在接 Hermes / 飞书之前，用**真实音频 + 真实 UVR/SVC**证明 Worker 执行器稳定可交付。  
**原则：** 先稳执行器，再包消息外壳。

---

## 1. 为什么现在做真冒烟

| 已有 | 缺口 |
|---|---|
| FileJobQueue + claim/complete | mock 不跑 Pipeline |
| `run(job_id=)` 透传 | 未验证 `outputs/{job_id}` 与队列 id 一致 |
| Worker 主循环 | 未在真实 GPU/DirectML 负载下跑通 |

若跳过本步直接改 Skill enqueue + 飞书，失败时难以区分是 **消息层** 还是 **执行器**。

---

## 2. 验收目标（Must Pass）

一次成功冒烟须同时满足：

1. **Enqueue**：向 `jobs/queued/` 写入含真实 `input_audio` 的 job（脚本或 Python，不经 Hermes）。  
2. **Worker**：`python -m aivoice_studio.worker --once -v`（或常驻窗口）claim 并执行。  
3. **执行**：真实走过 UVR → SVC → Mix → Export（`mock_mode=false`）。  
4. **对齐**：`outputs/{job_id}/cover.mp3` 存在，且父目录名 == FS `job_id`。  
5. **队列终态**：`jobs/completed/{job_id}.json` 存在；`running/` / `queued/` 无该 id；`output_path` 指向该 mp3。  
6. **进度**：`completed` JSON 中曾出现合理 `current_stage` 痕迹（至少执行中写过 `uvr` 或 `svc`；终态 `done`）。  
7. **锁**：冒烟期间仅一个 Worker；第二实例应因 `worker.lock` 失败退出（可选检查，建议做）。

失败冒烟（至少一条）也建议设计进套件：

8. **缺文件失败**：`input_audio` 不存在 → `jobs/failed/{id}.json`，`error` 可读，无 traceback 文件污染。

---

## 3. 非目标（本设计明确不做）

- 不改 Hermes Skill / 飞书 / outbox  
- 不改 Pipeline / UVR / SVC / GUI  
- 不要求自动化 CI 上跑 GPU（本机手工或半自动脚本即可）  
- 不测多 job 并发（应串行；可测「队列里两单、Worker 依次完成」作为增强项）  
- 不做 cancel / stale running 恢复（可记观察项）

---

## 4. 测试资产

### 4.1 输入音频

| 选项 | 说明 | 推荐 |
|---|---|---|
| **A. 短本地 mp3** | 已有 `workdir/_gpu_smoke/clip30.mp3`（约 30s）或从成功翻唱源截取 20–40s | **首选**（控制在数分钟内） |
| **B. 全曲** | 如已下载的 GD `source.mp3` | 回归用，耗时长 |
| **C. 新截取** | `ffmpeg -t 25 -i <full> clip.mp3` | 无短文件时 |

音色：`voice_id=example_voice_b` 或 `example_voice`（二者均已真机验证过即可；建议 **先 example_voice 或 example_voice_b 固定一个**，避免一次冒烟换模型噪音）。

### 4.2 环境前提 Checklist

冒烟前人工确认：

- [ ] AIVOICE `.venv` 可用；`PYTHONPATH` 未指向 Hermes site-packages  
- [ ] `config` 中 `runtime.mock_mode: false`  
- [ ] UVR DirectML / SVC workenv 与近期成功翻唱一致  
- [ ] 磁盘 `jobs/`、`outputs/`、`workdir/` 可写  
- [ ] 无第二 Worker / 无 GUI 重翻唱抢 GPU（建议关掉其它翻唱）  
- [ ] `nvidia-smi` 可见 GPU（SVC）；UVR 走 DirectML  

---

## 5. 冒烟流程设计

### 5.1 Happy path（主路径）

```text
0. 准备 clip.mp3 + 选定 voice_id
1. 清理（可选）：移走 jobs/running|queued 里旧测试残留
2. Enqueue（设计约定用一小段 Python/CLI，非 Hermes）：
     enqueue_job(
       input_audio=<绝对路径>,
       voice_id=<example_voice_b|example_voice>,
       pitch=0,
       source="worker-smoke",
       metadata={"smoke": true},
     )
   → 记录 job_id
3. 启动 Worker --once -v
4. 观察日志：
     event=claim …
     event=stage … uvr / svc …
     event=complete … output_path=…
5. 断言文件系统（见 §2）
6. 人工听一下 mp3（可选但强烈建议）
7. 记录耗时 wall clock、profiling_report（若 Pipeline 仍写 profiling）
```

### 5.2 Failure path（缺输入）

```text
enqueue_job(input_audio=<不存在路径>, voice_id=example_voice_b)
worker --once
→ failed/{id}.json, error 含「找不到输入音频」类文案
→ 无 completed；outputs 下无该 id 成功物（或仅空目录可接受）
```

### 5.3 Lock path（可选）

```text
终端 A：worker 常驻（或卡住 sleep 的长任务）
终端 B：再启 worker
→ exit code ≠ 0，日志 lock_failed
```

---

## 6. 断言清单（实现验收脚本时对照）

| ID | 断言 | 失败含义 |
|---|---|---|
| A1 | enqueue 后 `queued/{id}.json` 存在 | Queue 回归坏了 |
| A2 | worker 退出码 0（成功路径） | 执行器或环境崩了 |
| A3 | `completed/{id}.json` 存在 | complete_job 未走通 |
| A4 | `status==completed` 且 `output_path` 非空 | JSON 终态错误 |
| A5 | `Path(output_path).is_file()` | 路径写了但文件无 |
| A6 | `Path(output_path).parent.name == job_id` | **job_id 未透传** |
| A7 | `queued/`、`running/` 无该 id | 状态机/rename 问题 |
| A8 | mp3 大小 > 阈值（如 > 50KB） | 空壳/失败误标成功 |
| A9 | （可选）日志含 `stage=uvr` 或 `svc` | progress 桥未工作 |
| F1 | 缺文件 → `failed/` + 可读 error | 失败路径回归 |

---

## 7. 建议的验收载体（实现阶段再写）

设计推荐新增（**本阶段不创建**）：

| 产物 | 作用 |
|---|---|
| `scripts/smoke_worker_e2e.py` | 半自动：enqueue → 调 worker --once → 跑断言 → 打印 JSON 报告 |
| `scripts/smoke_worker_e2e.ps1` | 清环境、`unset` 等价、设 `PYTHONPATH=src`、调上述脚本 |
| `worker_e2e_smoke_report.md` | 跑完后人工或脚本填写：job_id、耗时、路径、听感、GPU 备注 |

参数建议：

```text
--audio <path>          # 默认 clip30
--voice-id example_voice_b|example_voice
--jobs-root <optional>
--skip-lock false
--timeout-hint 600      # 仅文档/外层等待，非改 CoverService
```

脚本 **不得** mock CoverService；失败即冒烟失败。

---

## 8. 通过 / 失败判定

### Pass

- Happy path A1–A8 全过  
- Failure path F1 过  
- （推荐）人工确认音频可听  

### Fail → 阻断 Hermes 接入

任一：

- A6（job_id 目录不一致）  
- A2 非 0 且非环境说明不足  
- 成功标 completed 但无有效 mp3  
- Worker 进程崩溃留下 running 且无失败收口（记录为缺陷，可先手工 fail 再修）  

### 环境性延期（不算产品 Fail，但不可宣称 Pass）

- 显存不足 / 驱动异常 / 依赖缺失  
→ 报告标注 **BLOCKED**，修环境后重跑，**仍不应开始 Hermes enqueue**。

---

## 9. 观察项（记入报告，不挡 Pass）

- 端到端 wall time vs 近期 GUI/Skill 同曲目  
- UVR DirectML 是否仍明显快于历史 CPU  
- `jobs/completed` JSON 的 `progress` 最终形态  
- 是否生成 `profiling_report.md`  
- 睡眠/锁屏是否导致异常（若偶发，记入恢复切片）  

---

## 10. 与后续 Hermes 的边界

| 本冒烟证明 | Hermes 切片才做 |
|---|---|
| Worker 能稳定吃 queue 出成品 | Skill 只 enqueue + 秒回 |
| job_id ↔ outputs 对齐 | outbox → 飞书发文件 |
| 单卡串行 + lock | 会话 / pick 与 job 关联 |

**门禁：** `worker_e2e_smoke_report.md` 标记 **PASS** 后，才开 v1.3 Skill enqueue / 通知切片。

---

## 11. 设计结论

1. 真冒烟 = 短真实 mp3 + `enqueue_job` + `worker --once` + 文件系统断言（尤其 **A6 job_id 对齐**）。  
2. mock 验收保留作回归；**不能替代**本冒烟。  
3. 实现阶段只需薄脚本 + 报告模板；**不改** Pipeline / Cover 执行逻辑。  
4. Pass 是 Hermes「接入服务」的前置条件。

---

*v1.3-0.3.3 设计结束。下一步：按本文实现 smoke 脚本并出 PASS/FAIL 报告（仍可不改 Hermes）。*
