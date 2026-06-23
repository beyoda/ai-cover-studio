"""Fetch cover art from APIs or generate a default."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

GRADIENT_COLORS = [
    ("#1DB954", "#121212"),
    ("#E91E63", "#1A1A2E"),
    ("#4A90D9", "#16213E"),
    ("#F59B23", "#1A1A1A"),
    ("#9B59B6", "#1A1A1A"),
    ("#2ECC71", "#0A0A0A"),
    ("#E74C3C", "#1A1A1A"),
    ("#3498DB", "#121212"),
]


def fetch_cover(song: str, artist: str = "", output_dir: Path | None = None) -> Optional[Path]:
    """Try to fetch cover art. Returns path to cover image or None."""
    # 1. try iTunes
    path = _itunes_search(song, artist, output_dir)
    if path:
        return path

    # 2. fallback: generate default
    if output_dir:
        return _generate_default(song, output_dir)
    return None


def _itunes_search(song: str, artist: str = "", output_dir: Path | None = None) -> Optional[Path]:
    try:
        import tempfile
        import requests
        query = f"{song} {artist}".strip()
        url = f"https://itunes.apple.com/search?term={query}&limit=1&entity=song"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        results = data.get("results", [])
        if results:
            artwork_url = results[0].get("artworkUrl100", "")
            if artwork_url:
                # get higher res version
                artwork_url = artwork_url.replace("100x100", "600x600")
                img_resp = requests.get(artwork_url, timeout=15)
                if img_resp.status_code == 200:
                    dest = output_dir or Path(tempfile.gettempdir())
                    dest_path = Path(dest) / "cover.jpg"
                    dest_path.write_bytes(img_resp.content)
                    return dest_path
    except Exception:
        pass
    return None


def _generate_default(title: str, output_dir: Path) -> Path:
    """Generate an 800x800 gradient cover with album title."""
    import random
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        # fallback: create a simple solid-color image
        dest = Path(output_dir) / "cover.jpg"
        dest.write_bytes(_minimal_jpg())
        return dest

    c1, c2 = random.choice(GRADIENT_COLORS)
    img = Image.new("RGB", (800, 800), c1)
    draw = ImageDraw.Draw(img)

    # vertical gradient
    for y in range(800):
        ratio = y / 800
        r = int(int(c1[1:3], 16) * (1 - ratio) + int(c2[1:3], 16) * ratio)
        g = int(int(c1[3:5], 16) * (1 - ratio) + int(c2[3:5], 16) * ratio)
        b = int(int(c1[5:7], 16) * (1 - ratio) + int(c2[5:7], 16) * ratio)
        draw.line([(0, y), (800, y)], fill=(r, g, b))

    # text
    try:
        title_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 48)
        small_font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 16)
    except OSError:
        title_font = ImageFont.load_default()
        small_font = title_font

    def draw_centered(text: str, y: int, font, fill: str = "#FFFFFF") -> None:
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        x = (800 - tw) // 2
        draw.text((x, y), text, fill=fill, font=font)

    # wrap long titles
    if len(title) > 12:
        lines = [title[:12], title[12:24]] if len(title) > 12 else [title]
        y_start = 280
        for i, line in enumerate(lines):
            draw_centered(line, y_start + i * 60, title_font)
    else:
        draw_centered(title, 340, title_font)

    draw_centered("AI Cover Studio", 550, small_font, "#888888")

    dest = Path(output_dir) / "cover.jpg"
    img.save(dest, "JPEG", quality=90)
    return dest


def _minimal_jpg() -> bytes:
    """Minimal valid JPEG bytes (1x1 green pixel)."""
    import base64
    # base64 encoded 1x1 green JPEG
    return base64.b64decode(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
        "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAAB"
        "AAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AK//Z"
    )
