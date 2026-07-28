# AIVOICE v1.3-0.3.3 — Worker E2E Smoke Report

> 日期：2026-07-27  
> 依据：`aivoice_v1.3_worker_e2e_smoke_design.md`  
> 总判定：**PASS**  
> 说明：本报告区分 **真实翻唱成功** 与 **故意失败路径**；后者的 error 文案不是产品执行失败。

---

## 1. Environment

| 项 | 值 |
|---|---|
| audio | `<repo-root>\workdir\_gpu_smoke\clip30.mp3` |
| voice_id | `example_voice_b` |
| jobs_root | `<repo-root>\jobs` |
| mock CoverService | **false**（真实 Worker 子进程，无 mock） |
| PYTHONPATH | `<repo-root>\src` |

---

## 2. Happy Path — Real Worker Execution

**状态：SUCCESS（真实翻唱成功）**

本路径使用真实音频，经真实 Worker claim → `CoverService.run` → UVR → SVC → Mix → Export，**不是**失败用例。

| 项 | 值 |
|---|---|
| 结果 | **成功完成** |
| job_id | `983b10cb5b37` |
| 队列终态 | `jobs/completed/983b10cb5b37.json`（`queued` / `running` 已清空） |
| wall_s | 36.7 |
| worker_rc | 0 |
| output_path | `<repo-root>\outputs\983b10cb5b37\cover.mp3` |
| output_bytes | 1003146（> 50KB） |
| current_stage | `done` |
| job_id 对齐 | `output_path` 父目录名 == `983b10cb5b37`（A6 PASS） |
| stages | 日志含 `uvr` → `svc` → `mixing` → `exporting` → `done` |
| assertions | A1–A8 全过；A9 stage 痕迹有 |

**听检（客观 + 播放）：**

- 时长 25.0s / 320 kb/s stereo / 44.1 kHz  
- mean ≈ -24.6 dB，peak ≈ -9.4 dB（非空壳、未削波）  
- 已用系统播放器打开；可人工确认人声/伴奏

---

## 3. Failure Path — Intentional Missing Input

**状态：EXPECTED FAIL（故意错误输入，验证失败收口）**

本路径**故意** enqueue 不存在的 `input_audio`，用于验证 Worker 将任务写入 `failed/` 并给出可读错误。  
**「找不到输入音频文件。」是预期结果，不是 Happy Path 失败，也不是真实翻唱崩溃。**

| 项 | 值 |
|---|---|
| 结果 | **按设计失败收口（PASS）** |
| 意图 | 负向用例 / 缺文件 |
| job_id | `6b2971b7c8f1` |
| 队列终态 | `jobs/failed/6b2971b7c8f1.json`（无 `completed`） |
| error（预期） | `找不到输入音频文件。` |
| worker_rc | 0（进程正常退出；job 已 `fail_job`） |
| assertions | F1：failed 文件 + 可读 error + 无 completed |

---

## 4. Lock Path（可选）

**状态：EXPECTED FAIL（第二实例争锁）**

| 项 | 值 |
|---|---|
| 结果 | **按设计拒绝第二 Worker（PASS）** |
| worker_rc | 1 |
| 说明 | `worker.lock` 占用时第二实例非 0 退出（Windows 上可见 PermissionError / lock_failed） |
| assertions | L1 PASS |

---

## 5. 观察项

- Happy Path 端到端 ~36.7s（25s clip / example_voice_b）；UVR DirectML → SVC → mix → export。  
- profiling：`<repo-root>\profiling_report.md`（本次 Happy Path 已生成）。  
- Failure Path 的 error 文案仅证明失败路径，**不得**解读为冒烟整体失败。

---

## 6. 结论

| 路径 | 含义 | 本报告 |
|---|---|---|
| Happy Path | 真实 Worker 翻唱成功 | **SUCCESS** |
| Failure Path | 故意缺文件 → 可读 fail | **EXPECTED FAIL（用例 PASS）** |
| Lock Path | 单 Worker 锁 | **EXPECTED FAIL（用例 PASS）** |

**总判定：PASS** — 可开 Hermes Skill enqueue / 飞书 outbox 切片。
