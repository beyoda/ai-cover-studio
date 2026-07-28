#!/usr/bin/env python3
"""Validate Hermes experience polish (search → pick → request; local still works)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
SCRIPT = Path(__file__).resolve().parent / "aivoice_cover.py"
SRC = ROOT / "src"


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = {**dict(**{k: v for k, v in __import__("os").environ.items() if k.upper() != "PYTHONPATH"})}
    env["PYTHONPATH"] = str(SRC)
    # Scrub Hermes contamination for child consistency
    for k in list(env):
        if k.upper() in {"PYTHONPATH", "VIRTUAL_ENV", "PYTHONHOME"} and k != "PYTHONPATH":
            env.pop(k, None)
    env["PYTHONPATH"] = str(SRC)
    cmd = [str(PY), str(SCRIPT), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and proc.returncode not in (0, 2):
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(f"fail rc={proc.returncode} args={args}")
    return proc


def last_json(stdout: str) -> dict:
    lines = [ln for ln in stdout.splitlines() if ln.strip().startswith("{")]
    assert lines, f"no json in stdout: {stdout!r}"
    return json.loads(lines[-1])


def main() -> int:
    print("== parse NL ==")
    p = run(["--parse", "用example_voice_b翻唱示例歌手的示例曲目"])
    data = last_json(p.stdout)
    assert data["params"].get("voice_id") == "example_voice_b"
    assert "示例曲目" in str(data["params"].get("source") or "")
    assert data["params"].get("action") == "search"
    print("ok parse")

    print("== pitch ==")
    from param_parse import parse_pitch_from_text

    assert parse_pitch_from_text("升两个key") == 2
    assert parse_pitch_from_text("降一个key") == -1
    print("ok pitch")

    print("== list voices ==")
    p = run(["--list-voices"])
    data = last_json(p.stdout)
    ids = {v["voice_id"] for v in data["voices"]}
    assert "example_voice_b" in ids and "example_voice" in ids
    assert "当前可用音色" in data.get("pretty", "")
    assert "mismatch" not in (p.stdout + p.stderr).lower()
    assert "建议换" not in p.stdout + p.stderr
    assert "容易失败" not in p.stdout + p.stderr
    print("ok voices")

    print("== search + session pick dry-run ==")
    sid = "validate_experience_glass"
    p = run(
        [
            "--session-id",
            sid,
            "--voice-id",
            "example_voice_b",
            "--search",
            "示例歌手的示例曲目",
            "--search-count",
            "5",
        ],
        check=False,
    )
    assert p.returncode == 2, p.stdout + p.stderr
    choice = last_json(p.stdout)
    assert choice["status"] == "choice_needed"
    assert choice["candidates"]
    assert choice.get("stage") == "waiting_track_choice"
    track0 = choice["candidates"][0]["track_id"]

    p2 = run(["--session-id", sid, "--pick", "1", "--dry-run"])
    ready = last_json(p2.stdout)
    assert ready["status"] == "ready_to_cover"
    req = ready["request"]
    assert req["voice_id"] == "example_voice_b"
    assert req["track_id"] == track0
    assert req.get("provider") == "gdstudio"
    # Write cover_request.json artifact
    out = Path(__file__).resolve().parent / "cover_request.json"
    out.write_text(json.dumps(req, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ok pick → {out} track_id={track0}")

    print("== local file resolve still works ==")
    sys.path.insert(0, str(SRC))
    from aivoice_studio.cover.music_source import resolve_to_audio_asset

    sample = None
    songs = ROOT / "test_songs"
    if songs.is_dir():
        for f in songs.rglob("*.mp3"):
            sample = f
            break
    if sample is None:
        # create tiny fake is not enough for cover; just ensure path resolution contract
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "x.mp3"
            fake.write_bytes(b"ID3fake")
            asset = resolve_to_audio_asset(input_path=str(fake))
            assert asset.source == "local"
    else:
        asset = resolve_to_audio_asset(input_path=str(sample))
        assert asset.source == "local"
        assert Path(asset.path).is_file()
    print("ok local")

    print("ALL validate_experience checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
