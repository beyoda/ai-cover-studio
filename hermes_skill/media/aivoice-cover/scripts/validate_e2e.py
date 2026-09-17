#!/usr/bin/env python3
"""Hermes → AIVOICE Skill local E2E checks (discovery + parse; optional real cover).

Voice data is synthetic and injected per run through ``AIVOICE_VOICES_CONFIG``,
so this works on a fresh clone with an empty ``config/voices.json`` and never
depends on a private voice id or a maintainer path.

    python validate_e2e.py              # discovery + parse + registry listing
    python validate_e2e.py --skip-cover # (default already skips the GPU cover)

To additionally exercise a real cover (needs a GPU runtime and audio you are
authorized to process):

    set AIVOICE_E2E_AUDIO=C:\\path\\to\\your-authorized-track.mp3
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import testkit  # noqa: E402
from param_parse import (  # noqa: E402
    extract_cover_params_from_utterances,
    parse_source_and_voice,
    song_display_name,
)

ROOT = testkit.ROOT
SKILL_MD = testkit.SKILL_MD
UTTERANCE = "使用Alpha声音翻唱 示例歌手 - 示例曲目.mp3"
SKIPPED = "SKIP"


def _ok(name: str, cond: bool, detail: str = "") -> bool:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def _skip(name: str, why: str) -> str:
    print(f"[{SKIPPED}] {name} — {why}")
    return SKIPPED


def check_skill_md() -> bool:
    ok = _ok("SKILL.md exists", SKILL_MD.is_file(), str(SKILL_MD))
    body = SKILL_MD.read_text(encoding="utf-8")
    ok = _ok("SKILL.md has Examples", "## Examples" in body) and ok
    ok = _ok("SKILL.md mentions cover script", "aivoice_cover.py" in body) and ok
    return ok


def check_hermes_discovery() -> bool | str:
    if shutil.which("hermes") is None:
        return _skip("Hermes discovers aivoice-cover", "the hermes CLI is not installed here")
    import subprocess

    proc = subprocess.run(
        ["hermes", "skills", "list"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    return _ok(
        "Hermes discovers aivoice-cover",
        "aivoice-cover" in text,
        f"rc={proc.returncode}",
    )


def check_param_parse() -> bool:
    parsed = parse_source_and_voice(UTTERANCE)
    ok = _ok("parse voice_id=alpha", parsed.get("voice_id") == "alpha", str(parsed))
    ok = _ok(
        "parse input filename",
        parsed.get("input") == "示例歌手 - 示例曲目.mp3",
        str(parsed),
    ) and ok
    multi = extract_cover_params_from_utterances([UTTERANCE])
    ok = _ok(
        "extract combo",
        multi.get("voice_id") == "alpha" and multi.get("input") == "示例歌手 - 示例曲目.mp3",
        str(multi),
    ) and ok
    ok = _ok("song_display 示例曲目", song_display_name("示例歌手 - 示例曲目") == "示例曲目") and ok
    ok = _ok(
        "second voice parses",
        parse_source_and_voice("用Beta翻唱这首歌").get("voice_id") == "beta",
    ) and ok
    return ok


def check_skill_list_voices(voices_json: Path) -> bool:
    proc = testkit.run_skill(["--list-voices"], voices_json=voices_json, timeout=90)
    if proc.returncode != 0:
        return _ok("skill --list-voices", False, proc.stderr[-200:])
    data = testkit.last_json(proc.stdout)
    ids = {v["voice_id"] for v in data.get("voices", [])}
    return _ok(
        "skill lists the registered voices",
        ids == set(testkit.SYNTHETIC_VOICE_IDS),
        str(sorted(ids)),
    )


def run_real_cover(voices_json: Path) -> tuple[bool | str, dict]:
    import os

    audio_raw = (os.environ.get("AIVOICE_E2E_AUDIO") or "").strip()
    if not audio_raw:
        return (
            _skip("real cover", "set AIVOICE_E2E_AUDIO to run it"),
            {},
        )
    audio = Path(audio_raw).expanduser()
    if not audio.is_file():
        return _ok("real cover", False, f"audio not found: {audio}"), {}

    voice = (os.environ.get("AIVOICE_E2E_VOICE") or "").strip() or testkit.SYNTHETIC_VOICE_IDS[0]
    payload = {
        "input": str(audio),
        "voice_id": voice,
        "pitch": 0,
        "options": {"reverb": "关闭", "export_mp3": True},
    }
    proc = testkit.run_skill(
        ["--json", json.dumps(payload, ensure_ascii=False), "--timeout", "600"],
        voices_json=voices_json,
        timeout=660,
    )
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    data: dict = {}
    if lines:
        try:
            data = json.loads(lines[-1])
        except json.JSONDecodeError:
            data = {"status": "failed", "error": "bad stdout", "raw": lines[-1]}
    data["_rc"] = proc.returncode
    data["_stderr_tail"] = (proc.stderr or "")[-1500:]

    # The skill enqueues; "queued" is the success state (see SKILL.md).
    ok = _ok(
        "real cover enqueued",
        proc.returncode == 0 and data.get("status") == "queued",
        json.dumps(
            {k: data.get(k) for k in ("status", "song", "voice", "pitch", "job_id", "error")},
            ensure_ascii=False,
        ),
    )
    return ok, data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-cover", action="store_true", help="skip the GPU cover stage")
    args = ap.parse_args()

    with testkit.temporary_workspace("aivoice_validate_e2e_") as tmp:
        voices_json = testkit.make_synthetic_registry(Path(tmp))
        testkit.activate_registry(voices_json)
        print(f"synthetic registry: {voices_json}")

        results: dict[str, bool | str | None] = {
            "skill_md": check_skill_md(),
            "hermes_discovery": check_hermes_discovery(),
            "param_parse": check_param_parse(),
            "skill_list_voices": check_skill_list_voices(voices_json),
        }
        cover_data: dict = {}
        if args.skip_cover:
            results["real_cover"] = None
        else:
            results["real_cover"], cover_data = run_real_cover(voices_json)

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
    # workdir/ is git-ignored; keep the JSON there so the tree stays clean.
    out_path = ROOT / "workdir" / "hermes_e2e_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    fails = [k for k, v in results.items() if v is False]
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
