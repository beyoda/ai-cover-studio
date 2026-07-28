"""Skill-layer NL helpers — voice ids come from Voice Registry when available."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma", ".mp4"}


def format_song_choices(
    candidates: list[dict[str, Any]] | list[Any],
    *,
    query: str = "",
    voice_hint: str = "",
) -> str:
    """Pretty chat text for GD音乐台 search picks."""
    header = "找到这些可翻唱版本"
    if query:
        header = f"搜「{query}」找到这些版本"
    lines = [header + "（来源：GD音乐台）", ""]
    for i, raw in enumerate(candidates, 1):
        if isinstance(raw, dict):
            name = str(raw.get("name") or "").strip() or "未知曲目"
            artist = str(raw.get("artist") or "").strip() or "未知艺人"
            album = str(raw.get("album") or "").strip()
            tid = str(raw.get("track_id") or "").strip()
        else:
            name = getattr(raw, "name", "") or "未知曲目"
            artist = getattr(raw, "artist", "") or "未知艺人"
            album = getattr(raw, "album", "") or ""
            tid = getattr(raw, "track_id", "") or ""
        primary = f"{i}️⃣  {name}  ·  {artist}"
        lines.append(primary)
        meta = []
        if album:
            meta.append(f"专辑 {album}")
        if tid:
            meta.append(f"id {tid}")
        if meta:
            lines.append("    " + " ｜ ".join(meta))
        lines.append("")
    footer = "回复序号（例如 1），或直接回 track_id。"
    if voice_hint:
        footer += f" 选完后用「{voice_hint}」音色翻唱。"
    lines.append(footer)
    return "\n".join(lines).rstrip() + "\n"


def normalize_voice_id(text: str | None) -> str | None:
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    # Strip 「版本/版」 chatter: ExampleVoiceB版本 → ExampleVoiceB
    raw = re.sub(r"(版本|版)$", "", raw).strip()
    try:
        from aivoice_studio.cover.voice_registry import get_voice_registry

        return get_voice_registry().resolve(raw).voice_id
    except Exception:
        return None


def parse_choice_token(text: str) -> str | None:
    """If utterance is only a pick (1 / track_id), return it."""
    t = (text or "").strip()
    if not t:
        return None
    if re.fullmatch(r"[1-9]\d?", t):
        return t
    if re.fullmatch(r"\d{6,}", t):
        return t
    m = re.fullmatch(r"(?:选|第)?\s*([1-9]\d?)\s*(?:号|首)?", t)
    if m:
        return m.group(1)
    return None


def parse_pitch_from_text(text: str) -> int | None:
    t = text.strip().lower()
    t_cn = text.strip()

    m = re.search(r"pitch\s*\+?\s*(-?\d+)", t)
    if m:
        return int(m.group(1))

    m = re.search(r"([+-]?\d+)\s*个?(?:key|调|半音)", t_cn, re.I)
    if m and ("升" in t_cn or "降" in t_cn or t_cn.lower().startswith("+") or "-" in m.group(1)):
        val = int(m.group(1))
        if "降" in t_cn and val > 0:
            return -val
        if "升" in t_cn and val < 0:
            return abs(val)
        if "升" in t_cn:
            return abs(val)
        return val

    m = re.search(r"升\s*([一二两三四五六七八九十\d]+)\s*(?:个)?\s*(?:key|调)?", t_cn)
    if m:
        return _cn_num(m.group(1))
    m = re.search(r"降\s*([一二两三四五六七八九十\d]+)\s*(?:个)?\s*(?:key|调)?", t_cn)
    if m:
        return -_cn_num(m.group(1))

    return None


def _cn_num(token: str) -> int:
    table = {
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if token.isdigit() or (token.startswith("-") and token[1:].isdigit()):
        return int(token)
    return table.get(token, 0)


def normalize_reverb(value: Any) -> str:
    if isinstance(value, bool):
        return "录音棚" if value else "关闭"
    if value is None:
        return "关闭"
    s = str(value).strip().lower()
    if s in ("false", "0", "off", "no", "关闭", "关", "不要混响", "关闭reverb", "关闭混响"):
        return "关闭"
    if s in ("true", "1", "on", "yes", "打开混响", "要混响", "开"):
        return "录音棚"
    if str(value) in ("关闭", "录音棚", "现场", "大教堂"):
        return str(value)
    return str(value)


def parse_reverb_from_text(text: str) -> str | None:
    t = text.strip()
    tl = t.lower()
    if any(x in t for x in ("不要混响", "关闭混响")) or "关闭reverb" in tl:
        return "关闭"
    if any(x in t for x in ("打开混响", "要混响", "开启混响")):
        return "录音棚"
    return None


def _clean_source_title(raw: str) -> str:
    s = (raw or "").strip()
    s = s.strip("《》「」『』\"'“”‘’")
    s = re.sub(r"[。！？!?,，.]+$", "", s).strip()
    # Drop trailing pitch chatter if glued
    s = re.sub(r"(?:，|,)?\s*(?:升|降).*(?:key|调).*$", "", s).strip()
    return s


def _looks_like_audio_file(name: str) -> bool:
    return Path(name).suffix.lower() in AUDIO_SUFFIXES


def song_display_name(title_or_path: str) -> str:
    """Derive short song label: ``示例歌手 - 示例曲目`` → ``示例曲目``."""
    stem = Path(title_or_path).stem if _looks_like_audio_file(title_or_path) else title_or_path
    stem = (stem or "").strip()
    if " - " in stem:
        return stem.split(" - ", 1)[-1].strip() or stem
    if "-" in stem and re.search(r"\s-\s", stem):
        return re.split(r"\s-\s", stem, maxsplit=1)[-1].strip() or stem
    return stem


def parse_source_and_voice(text: str) -> dict[str, str]:
    """Parse NL like 「使用示例歌手声音翻唱 示例歌手 - 示例曲目.mp3」 → input/source + voice_id."""
    t = (text or "").strip()
    if not t:
        return {}

    patterns = [
        # ExampleVoiceB版本翻唱…
        re.compile(
            r"(?P<voice>[\w\u4e00-\u9fff]+)\s*版本翻唱\s*(?P<source>.+)$"
        ),
        # 使用/用 示例歌手声音翻唱 …
        re.compile(
            r"(?:用|使用)(?P<voice>.+?)(?:的)?(?:声音|音色)翻唱\s*(?P<source>.+)$"
        ),
        # 翻唱…，用示例歌手声音
        re.compile(
            r"翻唱\s*(?P<source>.+?)(?:，|,|；|;)\s*(?:用|使用)(?P<voice>.+?)(?:的)?(?:声音|音色)?$"
        ),
        # 用/使用 ExampleVoiceB翻唱这首歌 / 用示例歌手翻唱晴天
        re.compile(r"(?:用|使用)(?P<voice>.+?)翻唱\s*(?P<source>.+)$"),
        # 翻唱周杰伦晴天 / 翻唱晴天（无音色 → 仅 source，进入搜索）
        re.compile(r"^翻唱\s*(?P<source>.+)$"),
    ]

    for pat in patterns:
        m = pat.search(t)
        if not m:
            continue
        source = _clean_source_title(m.group("source"))
        voice_raw = m.groupdict().get("voice")
        voice_id = normalize_voice_id(voice_raw.strip()) if voice_raw else None
        out: dict[str, str] = {}
        if source:
            out["source"] = source
            out["source_query"] = source
            out["action"] = "search" if not _looks_like_audio_file(source) else "cover"
            if _looks_like_audio_file(source):
                out["input"] = source
                out["action"] = "cover"
        if voice_id:
            out["voice_id"] = voice_id
        return out
    return {}


def extract_cover_params_from_utterances(utterances: list[str]) -> dict[str, Any]:
    voice_id = None
    pitch = None
    reverb = None
    source = None
    input_path = None
    action = None
    choice = None
    for u in utterances:
        choice = parse_choice_token(u) or choice
        combo = parse_source_and_voice(u)
        if combo.get("voice_id"):
            voice_id = combo["voice_id"]
        if combo.get("source"):
            source = combo["source"]
        if combo.get("input"):
            input_path = combo["input"]
        if combo.get("action"):
            action = combo["action"]
        # Bare voice mention: 「ExampleVoiceB版本」「用example_voice」
        bare = re.sub(
            r"^(?:用|使用)\s*",
            "",
            re.sub(r"(?:版本|版)$", "", u.strip()),
        ).strip()
        v = normalize_voice_id(bare) or normalize_voice_id(u)
        if v and not combo.get("source"):
            voice_id = v
        p = parse_pitch_from_text(u)
        if p is not None:
            pitch = p
        r = parse_reverb_from_text(u)
        if r is not None:
            reverb = r
    out: dict[str, Any] = {}
    if voice_id:
        out["voice_id"] = voice_id
    if input_path:
        out["input"] = input_path
    if source:
        out["source"] = source
        out["source_query"] = source
    if action:
        out["action"] = action
    if choice:
        out["choice"] = choice
        out["action"] = out.get("action") or "pick"
    if pitch is not None:
        out["pitch"] = pitch
    if reverb is not None:
        out["options"] = {"reverb": reverb}
    return out
