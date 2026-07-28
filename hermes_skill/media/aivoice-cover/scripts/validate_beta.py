"""Offline validation for Skill-layer NL mapping (no Hermes live chat)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from param_parse import (  # noqa: E402
    extract_cover_params_from_utterances,
    normalize_reverb,
    normalize_voice_id,
    parse_pitch_from_text,
    parse_reverb_from_text,
)

ROOT = SCRIPTS.parents[3]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
COVER = SCRIPTS / "aivoice_cover.py"


def _ok(name: str, cond: bool, detail: str = "") -> bool:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def test_voice() -> bool:
    cases = [
        ("示例歌手", "example_voice"),
        ("ExampleVoice", "example_voice"),
        ("example_voice", "example_voice"),
        ("使用example_voice模型", "example_voice"),
        ("用ExampleVoice声音翻唱", "example_voice"),
        ("用示例歌手音色唱", "example_voice"),
        ("用example_voice_b声音翻唱", "example_voice_b"),
        ("example_voice_b", "example_voice_b"),
    ]
    ok = True
    for text, expect in cases:
        got = normalize_voice_id(text)
        ok = _ok(f"voice:{text!r}", got == expect, f"got={got}") and ok
    return ok


def test_pitch() -> bool:
    cases = [
        ("升两个key", 2),
        ("升2个调", 2),
        ("pitch +2", 2),
        ("降一个key", -1),
    ]
    ok = True
    for text, expect in cases:
        got = parse_pitch_from_text(text)
        ok = _ok(f"pitch:{text!r}", got == expect, f"got={got}") and ok
    return ok


def test_reverb() -> bool:
    ok = True
    ok = _ok("reverb off phrase", parse_reverb_from_text("不要混响") == "关闭") and ok
    ok = _ok("reverb off phrase2", parse_reverb_from_text("关闭reverb") == "关闭") and ok
    ok = _ok("reverb on phrase", parse_reverb_from_text("打开混响") == "录音棚") and ok
    ok = _ok("reverb bool false", normalize_reverb(False) == "关闭") and ok
    ok = _ok("reverb bool true", normalize_reverb(True) == "录音棚") and ok
    # JSON shape expected by validation prompt (bool) maps correctly for CoverRequest
    ok = _ok(
        "reverb false→关闭",
        normalize_reverb(False) == "关闭",
    ) and ok
    return ok


def test_multiturn_partial() -> bool:
    p1 = extract_cover_params_from_utterances(["我要做一个翻唱"])
    ok = _ok("multiturn incomplete has no voice", "voice_id" not in p1)
    p2 = extract_cover_params_from_utterances(["我要做一个翻唱", "示例歌手"])
    ok = _ok("multiturn 示例歌手→example_voice", p2.get("voice_id") == "example_voice") and ok
    return ok


def _run_cover(payload: dict) -> dict:
    proc = subprocess.run(
        [str(PY), str(COVER), "--json", json.dumps(payload, ensure_ascii=False)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(ROOT),
    )
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    data = json.loads(lines[-1]) if lines else {"status": "failed", "error": "no stdout"}
    data["_stderr"] = proc.stderr
    data["_code"] = proc.returncode
    return data


def test_errors() -> bool:
    missing = _run_cover(
        {"input": r"D:\not_exist.mp3", "voice_id": "example_voice", "pitch": 0, "options": {}}
    )
    err = missing.get("error") or ""
    ok = _ok(
        "missing file",
        missing.get("status") == "failed"
        and ("file not found" in err or "not found" in err.lower())
        and "Traceback" not in missing.get("_stderr", "").split("error:")[0],
        missing.get("error"),
    )
    # traceback must not be on stdout
    ok = _ok("no traceback on stdout for missing", "Traceback" not in json.dumps(missing)) and ok

    bad = _run_cover(
        {
            "input": str(SCRIPTS / "param_parse.py"),  # .py not audio
            "voice_id": "example_voice",
            "pitch": 0,
            "options": {},
        }
    )
    ok = _ok(
        "unsupported format",
        bad.get("status") == "failed"
        and "unsupported audio format" in (bad.get("error") or ""),
        bad.get("error"),
    ) and ok
    return ok


def test_real_cover() -> bool:
    audio = ROOT / "test_songs" / "示例歌手 - 示例曲目.mp3"
    if not audio.is_file():
        return _ok("real cover", False, "test song missing")
    data = _run_cover(
        {
            "input": str(audio),
            "voice_id": "example_voice",
            "pitch": 0,
            "options": {"reverb": False, "export_mp3": True},
        }
    )
    out = data.get("output_path")
    path_ok = bool(out) and Path(out).is_file() and Path(out).stat().st_size > 1000
    queued_ack = '"status": "queued"' in data.get("_stderr", "") or '"status":"queued"' in data.get(
        "_stderr", ""
    )
    ok = _ok("real cover completed", data.get("status") == "completed" and path_ok, str(out))
    ok = _ok("queued ack on stderr", queued_ack) and ok
    return ok


def main() -> int:
    results = [
        ("voice", test_voice()),
        ("pitch", test_pitch()),
        ("reverb", test_reverb()),
        ("multiturn", test_multiturn_partial()),
        ("errors", test_errors()),
        ("real_cover", test_real_cover()),
    ]
    print("---")
    for name, passed in results:
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
    return 0 if all(p for _, p in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
