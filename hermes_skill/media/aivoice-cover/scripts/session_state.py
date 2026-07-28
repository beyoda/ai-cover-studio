"""Lightweight Hermes session state for search → pick → cover."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

# hermes_skill/runtime/sessions/{session_id}.json
RUNTIME_ROOT = Path(__file__).resolve().parents[3] / "runtime" / "sessions"


def sessions_dir() -> Path:
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    return RUNTIME_ROOT


def _safe_session_id(session_id: str) -> str:
    sid = re.sub(r"[^a-zA-Z0-9._-]+", "_", (session_id or "").strip())[:80]
    return sid or "default"


def session_path(session_id: str) -> Path:
    return sessions_dir() / f"{_safe_session_id(session_id)}.json"


def load_session(session_id: str) -> dict[str, Any] | None:
    path = session_path(session_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_session(session_id: str, data: dict[str, Any]) -> Path:
    path = session_path(session_id)
    payload = dict(data)
    payload["session_id"] = _safe_session_id(session_id)
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def clear_session(session_id: str) -> None:
    path = session_path(session_id)
    if path.is_file():
        path.unlink()


def save_waiting_track_choice(
    session_id: str,
    *,
    query: str,
    voice_id: str | None,
    pitch: int = 0,
    candidates: list[dict[str, Any]],
    feishu_chat_id: str | None = None,
) -> dict[str, Any]:
    rows = []
    for i, c in enumerate(candidates, 1):
        rows.append(
            {
                "index": i,
                "track_id": str(c.get("track_id") or ""),
                "name": str(c.get("name") or ""),
                "artist": str(c.get("artist") or ""),
                "album": str(c.get("album") or ""),
                "label": str(c.get("label") or ""),
            }
        )
    data: dict[str, Any] = {
        "stage": "waiting_track_choice",
        "query": query,
        "voice_id": voice_id,
        "pitch": pitch,
        "provider": "gdstudio",
        "candidates": rows,
    }
    if feishu_chat_id:
        data["feishu_chat_id"] = str(feishu_chat_id).strip()
    save_session(session_id, data)
    return data


def resolve_pick(session: dict[str, Any], pick: str | int) -> dict[str, Any]:
    """Map user reply (1 / track_id) to a candidate; raises ValueError if invalid."""
    raw = str(pick).strip()
    candidates = session.get("candidates") or []
    if not candidates:
        raise ValueError("当前没有待选歌曲，请先搜索歌名。")

    if raw.isdigit() and len(raw) <= 2:
        idx = int(raw)
        for c in candidates:
            if int(c.get("index") or 0) == idx:
                return c
        raise ValueError(f"序号 {idx} 无效，请回复 1–{len(candidates)}。")

    for c in candidates:
        if str(c.get("track_id") or "") == raw:
            return c
    raise ValueError("无法识别该选择，请回复列表中的序号或 track_id。")


def build_cover_request_from_pick(
    session: dict[str, Any],
    chosen: dict[str, Any],
    *,
    voice_id: str | None = None,
    pitch: int | None = None,
) -> dict[str, Any]:
    vid = voice_id or session.get("voice_id") or "example_voice"
    p = pitch if pitch is not None else int(session.get("pitch") or 0)
    label = chosen.get("label") or f"{chosen.get('name')} - {chosen.get('artist')}"
    return {
        "source": session.get("query") or label,
        "source_query": session.get("query") or "",
        "track_id": str(chosen.get("track_id") or ""),
        "voice_id": vid,
        "provider": "gdstudio",
        "pitch": p,
        "options": {"reverb": "关闭", "export_mp3": True},
        "chosen_label": label,
        "chosen_name": chosen.get("name"),
        "chosen_artist": chosen.get("artist"),
    }
