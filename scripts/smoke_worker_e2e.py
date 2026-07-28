#!/usr/bin/env python3
"""AIVOICE v1.3-0.3.3 — real end-to-end Worker smoke (no CoverService mock).

Enqueue → real ``python -m aivoice_studio.worker --once`` → filesystem asserts.
See ``aivoice_v1.3_worker_e2e_smoke_design.md``.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DEFAULT_AUDIO = ROOT / "workdir" / "_gpu_smoke" / "clip30.mp3"
REPORT_PATH = ROOT / "worker_e2e_smoke_report.md"
MIN_MP3_BYTES = 50 * 1024

# Ensure project package is importable; do not inherit Hermes site-packages.
sys.path.insert(0, str(SRC))

from aivoice_studio.worker.lock import WorkerLock  # noqa: E402
from aivoice_studio.worker.queue import FileJobQueue, JobStatus  # noqa: E402


def _python() -> Path:
    venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        return venv_py
    return Path(sys.executable)


def _env_for_worker() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    # Drop VirtualEnv hints that may point at Hermes / other trees.
    env.pop("VIRTUAL_ENV", None)
    env.pop("PYTHONHOME", None)
    return env


def _run_worker(
    *,
    jobs_root: Path,
    timeout_s: float,
    skip_lock: bool = False,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        str(_python()),
        "-m",
        "aivoice_studio.worker",
        "--once",
        "-v",
        "--jobs-root",
        str(jobs_root),
        "--idle-sleep",
        "0.3",
    ]
    if skip_lock:
        cmd.append("--skip-lock")
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=_env_for_worker(),
        capture_output=True,
        text=True,
        timeout=timeout_s,
        encoding="utf-8",
        errors="replace",
    )


def _load_job(queue: FileJobQueue, status: str, job_id: str) -> dict[str, Any]:
    path = queue.job_path(status, job_id)
    return json.loads(path.read_text(encoding="utf-8"))


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


def run_happy_path(
    *,
    audio: Path,
    voice_id: str,
    jobs_root: Path,
    timeout_s: float,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": "happy_path",
        "ok": False,
        "assertions": {},
        "job_id": None,
        "wall_s": None,
        "worker_returncode": None,
        "output_path": None,
        "current_stage": None,
        "progress": None,
        "log_tail": "",
    }
    queue = FileJobQueue(jobs_root)
    t0 = time.monotonic()
    job = queue.enqueue_job(
        input_audio=str(audio.resolve()),
        voice_id=voice_id,
        pitch=0,
        source="worker-smoke",
        metadata={"smoke": True},
    )
    job_id = job.job_id
    result["job_id"] = job_id

    queued_path = queue.job_path(JobStatus.QUEUED, job_id)
    result["assertions"]["A1_queued"] = queued_path.is_file()
    _assert(queued_path.is_file(), f"A1: missing queued/{job_id}.json")

    proc = _run_worker(jobs_root=jobs_root, timeout_s=timeout_s, skip_lock=False)
    result["worker_returncode"] = proc.returncode
    result["wall_s"] = round(time.monotonic() - t0, 1)
    log = (proc.stdout or "") + "\n" + (proc.stderr or "")
    result["log_tail"] = log[-4000:]
    result["assertions"]["A2_worker_exit_0"] = proc.returncode == 0
    _assert(proc.returncode == 0, f"A2: worker exit={proc.returncode}\n{log[-1500:]}")

    completed = queue.job_path(JobStatus.COMPLETED, job_id)
    result["assertions"]["A3_completed_file"] = completed.is_file()
    _assert(completed.is_file(), f"A3: missing completed/{job_id}.json")

    done = _load_job(queue, JobStatus.COMPLETED, job_id)
    output = done.get("output_path") or ""
    result["output_path"] = output
    result["current_stage"] = done.get("current_stage")
    result["progress"] = done.get("progress")
    result["assertions"]["A4_status_output"] = (
        done.get("status") == JobStatus.COMPLETED and bool(output)
    )
    _assert(
        done.get("status") == JobStatus.COMPLETED and bool(output),
        f"A4: bad terminal json status={done.get('status')!r} output={output!r}",
    )

    out_path = Path(output)
    result["assertions"]["A5_output_exists"] = out_path.is_file()
    _assert(out_path.is_file(), f"A5: output_path not a file: {output}")

    parent_ok = out_path.parent.name == job_id
    result["assertions"]["A6_parent_is_job_id"] = parent_ok
    _assert(parent_ok, f"A6: parent={out_path.parent.name!r} != job_id={job_id!r}")

    no_queued = not queue.job_path(JobStatus.QUEUED, job_id).exists()
    no_running = not queue.job_path(JobStatus.RUNNING, job_id).exists()
    result["assertions"]["A7_left_queued_running"] = no_queued and no_running
    _assert(no_queued and no_running, "A7: job still in queued/ or running/")

    size_ok = out_path.stat().st_size > MIN_MP3_BYTES
    result["assertions"]["A8_mp3_size"] = size_ok
    result["output_bytes"] = out_path.stat().st_size
    _assert(size_ok, f"A8: mp3 too small ({out_path.stat().st_size} bytes)")

    stage_hint = (
        "stage=uvr" in log
        or "stage=svc" in log
        or str(done.get("current_stage") or "") in ("done", "uvr", "svc", "mix", "export")
    )
    result["assertions"]["A9_stage_trace"] = stage_hint
    # A9 optional — record only, do not fail smoke
    result["ok"] = True
    return result


def run_failure_path(*, voice_id: str, jobs_root: Path, timeout_s: float) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": "failure_missing_input",
        "ok": False,
        "assertions": {},
        "job_id": None,
        "error": None,
        "worker_returncode": None,
    }
    queue = FileJobQueue(jobs_root)
    missing = ROOT / "workdir" / "_gpu_smoke" / "__missing_smoke_input__.mp3"
    job = queue.enqueue_job(
        input_audio=str(missing),
        voice_id=voice_id,
        source="worker-smoke-fail",
        metadata={"smoke": True, "expect": "failed"},
    )
    job_id = job.job_id
    result["job_id"] = job_id

    proc = _run_worker(jobs_root=jobs_root, timeout_s=min(timeout_s, 120.0), skip_lock=False)
    result["worker_returncode"] = proc.returncode
    # Worker itself returns 0 after failing the job into failed/
    failed_path = queue.job_path(JobStatus.FAILED, job_id)
    result["assertions"]["F1_failed_file"] = failed_path.is_file()
    _assert(failed_path.is_file(), f"F1: missing failed/{job_id}.json")

    failed = _load_job(queue, JobStatus.FAILED, job_id)
    err = str(failed.get("error") or "")
    result["error"] = err
    readable = "找不到" in err or "输入音频" in err or "audio" in err.lower()
    result["assertions"]["F1_readable_error"] = readable and bool(err)
    _assert(readable and bool(err), f"F1: unreadable error={err!r}")

    no_completed = not queue.job_path(JobStatus.COMPLETED, job_id).exists()
    result["assertions"]["F1_no_completed"] = no_completed
    _assert(no_completed, "F1: unexpected completed job")

    result["ok"] = True
    return result


def run_lock_path(*, jobs_root: Path, timeout_s: float) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": "lock_contention",
        "ok": False,
        "assertions": {},
        "worker_returncode": None,
        "log_tail": "",
    }
    lock = WorkerLock(jobs_root / "worker.lock")
    lock.acquire()
    try:
        proc = _run_worker(jobs_root=jobs_root, timeout_s=min(timeout_s, 60.0), skip_lock=False)
    finally:
        lock.release()

    result["worker_returncode"] = proc.returncode
    log = (proc.stdout or "") + "\n" + (proc.stderr or "")
    result["log_tail"] = log[-2000:]
    # Windows may raise PermissionError reading an exclusively-opened lock file
    # before WorkerLockError is constructed; either form proves single-worker lock.
    lock_signal = (
        "lock_failed" in log
        or "another worker" in log
        or "cannot acquire" in log
        or "PermissionError" in log
        or "worker.lock" in log
    )
    ok = proc.returncode != 0 and lock_signal
    result["assertions"]["L1_second_worker_fails"] = ok
    _assert(ok, f"L1: expected lock failure, exit={proc.returncode}\n{log[-800:]}")
    result["ok"] = True
    return result


def write_report(
    *,
    report_path: Path,
    verdict: str,
    audio: Path,
    voice_id: str,
    jobs_root: Path,
    cases: list[dict[str, Any]],
    blocked_reason: str | None = None,
    error: str | None = None,
) -> None:
    happy = next((c for c in cases if c.get("name") == "happy_path"), {})
    fail = next((c for c in cases if c.get("name") == "failure_missing_input"), {})
    lock = next((c for c in cases if c.get("name") == "lock_contention"), {})

    happy_ok = bool(happy.get("ok"))
    fail_ok = bool(fail.get("ok"))
    lock_ok = bool(lock.get("ok")) if lock else False
    happy_status = "SUCCESS（真实翻唱成功）" if happy_ok else "FAIL"
    fail_status = (
        "EXPECTED FAIL（故意错误输入，验证失败收口）"
        if fail_ok
        else ("FAIL" if fail else "SKIPPED")
    )
    lock_status = (
        "EXPECTED FAIL（第二实例争锁）"
        if lock_ok
        else ("FAIL" if lock else "SKIPPED")
    )

    lines = [
        "# AIVOICE v1.3-0.3.3 — Worker E2E Smoke Report",
        "",
        f"> 日期：{time.strftime('%Y-%m-%d')}",
        f"> 依据：`aivoice_v1.3_worker_e2e_smoke_design.md`",
        f"> 总判定：**{verdict}**",
        "> 说明：本报告区分 **真实翻唱成功** 与 **故意失败路径**；"
        "后者的 error 文案不是产品执行失败。",
        "",
        "---",
        "",
        "## 1. Environment",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| audio | `{audio}` |",
        f"| voice_id | `{voice_id}` |",
        f"| jobs_root | `{jobs_root}` |",
        "| mock CoverService | **false**（真实 Worker 子进程，无 mock） |",
        f"| PYTHONPATH | `{SRC}` |",
        "",
    ]
    if blocked_reason:
        lines += ["## BLOCKED", "", blocked_reason, ""]

    lines += [
        "## 2. Happy Path — Real Worker Execution",
        "",
        f"**状态：{happy_status}**",
        "",
        "本路径使用真实音频，经真实 Worker claim → `CoverService.run` → "
        "UVR → SVC → Mix → Export，**不是**失败用例。",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 结果 | {'**成功完成**' if happy_ok else '**未通过**'} |",
        f"| job_id | `{happy.get('job_id')}` |",
        f"| wall_s | {happy.get('wall_s')} |",
        f"| worker_rc | {happy.get('worker_returncode')} |",
        f"| output_path | `{happy.get('output_path')}` |",
        f"| output_bytes | {happy.get('output_bytes')} |",
        f"| current_stage | `{happy.get('current_stage')}` |",
        f"| assertions | `{json.dumps(happy.get('assertions') or {}, ensure_ascii=False)}` |",
        "",
        "## 3. Failure Path — Intentional Missing Input",
        "",
        f"**状态：{fail_status}**",
        "",
        "本路径**故意** enqueue 不存在的 `input_audio`，用于验证 Worker 写入 `failed/` "
        "并给出可读错误。**「找不到输入音频文件。」是预期结果，不是 Happy Path 失败。**",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| 结果 | {'**按设计失败收口（用例 PASS）**' if fail_ok else '**未通过 / 跳过**'} |",
        "| 意图 | 负向用例 / 缺文件 |",
        f"| job_id | `{fail.get('job_id')}` |",
        f"| error（预期） | `{fail.get('error')}` |",
        f"| worker_rc | {fail.get('worker_returncode')} |",
        f"| assertions | `{json.dumps(fail.get('assertions') or {}, ensure_ascii=False)}` |",
        "",
        "## 4. Lock Path（可选）",
        "",
        f"**状态：{lock_status}**",
        "",
        "| 项 | 值 |",
        "|---|---|",
        f"| worker_rc | {lock.get('worker_returncode')} |",
        f"| assertions | `{json.dumps(lock.get('assertions') or {}, ensure_ascii=False)}` |",
        "",
        "## 5. 观察项",
        "",
        "- 人工听感：请打开 Happy Path `output_path` 确认可听。",
        "- Failure Path 的 error 文案仅证明失败路径，**不得**解读为冒烟整体失败。",
        "- profiling：若 Pipeline 仍写 `profiling_report.md`，可附路径。",
        "",
        "## 6. 结论",
        "",
        "| 路径 | 含义 | 本报告 |",
        "|---|---|---|",
        f"| Happy Path | 真实 Worker 翻唱成功 | **{'SUCCESS' if happy_ok else 'FAIL'}** |",
        f"| Failure Path | 故意缺文件 → 可读 fail | **{'EXPECTED FAIL（用例 PASS）' if fail_ok else 'FAIL / SKIPPED'}** |",
        f"| Lock Path | 单 Worker 锁 | **{'EXPECTED FAIL（用例 PASS）' if lock_ok else 'FAIL / SKIPPED'}** |",
        "",
        f"**总判定：{verdict}** — Hermes Skill enqueue / 飞书 outbox 仅在 PASS 后开启。",
        "",
    ]
    if error:
        lines += ["### Error", "", "```", error, "```", ""]
    report_path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Real Worker E2E smoke (no mocks)")
    p.add_argument(
        "--audio",
        type=Path,
        default=DEFAULT_AUDIO,
        help=f"Input mp3 (default: {DEFAULT_AUDIO})",
    )
    p.add_argument("--voice-id", default="example_voice_b", help="Voice id (default: example_voice_b)")
    p.add_argument(
        "--jobs-root",
        type=Path,
        default=None,
        help="Jobs root (default: <project>/jobs)",
    )
    p.add_argument(
        "--timeout-hint",
        type=float,
        default=600.0,
        help="Outer worker subprocess timeout seconds (default 600)",
    )
    p.add_argument(
        "--skip-lock-check",
        action="store_true",
        help="Skip optional second-worker lock assertion",
    )
    p.add_argument(
        "--skip-failure-path",
        action="store_true",
        help="Skip missing-input failure path",
    )
    p.add_argument(
        "--report",
        type=Path,
        default=REPORT_PATH,
        help="Markdown report path",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    audio = Path(args.audio)
    voice_id = str(args.voice_id)
    jobs_root = Path(args.jobs_root) if args.jobs_root else (ROOT / "jobs")
    timeout_s = float(args.timeout_hint)
    report_path = Path(args.report)

    cases: list[dict[str, Any]] = []
    summary: dict[str, Any] = {"ok": False, "verdict": "FAIL", "cases": cases}

    if not audio.is_file():
        write_report(
            report_path=report_path,
            verdict="BLOCKED",
            audio=audio,
            voice_id=voice_id,
            jobs_root=jobs_root,
            cases=cases,
            blocked_reason=(
                f"输入音频不存在：`{audio}`。"
                "请提供 `--audio` 或生成 `workdir/_gpu_smoke/clip30.mp3`。"
            ),
        )
        summary["verdict"] = "BLOCKED"
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    try:
        # Lock check first (fast), then failure path, then happy (slow GPU).
        if not args.skip_lock_check:
            cases.append(run_lock_path(jobs_root=jobs_root, timeout_s=timeout_s))
        if not args.skip_failure_path:
            cases.append(
                run_failure_path(voice_id=voice_id, jobs_root=jobs_root, timeout_s=timeout_s)
            )
        cases.append(
            run_happy_path(
                audio=audio,
                voice_id=voice_id,
                jobs_root=jobs_root,
                timeout_s=timeout_s,
            )
        )
    except subprocess.TimeoutExpired as exc:
        write_report(
            report_path=report_path,
            verdict="BLOCKED",
            audio=audio,
            voice_id=voice_id,
            jobs_root=jobs_root,
            cases=cases,
            blocked_reason=f"Worker 超时（{timeout_s}s）：{exc}",
            error=str(exc),
        )
        summary["verdict"] = "BLOCKED"
        summary["error"] = str(exc)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2
    except Exception as exc:
        summary["error"] = str(exc)
        write_report(
            report_path=report_path,
            verdict="FAIL",
            audio=audio,
            voice_id=voice_id,
            jobs_root=jobs_root,
            cases=cases,
            error=str(exc),
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1

    all_ok = all(c.get("ok") for c in cases)
    verdict = "PASS" if all_ok else "FAIL"
    summary["ok"] = all_ok
    summary["verdict"] = verdict
    write_report(
        report_path=report_path,
        verdict=verdict,
        audio=audio,
        voice_id=voice_id,
        jobs_root=jobs_root,
        cases=cases,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
