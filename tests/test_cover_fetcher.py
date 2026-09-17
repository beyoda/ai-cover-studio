"""Default cover-art generation must not depend on one hard-coded system font.

The original code pointed straight at ``C:/Windows/Fonts/msyh.ttc``. It had an
``except OSError`` fallback so it never crashed, but on any non-Windows host the
artwork silently degraded to PIL's bitmap default. These tests pin the selection
contract: the first candidate that can be opened wins, missing candidates are
skipped rather than fatal, and a machine with none of them still gets a usable
font object.

The selection tests stub ``PIL.ImageFont`` so they run even where Pillow is not
installed (Pillow is an optional ``images`` extra).
"""

from __future__ import annotations

import sys
import types

from aivoice_studio.ui import cover_fetcher


class _FakeFont:
    def __init__(self, path: str, size: int) -> None:
        self.path = path
        self.size = size


def _stub_pillow(monkeypatch, attempts: list[str], missing: set[str]) -> None:
    """Install a fake ``PIL``/``PIL.ImageFont`` that records every open attempt."""
    def truetype(path, size):
        attempts.append(path)
        if path in missing:
            raise OSError(f"cannot open resource: {path}")
        return _FakeFont(path, size)

    fake_font = types.ModuleType("PIL.ImageFont")
    fake_font.truetype = truetype
    fake_font.load_default = lambda: _FakeFont("<default>", 0)

    fake_pil = types.ModuleType("PIL")
    fake_pil.ImageFont = fake_font

    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.ImageFont", fake_font)


def test_falls_back_to_default_when_every_candidate_is_missing(monkeypatch):
    attempts: list[str] = []
    candidates = ("/definitely/not/here.ttc", "/also/missing.otf")
    _stub_pillow(monkeypatch, attempts, missing=set(candidates))
    monkeypatch.setattr(cover_fetcher, "CJK_FONT_CANDIDATES", candidates)

    font = cover_fetcher._load_font(48)

    assert font.path == "<default>"
    assert attempts == list(candidates)


def test_skips_a_missing_candidate_and_uses_the_next_one(monkeypatch):
    attempts: list[str] = []
    _stub_pillow(monkeypatch, attempts, missing={"/definitely/not/here.ttc"})
    monkeypatch.setattr(
        cover_fetcher,
        "CJK_FONT_CANDIDATES",
        ("/definitely/not/here.ttc", "/a/real/one.ttf"),
    )

    font = cover_fetcher._load_font(24)

    assert font.path == "/a/real/one.ttf"
    assert font.size == 24
    assert attempts == ["/definitely/not/here.ttc", "/a/real/one.ttf"]


def test_windows_still_gets_yahai_first():
    """The original Windows rendering must not change."""
    assert cover_fetcher.CJK_FONT_CANDIDATES[0] == "C:/Windows/Fonts/msyh.ttc"


def test_candidates_cover_all_three_platforms():
    joined = " ".join(cover_fetcher.CJK_FONT_CANDIDATES)
    assert "Windows" in joined
    assert "/System/Library" in joined
    assert "/usr/share/fonts" in joined


def test_generate_default_writes_a_jpeg(tmp_path):
    """Works with Pillow present and with Pillow absent (minimal-JPEG path)."""
    out = cover_fetcher._generate_default("示例歌手 - 示例曲目", tmp_path)
    assert out.exists()
    assert out.suffix == ".jpg"
    assert out.stat().st_size > 0
