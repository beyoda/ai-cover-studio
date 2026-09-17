"""Bridge from the Hermes skill scripts to the AIVOICE Voice Registry.

The registry is the single source of truth for voice ids. Nothing in this
package hardcodes a voice: the shipped ``config/voices.json`` is an empty
template, and every helper below degrades to ``None``/``[]`` when no voice is
registered, so callers can report the real state to the user.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# hermes_skill/media/aivoice-cover/scripts -> repository root
AIVOICE_ROOT = Path(__file__).resolve().parents[4]
SRC = AIVOICE_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def registry() -> Any | None:
    """The process-wide VoiceRegistry, or ``None`` when it cannot be loaded."""
    try:
        from aivoice_studio.cover.voice_registry import get_voice_registry

        return get_voice_registry()
    except Exception:
        return None


def default_voice_id() -> str | None:
    """Configured ``default_voice_id``, else the first enabled voice, else ``None``."""
    reg = registry()
    if reg is None:
        return None
    if getattr(reg, "default_voice_id", None):
        return str(reg.default_voice_id)
    voices = reg.list_voices()
    return voices[0].voice_id if voices else None


def available_voice_ids() -> list[str]:
    """Enabled voice ids, sorted by the registry."""
    reg = registry()
    if reg is None:
        return []
    return [asset.voice_id for asset in reg.list_voices()]


def resolve_voice_id(ref: str | None) -> str | None:
    """Resolve a voice_id, display name, alias, or checkpoint stem."""
    raw = (ref or "").strip()
    if not raw:
        return None
    reg = registry()
    if reg is None:
        return None
    try:
        return reg.resolve(raw).voice_id
    except Exception:
        return None
