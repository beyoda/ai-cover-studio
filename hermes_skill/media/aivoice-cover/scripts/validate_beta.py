#!/usr/bin/env python3
"""Offline validation for Skill-layer NL mapping (no Hermes live chat).

Voice assertions run against a synthetic registry created in a temporary
directory and injected via ``AIVOICE_VOICES_CONFIG``: no celebrity model, no
private voice id, no maintainer path, and the user's ``config/voices.json`` is
never read or written.

The end-to-end cover check needs a real GPU runtime plus audio you are
authorized to process, so it is opt-in:

    set AIVOICE_E2E_AUDIO=C:\\path\\to\\your-authorized-track.mp3
    set AIVOICE_E2E_VOICE=alpha        # any voice registered on your machine
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import testkit  # noqa: E402
from param_parse import (  # noqa: E402
    extract_cover_params_from_utterances,
    normalize_reverb,
    normalize_voice_id,
    parse_pitch_from_text,
    parse_reverb_from_text,
)

ROOT = testkit.ROOT
COVER = testkit.COVER

SKIPPED = "SKIP"


def _ok(name: str, cond: bool, detail: str = "") -> bool:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def _skip(name: str, why: str) -> str:
    print(f"[{SKIPPED}] {name} — {why}")
    return SKIPPED


def test_voice() -> bool:
    cases = [
        ("Alpha", "alpha"),
        ("alpha", "alpha"),
        ("示例音色A", "alpha"),
        ("使用alpha模型", "alpha"),
        ("用Alpha声音翻唱", "alpha"),
        ("用示例音色B声音翻唱", "beta"),
        ("beta", "beta"),
    ]
    ok = True
    for text, expect in cases:
        got = normalize_voice_id(text)
        ok = _ok(f"voice:{text!r}", got == expect, f"got={got}") and ok
    # An unknown reference must not resolve to anything.
    ok = _ok("unknown voice resolves to None", normalize_voice_id("not-a-voice") is None) and ok
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
    # JSON shape expected by the validation prompt (bool) maps correctly for CoverRequest
    ok = _ok(
        "reverb false→关闭",
        normalize_reverb(False) == "关闭",
    ) and ok
    return ok


def test_multiturn_partial() -> bool:
    p1 = extract_cover_params_from_utterances(["我要做一个翻唱"])
    ok = _ok("multiturn incomplete has no voice", "voice_id" not in p1)
    p2 = extract_cover_params_from_utterances(["我要做一个翻唱", "示例音色A"])
    ok = _ok("multiturn 示例音色A→alpha", p2.get("voice_id") == "alpha") and ok
    return ok


def test_synthetic_registry_is_resolvable(voices_json: Path) -> bool:
    """The fixture itself must be a valid registry the skill can list."""
    proc = testkit.run_skill(["--list-voices"], voices_json=voices_json, timeout=90)
    if proc.returncode != 0:
        return _ok("fixture --list-voices", False, proc.stderr[-200:])
    data = testkit.last_json(proc.stdout)
    ids = {row["voice_id"] for row in data.get("voices", [])}
    return _ok(
        "fixture voices listed",
        ids == set(testkit.SYNTHETIC_VOICE_IDS),
        str(sorted(ids)),
    )


def _run_cover(payload: dict, voices_json: Path) -> dict:
    proc = testkit.run_skill(
        ["--json", json.dumps(payload, ensure_ascii=False)],
        voices_json=voices_json,
    )
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    data = json.loads(lines[-1]) if lines else {"status": "failed", "error": "no stdout"}
    data["_stderr"] = proc.stderr
    data["_code"] = proc.returncode
    return data


def test_errors(voices_json: Path, tmp_path: Path) -> bool:
    missing_path = Path(tempfile.gettempdir()) / "aivoice_no_such_dir" / "missing-track.mp3"
    missing = _run_cover(
        {
            "input": str(missing_path),
            "voice_id": "alpha",
            "pitch": 0,
            "options": {},
        },
        voices_json,
    )
    err = missing.get("error") or ""
    ok = _ok(
        "missing file",
        missing.get("status") == "failed"
        and "找不到音频文件" in err
        and "Traceback" not in missing.get("_stderr", "").split("error:")[0],
        err.splitlines()[0] if err else "",
    )
    # traceback must not be on stdout
    ok = _ok("no traceback on stdout for missing", "Traceback" not in json.dumps(missing)) and ok

    bad = _run_cover(
        {
            "input": str(SCRIPTS / "param_parse.py"),  # .py not audio
            "voice_id": "alpha",
            "pitch": 0,
            "options": {},
        },
        voices_json,
    )
    ok = _ok(
        "unsupported format",
        bad.get("status") == "failed"
        and "unsupported audio format" in (bad.get("error") or ""),
        bad.get("error"),
    ) and ok

    # Valid audio + unregistered voice: must fail at registry resolution, not
    # silently fall back to some default voice.
    audio = testkit.synthetic_audio(tmp_path, "unknown-voice-check.mp3")
    unknown = _run_cover(
        {
            "input": str(audio),
            "voice_id": "not-a-registered-voice",
            "pitch": 0,
            "options": {},
        },
        voices_json,
    )
    ok = _ok(
        "unregistered voice is rejected",
        unknown.get("status") == "failed" and "未识别该音色" in (unknown.get("error") or ""),
        unknown.get("error"),
    ) and ok
    return ok


def test_real_cover(voices_json: Path) -> bool | str:
    """Opt-in: needs a real runtime plus audio you hold the rights to."""
    audio_raw = (os.environ.get("AIVOICE_E2E_AUDIO") or "").strip()
    if not audio_raw:
        return _skip(
            "real cover",
            "set AIVOICE_E2E_AUDIO (and optionally AIVOICE_E2E_VOICE) to run it",
        )
    audio = Path(audio_raw).expanduser()
    if not audio.is_file():
        return _ok("real cover", False, f"audio not found: {audio}")

    voice = (os.environ.get("AIVOICE_E2E_VOICE") or "").strip() or testkit.SYNTHETIC_VOICE_IDS[0]
    data = _run_cover(
        {
            "input": str(audio),
            "voice_id": voice,
            "pitch": 0,
            "options": {"reverb": "关闭", "export_mp3": True},
        },
        voices_json,
    )
    # The skill enqueues; "queued" is the success state (see SKILL.md).
    queued_ack = '"status": "queued"' in data.get("_stderr", "") or '"status":"queued"' in data.get(
        "_stderr", ""
    )
    ok = _ok("real cover enqueued", data.get("status") == "queued", json.dumps(data, ensure_ascii=False)[:200])
    ok = _ok("queued ack on stderr", queued_ack) and ok
    return ok


def main() -> int:
    with testkit.temporary_workspace("aivoice_validate_beta_") as tmp:
        tmp_path = Path(tmp)
        voices_json = testkit.make_synthetic_registry(tmp_path)
        testkit.activate_registry(voices_json)
        print(f"synthetic registry: {voices_json}")

        results: list[tuple[str, bool | str]] = [
            ("synthetic_registry", test_synthetic_registry_is_resolvable(voices_json)),
            ("voice", test_voice()),
            ("pitch", test_pitch()),
            ("reverb", test_reverb()),
            ("multiturn", test_multiturn_partial()),
            ("errors", test_errors(voices_json, tmp_path)),
            ("real_cover", test_real_cover(voices_json)),
        ]
    print("---")
    for name, passed in results:
        state = passed if isinstance(passed, str) else ("PASS" if passed else "FAIL")
        print(f"{name}: {state}")
    return 0 if not any(passed is False for _, passed in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
