#!/usr/bin/env python3
"""Hermes → AIVOICE Skill local E2E checks (discovery + parse; optional real cover)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
sys.path.insert(0, str(SCRIPTS))

from param_parse import (  # noqa: E402
    extract_cover_params_from_utterances,
    parse_source_and_voice,
    song_display_name,
)

PY = ROOT / ".venv" / "Scripts" / "python.exe"
COVER = SCRIPTS / "aivoice_cover.py"
SKILL_MD = SCRIPTS.parent / "SKILL.md"
UTTERANCE = "使用示例歌手声音翻唱 示例歌手 - 示例曲目.mp3"


def _ok(name: str, cond: bool, detail: str = "") -> bool:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def check_hermes_discovery() -> bool:
    ok = True
    proc = subprocess.run(
        ["hermes", "skills", "list"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    ok = _ok("Hermes discovers aivoice-cover", "aivoice-cover" in text, f"rc={proc.returncode}") and ok
    ok = _ok("SKILL.md exists", SKILL_MD.is_file(), str(SKILL_MD)) and ok
    body = SKILL_MD.read_text(encoding="utf-8")
    ok = _ok("SKILL.md has Examples", "## Examples" in body) and ok
    ok = _ok("SKILL.md mentions cover script", "aivoice_cover.py" in body) and ok
    return ok


def check_param_parse() -> bool:
    parsed = parse_source_and_voice(UTTERANCE)
    ok = _ok("parse voice_id=example_voice", parsed.get("voice_id") == "example_voice", str(parsed))
    ok = _ok(
        "parse input filename",
        parsed.get("input") == "示例歌手 - 示例曲目.mp3",
        str(parsed),
    ) and ok
    multi = extract_cover_params_from_utterances([UTTERANCE])
    ok = _ok(
        "extract combo",
        multi.get("voice_id") == "example_voice" and multi.get("input") == "示例歌手 - 示例曲目.mp3",
        str(multi),
    ) and ok
    ok = _ok("song_display 示例曲目", song_display_name("示例歌手 - 示例曲目") == "示例曲目") and ok
    ok = _ok(
        "ExampleVoiceB example parse",
        parse_source_and_voice("用ExampleVoiceB翻唱这首歌").get("voice_id") == "example_voice_b",
    ) and ok
    return ok


def check_skill_list_voices() -> bool:
    proc = subprocess.run(
        [str(PY), str(COVER), "--list-voices"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
    )
    if proc.returncode != 0:
        return _ok("skill --list-voices", False, proc.stderr[-200:])
    data = json.loads(proc.stdout.strip().splitlines()[-1])
    ids = {v["voice_id"] for v in data.get("voices", [])}
    return _ok("skill lists example_voice+example_voice_b", ids >= {"example_voice", "example_voice_b"}, str(ids))


def run_real_cover() -> tuple[bool, dict]:
    payload = {
        "input": "示例歌手 - 示例曲目.mp3",
        "voice_id": "example_voice",
        "pitch": 0,
        "options": {"reverb": "关闭", "export_mp3": True},
    }
    t0 = time.time()
    proc = subprocess.run(
        [str(PY), str(COVER), "--json", json.dumps(payload, ensure_ascii=False), "--timeout", "600"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
    )
    elapsed = time.time() - t0
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    data: dict = {}
    if lines:
        try:
            data = json.loads(lines[-1])
        except json.JSONDecodeError:
            data = {"status": "failed", "error": "bad stdout", "raw": lines[-1]}
    data["_elapsed_wall"] = round(elapsed, 1)
    data["_rc"] = proc.returncode
    data["_stderr_tail"] = (proc.stderr or "")[-1500:]

    out = data.get("output_path")
    ok = (
        proc.returncode == 0
        and data.get("status") == "completed"
        and bool(out)
        and Path(str(out)).is_file()
        and data.get("voice") == "示例歌手"
        and data.get("song") == "示例曲目"
    )
    _ok("real CoverService e2e", ok, json.dumps({k: data.get(k) for k in (
        "status", "song", "voice", "pitch", "duration", "output_path", "job_id", "error"
    )}, ensure_ascii=False))
    return ok, data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-cover", action="store_true")
    args = ap.parse_args()

    results = {
        "hermes_discovery": check_hermes_discovery(),
        "param_parse": check_param_parse(),
        "skill_list_voices": check_skill_list_voices(),
    }
    cover_data: dict = {}
    if not args.skip_cover:
        results["real_cover"], cover_data = run_real_cover()
    else:
        results["real_cover"] = None

    summary = {
        "results": results,
        "utterance": UTTERANCE,
        "cover": {
            k: cover_data.get(k)
            for k in ("status", "song", "voice", "pitch", "duration", "output_path", "job_id", "error")
        }
        if cover_data
        else None,
    }
    out_path = ROOT / "workdir" / "hermes_e2e_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    fails = [k for k, v in results.items() if v is False]
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
