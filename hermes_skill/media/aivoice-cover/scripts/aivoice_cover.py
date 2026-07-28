#!/usr/bin/env python3
"""AIVOICE Hermes Skill runner — Voice Registry is the only voice source."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from param_parse import (
    extract_cover_params_from_utterances,
    normalize_reverb,
    normalize_voice_id,
    parse_choice_token,
    song_display_name,
)
from session_state import (
    build_cover_request_from_pick,
    clear_session,
    load_session,
    resolve_pick,
    save_waiting_track_choice,
)
from user_messages import (
    QUEUED_ACK,
    format_cover_ack,
    format_voices_help,
    friendly_error,
)

AIVOICE_ROOT = Path(__file__).resolve().parents[4]
SRC = AIVOICE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def resolve_feishu_chat_id(
    req: dict[str, Any] | None = None,
    *,
    cli_chat_id: str | None = None,
    session_id: str | None = None,
) -> str | None:
    """Delivery target for Notifier.

    Priority: explicit feishu_chat_id → CLI → session_id (oc_/ou_) →
    latest Feishu inbound from Hermes gateway.log (when Hermes forgot --session-id).
    """
    req = req or {}
    options = req.get("options") if isinstance(req.get("options"), dict) else {}
    for raw in (
        req.get("feishu_chat_id"),
        options.get("feishu_chat_id") if options else None,
        cli_chat_id,
    ):
        if raw is not None and str(raw).strip():
            return str(raw).strip()
    sid = (session_id or "").strip()
    if sid.startswith("oc_") or sid.startswith("ou_"):
        return sid
    inferred = _infer_delivery_id_from_gateway_log()
    if inferred:
        _log(f"delivery_id_inferred_from_gateway_log={inferred}")
    return inferred


def _infer_delivery_id_from_gateway_log() -> str | None:
    """Best-effort: last Feishu inbound chat_id (oc_) or sender (ou_)."""
    import re

    log = Path(os.environ.get("LOCALAPPDATA") or "") / "hermes" / "logs" / "gateway.log"
    if not log.is_file():
        return None
    try:
        # Read only the tail to keep Skill enqueue fast.
        data = log.read_bytes()
        text = data[-256_000:].decode("utf-8", errors="replace")
    except OSError:
        return None
    chat = None
    user = None
    for line in text.splitlines():
        if "Inbound dm message received" not in line and "inbound message:" not in line:
            continue
        m_chat = re.search(r"chat_id=(oc_[a-zA-Z0-9]+)", line) or re.search(
            r"chat=(oc_[a-zA-Z0-9]+)", line
        )
        m_user = re.search(r"sender=user:(ou_[a-zA-Z0-9]+)", line) or re.search(
            r"user=(ou_[a-zA-Z0-9]+)", line
        )
        if m_chat:
            chat = m_chat.group(1)
        if m_user:
            user = m_user.group(1)
    # Prefer open_id for DM delivery reliability; fall back to chat_id.
    return user or chat


def _kick_cover_pipeline() -> None:
    """Fire-and-forget on-demand worker+notifier. Never raise to caller."""
    script = AIVOICE_ROOT / "scripts" / "kick_cover_pipeline.py"
    py = AIVOICE_ROOT / ".venv" / "Scripts" / "python.exe"
    if not script.is_file():
        _log(f"kick_skip missing_script={script}")
        return
    exe = str(py) if py.is_file() else sys.executable
    try:
        kwargs: dict[str, Any] = {
            "args": [exe, str(script)],
            "cwd": str(AIVOICE_ROOT),
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            # Detach from Hermes/Skill console; do not wait.
            kwargs["creationflags"] = (
                getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            )
            kwargs["close_fds"] = True
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(**kwargs)
        _log(f"kick_started script={script.name}")
    except Exception as exc:
        _log(f"kick_failed error={exc}")


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _fail(
    job_id: str | None,
    error: Any,
    status: str = "failed",
    *,
    song: str | None = None,
    voice: str | None = None,
    pitch: int | None = None,
    duration: str | None = None,
) -> int:
    msg = friendly_error(error)
    payload: dict[str, Any] = {
        "status": status,
        "job_id": job_id,
        "output_path": None,
        "error": msg.strip(),
        "user_message": msg,
    }
    if song is not None:
        payload["song"] = song
    if voice is not None:
        payload["voice"] = voice
    if pitch is not None:
        payload["pitch"] = pitch
    if duration is not None:
        payload["duration"] = duration
    _emit(payload)
    print(msg, file=sys.stderr, flush=True)
    return 1


def _load_request(args: argparse.Namespace) -> dict[str, Any]:
    if args.json_file:
        return json.loads(Path(args.json_file).read_text(encoding="utf-8"))
    if args.json:
        return json.loads(args.json)
    if not sys.stdin.isatty():
        raw = sys.stdin.read()
        if raw.strip():
            return json.loads(raw)
    raise ValueError("Provide --json, --json-file, or JSON on stdin")


def cmd_list_voices() -> int:
    from aivoice_studio.cover.voice_registry import get_voice_registry

    reg = get_voice_registry(reload=True)
    voices = []
    for row in reg.to_public_list():
        meta = dict(row.get("metadata") or {})
        meta.pop("notes", None)  # keep internal ops notes out of Feishu UX
        voices.append(
            {
                "voice_id": row.get("voice_id"),
                "display_name": row.get("display_name"),
                "description": row.get("description"),
                "metadata": meta,
            }
        )
    pretty = format_voices_help(voices)
    payload = {
        "status": "ok",
        "voices": voices,
        "pretty": pretty,
        "user_message": pretty,
    }
    _emit(payload)
    print(pretty, file=sys.stderr, flush=True)
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    text = (args.parse or "").strip()
    params = extract_cover_params_from_utterances([text] if text else [])
    # If session waiting and user sent a digit, mark pick
    if args.session_id and parse_choice_token(text):
        sess = load_session(args.session_id)
        if sess and sess.get("stage") == "waiting_track_choice":
            params["action"] = "pick"
            params["choice"] = parse_choice_token(text)
            if sess.get("voice_id") and "voice_id" not in params:
                params["voice_id"] = sess["voice_id"]
    if params.get("source") and not params.get("input") and params.get("action") != "pick":
        params.setdefault("action", "search")
    _emit({"status": "parsed", "params": params})
    return 0


def _emit_choice(
    *,
    query: str,
    candidates: list[dict[str, Any]],
    voice_id: str | None,
    session_id: str | None,
    pitch: int = 0,
    feishu_chat_id: str | None = None,
) -> int:
    from param_parse import format_song_choices

    if session_id:
        save_waiting_track_choice(
            session_id,
            query=query,
            voice_id=voice_id,
            pitch=pitch,
            candidates=candidates,
            feishu_chat_id=feishu_chat_id,
        )
    pretty = format_song_choices(candidates, query=query, voice_hint=voice_id or "")
    payload = {
        "status": "choice_needed",
        "query": query,
        "provider": "gdstudio",
        "attribution": "GD音乐台 (music.gdstudio.xyz)",
        "message": f"搜「{query}」找到 {len(candidates)} 首，请回复序号或 track_id",
        "pretty": pretty,
        "user_message": pretty,
        "candidates": candidates,
        "voice_id": voice_id,
        "session_id": session_id,
        "feishu_chat_id": feishu_chat_id,
        "stage": "waiting_track_choice",
    }
    _emit(payload)
    print(pretty, file=sys.stderr, flush=True)
    return 2


def cmd_search(args: argparse.Namespace) -> int:
    from aivoice_studio.cover.music_source import search_songs

    query = (args.search or "").strip()
    if not query:
        return _fail(None, "empty search query")
    voice_id = normalize_voice_id(args.voice_id) if args.voice_id else None
    try:
        pitch = int(args.pitch) if args.pitch is not None else 0
    except (TypeError, ValueError):
        pitch = 0
    chat_id = resolve_feishu_chat_id(
        cli_chat_id=getattr(args, "feishu_chat_id", None),
        session_id=args.session_id,
    )
    try:
        rows = search_songs(query, count=int(args.search_count))
    except Exception as exc:
        return _fail(None, exc)
    if not rows:
        return _fail(None, f"gdstudio: no search results for {query!r}")
    candidates = [c.to_dict() for c in rows]
    return _emit_choice(
        query=query,
        candidates=candidates,
        voice_id=voice_id,
        session_id=args.session_id,
        pitch=pitch,
        feishu_chat_id=chat_id,
    )


def cmd_pick(args: argparse.Namespace) -> int:
    sid = (args.session_id or "").strip()
    if not sid:
        return _fail(None, "选择歌曲需要 --session-id")
    sess = load_session(sid)
    if not sess or sess.get("stage") != "waiting_track_choice":
        return _fail(None, "当前没有待选歌曲，请先搜索歌名。")
    try:
        chosen = resolve_pick(sess, args.pick)
    except ValueError as exc:
        return _fail(None, exc)

    voice_override = normalize_voice_id(args.voice_id) if args.voice_id else None
    try:
        pitch_override = int(args.pitch) if args.pitch is not None else None
    except (TypeError, ValueError):
        pitch_override = None

    req = build_cover_request_from_pick(
        sess,
        chosen,
        voice_id=voice_override,
        pitch=pitch_override,
    )
    chat_id = resolve_feishu_chat_id(
        req,
        cli_chat_id=getattr(args, "feishu_chat_id", None) or sess.get("feishu_chat_id"),
        session_id=sid,
    )
    if chat_id:
        req["feishu_chat_id"] = chat_id
    # Persist covering stage briefly
    from session_state import save_session

    save_session(
        sid,
        {
            **sess,
            "stage": "covering",
            "track_id": req["track_id"],
            "voice_id": req["voice_id"],
            "pitch": req["pitch"],
            "feishu_chat_id": chat_id,
        },
    )
    if args.dry_run:
        _emit(
            {
                "status": "ready_to_cover",
                "request": req,
                "session_id": sid,
                "feishu_chat_id": chat_id,
            }
        )
        return 0
    return run_cover_request(
        req,
        session_id=sid,
        cli_feishu_chat_id=getattr(args, "feishu_chat_id", None),
    )


def cmd_cover(args: argparse.Namespace) -> int:
    try:
        req = _load_request(args)
    except Exception as exc:
        return _fail(None, f"invalid request JSON: {exc}")
    return run_cover_request(
        req,
        session_id=args.session_id,
        cli_feishu_chat_id=getattr(args, "feishu_chat_id", None),
    )


def run_cover_request(
    req: dict[str, Any],
    *,
    session_id: str | None = None,
    cli_feishu_chat_id: str | None = None,
) -> int:
    """Resolve audio + validate voice, then enqueue FS job (no CoverService poll)."""
    t0 = time.time()
    try:
        voice_raw = req.get("voice_id")
        voice_id = normalize_voice_id(str(voice_raw) if voice_raw is not None else None)
        if voice_id is None and voice_raw:
            voice_id = str(voice_raw).strip()

        try:
            pitch = int(req.get("pitch") or 0)
        except (TypeError, ValueError):
            return _fail(None, "invalid pitch")

        options = req.get("options") or {}
        if not isinstance(options, dict):
            return _fail(None, "options must be an object")

        if not voice_id:
            return _fail(None, "unknown voice")

        from aivoice_studio.cover.music_source import (
            MusicSourceChoiceNeeded,
            MusicSourceError,
            resolve_to_audio_asset,
        )
        from aivoice_studio.cover.voice_registry import VoiceRegistryError, get_voice_registry
        from aivoice_studio.cover.voice_request import build_cover_request_for_voice
        from aivoice_studio.worker.queue import FileJobQueue, JobQueueError

        source_query = req.get("source") or req.get("source_query")
        provider = req.get("provider") or (options.get("provider") if options else None)
        track_id = req.get("track_id") or options.get("track_id")
        try:
            audio = resolve_to_audio_asset(
                input_path=str(req.get("input") or "") or None,
                source=str(source_query) if source_query else None,
                provider=str(provider) if provider else None,
                track_id=str(track_id) if track_id else None,
            )
        except MusicSourceChoiceNeeded as exc:
            chat_id = resolve_feishu_chat_id(
                req,
                cli_chat_id=cli_feishu_chat_id,
                session_id=session_id,
            )
            return _emit_choice(
                query=exc.query,
                candidates=[c.to_dict() for c in exc.candidates],
                voice_id=str(voice_id),
                session_id=session_id,
                pitch=pitch,
                feishu_chat_id=chat_id,
            )
        except MusicSourceError as exc:
            return _fail(None, exc)

        song = song_display_name(
            str(req.get("chosen_name") or audio.title or Path(audio.path).stem)
        )
        track_label = req.get("chosen_label") or (
            f"{req.get('chosen_name')} - {req.get('chosen_artist')}"
            if req.get("chosen_name")
            else None
        )
        _log(f"music_source={audio.source} path={audio.path} title={audio.title} song={song}")

        queue_options = {
            "reverb": normalize_reverb(options.get("reverb", "关闭")),
            "f0_method": str(options.get("f0_method", "rmvpe")),
            "export_mp3": bool(options.get("export_mp3", True)),
            "accompaniment": str(options.get("accompaniment") or ""),
        }

        registry = get_voice_registry()
        try:
            _cover_req, asset = build_cover_request_for_voice(
                input_audio=audio.path,
                voice_id=str(voice_id),
                pitch=pitch,
                reverb=queue_options["reverb"],
                f0_method=queue_options["f0_method"],
                export_mp3=bool(queue_options["export_mp3"]),
                accompaniment=str(queue_options["accompaniment"]),
                client="hermes",
                request_id=options.get("request_id"),
                registry=registry,
            )
        except VoiceRegistryError:
            return _fail(None, "unknown voice", song=song, pitch=pitch)

        voice_label = asset.display_name or asset.voice_id
        ack = format_cover_ack(song=song, voice=voice_label, track_label=track_label)
        print(ack, file=sys.stderr, flush=True)

        feishu_chat_id = resolve_feishu_chat_id(
            req,
            cli_chat_id=cli_feishu_chat_id,
            session_id=session_id,
        )
        requester = req.get("requester") or options.get("requester")
        metadata = {
            "song": song,
            "voice": voice_label,
            "track_label": track_label,
            "client": "hermes",
        }
        if options.get("request_id") is not None:
            metadata["request_id"] = options.get("request_id")

        try:
            job = FileJobQueue().enqueue_job(
                input_audio=str(audio.path),
                voice_id=str(voice_id),
                pitch=pitch,
                options=queue_options,
                source=str(source_query) if source_query else song,
                provider=str(provider or getattr(audio, "source", None) or "") or None,
                track_id=str(track_id) if track_id else None,
                requester=str(requester) if requester else None,
                feishu_chat_id=str(feishu_chat_id) if feishu_chat_id else None,
                hermes_session_id=str(session_id) if session_id else None,
                metadata=metadata,
            )
        except JobQueueError as exc:
            return _fail(None, exc, song=song, voice=voice_label, pitch=pitch)

        job_id = job.job_id
        user_message = QUEUED_ACK
        if session_id:
            clear_session(session_id)
        _kick_cover_pipeline()
        payload = {
            "status": "queued",
            "job_id": job_id,
            "song": song,
            "voice": voice_label,
            "pitch": pitch,
            "output_path": None,
            "error": None,
            "feishu_chat_id": feishu_chat_id,
            "user_message": user_message,
            "pretty": user_message,
        }
        _log(json.dumps(payload, ensure_ascii=False))
        print(user_message, file=sys.stderr, flush=True)
        _emit(payload)
        return 0
    except Exception as exc:
        duration = f"{int(round(time.time() - t0))}s"
        return _fail(None, exc, duration=duration)


def main() -> int:
    parser = argparse.ArgumentParser(description="AIVOICE cover skill runner")
    parser.add_argument("--list-voices", action="store_true", help="List Registry voices")
    parser.add_argument("--search", default=None, help="Search GD音乐台 by song name")
    parser.add_argument("--search-count", type=int, default=8)
    parser.add_argument("--pick", default=None, help="Pick candidate index/track_id from session")
    parser.add_argument("--parse", default=None, help="Parse one NL utterance to JSON params")
    parser.add_argument("--session-id", default=None, help="Feishu/Hermes session key for state")
    parser.add_argument(
        "--feishu-chat-id",
        default=None,
        help="Feishu chat_id (oc_…) for outbox mp3 delivery; never use ou_ user id",
    )
    parser.add_argument("--voice-id", default=None, help="Preferred voice_id for search/pick")
    parser.add_argument("--pitch", default=None, help="Pitch for search session / pick override")
    parser.add_argument("--dry-run", action="store_true", help="With --pick: emit request only")
    parser.add_argument("--json", dest="json", default=None)
    parser.add_argument("--json-file", dest="json_file", default=None)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    if args.list_voices:
        return cmd_list_voices()
    if args.parse is not None:
        return cmd_parse(args)
    if args.search:
        return cmd_search(args)
    if args.pick is not None:
        return cmd_pick(args)
    return cmd_cover(args)


if __name__ == "__main__":
    raise SystemExit(main())
