"""User-facing copy for Hermes Feishu — no tracebacks, no model-tech jargon."""

from __future__ import annotations

from typing import Any

# Kept for future outbox / Worker-facing notify copy.
# Skill enqueue path does not print UVR/SVC stage lines to the user.
STAGE_UX = {
    "pending": ("queued", "已收到，翻唱已进入制作队列。"),
    "queued": ("queued", "已收到，翻唱已进入制作队列。"),
    "uvr": ("running", "制作中"),
    "svc": ("running", "制作中"),
    "mixing": ("running", "制作中"),
    "exporting": ("running", "制作中"),
    "done": ("done", "完成！"),
    "failed": ("failed", "制作失败"),
}

QUEUED_ACK = "已收到，翻唱已进入制作队列。完成后会通知你。"


def format_voices_help(voices: list[dict[str, Any]]) -> str:
    lines = ["当前可用音色：", ""]
    for row in voices:
        vid = str(row.get("voice_id") or "")
        name = str(row.get("display_name") or vid)
        desc = str(row.get("description") or "").strip()
        lines.append(f"🎤 {vid}")
        lines.append(f"   {name}" + (f" — {desc}" if desc else ""))
        lines.append("")
    lines.append("回复示例：用 example_voice_b 翻唱晴天")
    return "\n".join(lines).rstrip() + "\n"


def format_cover_ack(
    *,
    song: str,
    voice: str,
    track_label: str | None = None,
    eta: str | None = None,
) -> str:
    """Selection + enqueue ACK (Skill path). ``eta`` kept for signature compat; unused."""
    _ = eta
    title = track_label or song
    return (
        f"已选择：\n\n"
        f"🎵 {title}\n"
        f"🎤 音色：{voice}\n\n"
        f"{QUEUED_ACK}\n"
    )


def format_cover_queued(*, song: str | None = None, voice: str | None = None) -> str:
    """Plain queued ACK for notify / future Skill emit alignment."""
    _ = song, voice
    return QUEUED_ACK


def format_cover_done(*, song: str, voice: str, output_path: str, duration: str) -> str:
    """Completion copy for outbox / notify (not used by Skill enqueue path)."""
    return (
        f"完成！\n\n"
        f"🎵 {song}\n"
        f"🎤 {voice}\n"
        f"⏱ {duration}\n\n"
        f"文件：\n{output_path}\n"
    )


def friendly_error(exc: BaseException | str) -> str:
    text = str(exc)
    low = text.lower()

    if "no search results" in low or "搜不到" in text or "empty search" in low:
        return (
            "歌曲搜索暂时没有结果。\n\n"
            "可以尝试：\n"
            "1. 改歌名写法（去掉「的」「-」）\n"
            "2. 加上歌手名，或只搜歌名\n"
            "3. 提供本地 mp3 路径或公开直链\n"
        )
    if "timeout" in low or "超时" in text:
        return (
            "歌曲搜索超时了。\n\n"
            "稍后再试，或换一种歌名写法；也可以发本地文件 / 直链。\n"
        )
    if "http" in low or "api failed" in low or "urlerror" in low:
        return (
            "歌曲搜索暂时失败（网络或曲库服务异常）。\n\n"
            "可以尝试：\n"
            "1. 稍后再搜\n"
            "2. 修改歌曲名 / 添加歌手名\n"
            "3. 上传本地文件或公开直链\n"
        )
    if "unknown voice" in low or "未知音色" in text:
        return "未识别该音色。请先问「有哪些声音」，或使用 example_voice / example_voice_b。"
    if "file not found" in low or "not found" in low and (".mp3" in low or "path" in low):
        return "找不到音频文件。请检查路径，或改用歌名搜索 / 直链。"
    if "no playable url" in low or "copyright" in low:
        return "这首歌暂时没有可下载音源（可能受版权限制）。请换一个版本或用本地文件。"
    if "invalid request" in low or "json" in low:
        return "请求格式有误。请重新说：用 example_voice_b 翻唱<歌名>。"
    if "序号" in text or "无法识别该选择" in text or "没有待选" in text:
        return text if text.endswith("\n") else text + "\n"

    # Strip traceback-ish noise
    if "traceback" in low or "file \"" in low:
        return "制作过程出错了。请换一首歌重试，或稍后再试。"

    # Keep short technical detail only as last resort
    short = text.strip().splitlines()[0][:160]
    return f"出错了：{short}\n\n可以换歌名重试，或提供本地文件 / 直链。\n"
