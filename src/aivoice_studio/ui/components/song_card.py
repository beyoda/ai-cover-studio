"""Compact track info card."""

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from aivoice_studio.ui.theme import ACCENT, BG_CARD, BORDER, RADIUS, TEXT_MUTED

try:
    import ffmpeg  # type: ignore[import-untyped]
    HAS_FFPROBE = True
except ImportError:
    HAS_FFPROBE = False


class SongCard(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(
            f"SongCard {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
        )
        self.setFixedHeight(72)

        self.cover = QLabel("♫")
        self.cover.setFixedSize(48, 48)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover.setStyleSheet(
            f"background: #252525; border-radius: 6px; font-size: 22px; color: {ACCENT};"
        )

        self.title = QLabel("No file selected")
        self.title.setStyleSheet("font-size: 14px; font-weight: 600; color: #FFF; background: transparent;")
        self.title.setWordWrap(False)

        self.detail = QLabel("")
        self.detail.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; background: transparent;")

        info = QVBoxLayout()
        info.setSpacing(2)
        info.addWidget(self.title)
        info.addWidget(self.detail)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(self.cover)
        layout.addLayout(info, stretch=1)

    def set_file(self, file_path: str | Path) -> None:
        p = Path(file_path)
        self.title.setText(p.name)
        parts = [f"{p.stat().st_size / (1024 * 1024):.1f} MB"]

        if HAS_FFPROBE:
            try:
                probe = ffmpeg.probe(str(p))
                audio = next((s for s in probe.get("streams", []) if s["codec_type"] == "audio"), None)
                if audio:
                    dur = float(audio.get("duration", 0))
                    m, s = divmod(int(dur), 60)
                    sr = int(audio.get("sample_rate", 0))
                    ch = "Stereo" if audio.get("channels") == 2 else "Mono"
                    parts = [f"{m}:{s:02d}", f"{sr // 1000}kHz", ch, parts[0]]
            except Exception:
                pass

        self.detail.setText(" · ".join(parts))
        self.setVisible(True)

    def clear(self) -> None:
        self.title.setText("No file selected")
        self.detail.setText("")
        self.setVisible(False)
