#!/usr/bin/env python3
"""Validate the Hermes cover experience offline: parse → pick → enqueue → status.

Every fixture is synthetic and lives in a temporary directory:

* voices come from a generated registry injected via ``AIVOICE_VOICES_CONFIG``,
* the session store is redirected via ``AIVOICE_HERMES_SESSIONS_DIR``,
* the job queue is redirected via ``AIVOICE_JOBS_DIR``,
* the detached worker/notifier kick is suppressed via
  ``AIVOICE_SKIP_PIPELINE_KICK``.

So this script never reads or writes the user's ``config/voices.json``, never
leaves files in the cloned repository, and never processes real audio.

The only step that needs the network is the live GD音乐台 search, which is
opt-in:

    set AIVOICE_E2E_SEARCH=1
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import testkit  # noqa: E402

ROOT = testkit.ROOT
SKIPPED = "SKIP"


def _ok(name: str, cond: bool, detail: str = "") -> bool:
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    return cond


def _skip(name: str, why: str) -> str:
    print(f"[{SKIPPED}] {name} — {why}")
    return SKIPPED


def _run(args: list[str], voices_json: Path, **kwargs) -> tuple[int, dict, str]:
    proc = testkit.run_skill(args, voices_json=voices_json, **kwargs)
    try:
        data = testkit.last_json(proc.stdout)
    except AssertionError:
        data = {}
    return proc.returncode, data, proc.stdout + proc.stderr


# --------------------------------------------------------------------------- #
# 1. natural-language parsing (offline)
# --------------------------------------------------------------------------- #
def test_parse_nl(voices_json: Path) -> bool:
    code, data, raw = _run(
        ["--parse", "用示例音色A翻唱 示例歌手 - 示例曲目"],
        voices_json,
    )
    params = data.get("params") or {}
    ok = _ok("parse rc=0", code == 0, str(code))
    ok = _ok("parse voice_id", params.get("voice_id") == "alpha", str(params.get("voice_id"))) and ok
    ok = _ok("parse source keeps title", "示例曲目" in str(params.get("source") or ""), str(params.get("source"))) and ok
    ok = _ok("parse action=search", params.get("action") == "search", str(params.get("action"))) and ok
    ok = _ok("parse has no traceback", "Traceback" not in raw) and ok

    # An unregistered voice must not be invented.
    _, data2, _ = _run(["--parse", "用不存在音色翻唱 示例曲目"], voices_json)
    p2 = data2.get("params") or {}
    ok = _ok(
        "parse unknown voice stays unresolved",
        p2.get("voice_id") in (None, ""),
        str(p2.get("voice_id")),
    ) and ok
    return ok


def test_pitch() -> bool:
    from param_parse import parse_pitch_from_text

    cases = [("升两个key", 2), ("降一个key", -1)]
    ok = True
    for text, expect in cases:
        got = parse_pitch_from_text(text)
        ok = _ok(f"pitch:{text!r}", got == expect, f"got={got}") and ok
    return ok


# --------------------------------------------------------------------------- #
# 2. voice listing (offline, registry-backed)
# --------------------------------------------------------------------------- #
def test_list_voices(voices_json: Path) -> bool:
    code, data, raw = _run(["--list-voices"], voices_json)
    ids = {row.get("voice_id") for row in data.get("voices", [])}
    pretty = str(data.get("pretty") or "")
    ok = _ok("list-voices rc=0", code == 0, str(code))
    ok = _ok("registry ids round-trip", ids == set(testkit.SYNTHETIC_VOICE_IDS), str(sorted(ids))) and ok
    ok = _ok("pretty is user-facing", "当前可用音色" in pretty, pretty.splitlines()[:1]) and ok
    # The skill must not editorialise about a voice's stability.
    ok = _ok("no discouraging wording", "容易失败" not in raw and "建议换" not in raw) and ok
    ok = _ok("no mismatch warning", "mismatch" not in raw.lower()) and ok
    return ok


# --------------------------------------------------------------------------- #
# 3. search → pick → request (session state, offline dry-run)
# --------------------------------------------------------------------------- #
def _seed_waiting_session(session_id: str, *, voice_id: str) -> str:
    from session_state import save_waiting_track_choice

    candidates = [
        {
            "track_id": "1000000001",
            "name": "示例曲目",
            "artist": "示例歌手",
            "album": "示例专辑",
            "label": "示例曲目 - 示例歌手",
        },
        {
            "track_id": "1000000002",
            "name": "示例曲目二",
            "artist": "示例歌手",
            "album": "示例专辑",
            "label": "示例曲目二 - 示例歌手",
        },
    ]
    save_waiting_track_choice(
        session_id,
        query="示例曲目",
        voice_id=voice_id,
        pitch=0,
        candidates=candidates,
    )
    return candidates[0]["track_id"]


def test_pick_dry_run(voices_json: Path) -> bool:
    sid = "validate_experience_pick"
    track0 = _seed_waiting_session(sid, voice_id="alpha")

    code, data, raw = _run(["--session-id", sid, "--pick", "1", "--dry-run"], voices_json)
    req = data.get("request") or {}
    ok = _ok("pick dry-run rc=0", code == 0, str(code))
    ok = _ok("pick status", data.get("status") == "ready_to_cover", str(data.get("status"))) and ok
    ok = _ok("pick voice from session", req.get("voice_id") == "alpha", str(req.get("voice_id"))) and ok
    ok = _ok("pick track_id", req.get("track_id") == track0, str(req.get("track_id"))) and ok
    ok = _ok("pick provider", req.get("provider") == "gdstudio", str(req.get("provider"))) and ok
    ok = _ok("pick has no traceback", "Traceback" not in raw) and ok

    # An out-of-range index must be rejected, not silently defaulted.
    code2, data2, _ = _run(["--session-id", sid, "--pick", "99", "--dry-run"], voices_json)
    ok = _ok(
        "pick rejects unknown index",
        code2 == 1 and data2.get("status") == "failed",
        f"rc={code2} status={data2.get('status')}",
    ) and ok
    return ok


def test_parse_digit_uses_session(voices_json: Path) -> bool:
    sid = "validate_experience_digit"
    _seed_waiting_session(sid, voice_id="beta")
    code, data, _ = _run(["--session-id", sid, "--parse", "2"], voices_json)
    params = data.get("params") or {}
    ok = _ok("digit parse rc=0", code == 0, str(code))
    ok = _ok("digit maps to pick", params.get("action") == "pick", str(params.get("action"))) and ok
    ok = _ok("digit carries session voice", params.get("voice_id") == "beta", str(params.get("voice_id"))) and ok
    return ok


# --------------------------------------------------------------------------- #
# 4. job submission + status query (real queue code, temp queue root)
# --------------------------------------------------------------------------- #
def test_enqueue_and_status(voices_json: Path, audio: Path) -> bool:
    code, data, raw = _run(
        ["--json", json.dumps({"input": str(audio), "voice_id": "alpha", "pitch": 0}, ensure_ascii=False)],
        voices_json,
    )
    job_id = str(data.get("job_id") or "")
    ok = _ok("enqueue rc=0", code == 0, str(code))
    ok = _ok("enqueue status=queued", data.get("status") == "queued", str(data.get("status"))) and ok
    ok = _ok("enqueue returns job_id", bool(job_id), job_id) and ok
    ok = _ok("enqueue voice display name", data.get("voice") == "Alpha", str(data.get("voice"))) and ok
    ok = _ok("enqueue has ack copy", bool(str(data.get("user_message") or "").strip())) and ok
    ok = _ok("enqueue has no traceback", "Traceback" not in raw) and ok

    # Status query: the job record must be readable from the queue the skill used.
    sys.path.insert(0, str(ROOT / "src"))
    from aivoice_studio.worker.queue import FileJobQueue

    try:
        queue = FileJobQueue()
        path = queue.find_job_path(job_id)
    except Exception as exc:  # pragma: no cover - surfaced as a failure
        return _ok("queue readable", False, f"{type(exc).__name__}: {exc}")

    ok = _ok("job file exists in the queue root", path is not None, str(path)) and ok
    if path is not None:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        ok = _ok("job voice_id persisted", record.get("voice_id") == "alpha", str(record.get("voice_id"))) and ok
        ok = _ok(
            "job input_audio persisted",
            Path(str(record.get("input_audio") or "")).name == audio.name,
            str(record.get("input_audio")),
        ) and ok

    # The queue must have been redirected away from the repository.
    queue_root = json.dumps(str(getattr(queue, "root", "")))
    ok = _ok(
        "queue root is the temp override",
        testkit.jobs_dir(voices_json).as_posix() in queue_root.replace("\\\\", "/").replace("\\", "/"),
        queue_root,
    ) and ok
    return ok


# --------------------------------------------------------------------------- #
# 5. local file resolution contract (offline)
# --------------------------------------------------------------------------- #
def test_local_source(audio: Path, voices_json: Path) -> bool:
    sys.path.insert(0, str(ROOT / "src"))
    from aivoice_studio.cover.music_source import MusicSourceError, resolve_to_audio_asset

    asset = resolve_to_audio_asset(input_path=str(audio))
    ok = _ok("local asset source", asset.source == "local", asset.source)
    ok = _ok("local asset exists", Path(asset.path).is_file(), asset.path) and ok

    missing = Path(audio).parent / "no-such-track.mp3"
    try:
        resolve_to_audio_asset(input_path=str(missing))
        ok = _ok("missing local file rejected", False, "no exception") and ok
    except MusicSourceError as exc:
        ok = _ok("missing local file rejected", "not found" in str(exc).lower(), str(exc)) and ok
    return ok


# --------------------------------------------------------------------------- #
# 6. live search (opt-in, needs network)
# --------------------------------------------------------------------------- #
def test_live_search(voices_json: Path) -> bool | str:
    if (os.environ.get("AIVOICE_E2E_SEARCH") or "").strip() in ("", "0"):
        return _skip("live GD音乐台 search", "set AIVOICE_E2E_SEARCH=1 to run it")
    code, data, raw = _run(
        ["--session-id", "validate_experience_live", "--voice-id", "alpha", "--search", "示例", "--search-count", "3"],
        voices_json,
    )
    if code == 1:
        return _ok("live search", False, str(data.get("error")))
    ok = _ok("live search needs a choice", code == 2, str(code))
    ok = _ok("live search returns candidates", bool(data.get("candidates")), str(len(data.get("candidates") or []))) and ok
    ok = _ok("live search has no traceback", "Traceback" not in raw) and ok
    return ok


def main() -> int:
    with testkit.temporary_workspace("aivoice_validate_experience_") as tmp:
        tmp_path = Path(tmp)
        voices_json = testkit.make_synthetic_registry(tmp_path)
        testkit.activate_registry(voices_json)
        audio = testkit.synthetic_audio(tmp_path)
        # Session helpers are imported after the env override is in place.
        sys.path.insert(0, str(SCRIPTS))
        print(f"synthetic registry: {voices_json}")
        print(f"synthetic audio:    {audio}")

        results: list[tuple[str, bool | str]] = [
            ("parse_nl", test_parse_nl(voices_json)),
            ("pitch", test_pitch()),
            ("list_voices", test_list_voices(voices_json)),
            ("pick_dry_run", test_pick_dry_run(voices_json)),
            ("parse_digit", test_parse_digit_uses_session(voices_json)),
            ("local_source", test_local_source(audio, voices_json)),
            ("enqueue_and_status", test_enqueue_and_status(voices_json, audio)),
            ("live_search", test_live_search(voices_json)),
        ]
    print("---")
    for name, passed in results:
        state = passed if isinstance(passed, str) else ("PASS" if passed else "FAIL")
        print(f"{name}: {state}")
    return 0 if not any(passed is False for _, passed in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
