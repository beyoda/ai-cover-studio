"""Multi-stage progress indicator for UVR → SVC → Mix → Export."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget

from aivoice_studio.ui.theme import (
    ACCENT,
    BG_CARD,
    BORDER,
    CARD_SUBTITLE_STYLE,
    RADIUS,
    SECTION_STYLE,
    TEXT_SECONDARY,
)


class StageBar(QWidget):
    """Single pipeline stage with label + progress bar."""

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = QLabel(label)
        self._label.setStyleSheet(CARD_SUBTITLE_STYLE)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)

        self._pct = QLabel("—")
        self._pct.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY};")
        self._pct.setFixedWidth(40)
        self._pct.setAlignment(Qt.AlignmentFlag.AlignRight)

        from PyQt6.QtWidgets import QHBoxLayout

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self._label, stretch=1)
        top.addWidget(self._pct)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(4)
        layout.addLayout(top)
        layout.addWidget(self._bar)

        self.setVisible(False)

    def set_progress(self, pct: int) -> None:
        self._bar.setValue(pct)
        self._pct.setText(f"{pct}%")
        self.setVisible(True)

    def set_done(self) -> None:
        self._bar.setValue(100)
        self._pct.setText("✓")
        self._pct.setStyleSheet(f"font-size: 12px; color: {ACCENT};")

    def set_failed(self) -> None:
        self._pct.setText("✗")
        self._pct.setStyleSheet("font-size: 12px; color: #E22134;")


class ProgressPanel(QWidget):
    """Multi-stage progress panel: UVR | SVC | Mix | Export."""

    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(
            f"ProgressPanel {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: {RADIUS}px; }}"
        )

        self.title = QLabel("Processing")
        self.title.setStyleSheet(SECTION_STYLE)

        self.uvr = StageBar("Separating Vocals (UVR)")
        self.svc = StageBar("Voice Conversion (SVC)")
        self.mix = StageBar("Mixing Audio")
        self.export_bar = StageBar("Exporting MP3")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(4)
        layout.addWidget(self.title)
        layout.addSpacing(8)
        layout.addWidget(self.uvr)
        layout.addWidget(self.svc)
        layout.addWidget(self.mix)
        layout.addWidget(self.export_bar)
        layout.addStretch()

        self.setMinimumHeight(240)

    def reset(self) -> None:
        for stage in [self.uvr, self.svc, self.mix, self.export_bar]:
            stage.setVisible(False)

    def update_from_state(self, state: str, percent: int) -> None:
        """Map pipeline state to stage bars."""
        if "UVR" in state or state in ("separating", "uvr"):
            self.uvr.set_progress(percent)
        elif "SVC" in state or state in ("converting", "svc"):
            self.uvr.set_done()
            self.svc.set_progress(percent)
        elif "MIX" in state or state in ("mixing", "mix"):
            self.uvr.set_done()
            self.svc.set_done()
            self.mix.set_progress(percent)
        elif "EXPORT" in state or state in ("exporting", "export"):
            self.uvr.set_done()
            self.svc.set_done()
            self.mix.set_done()
            self.export_bar.set_progress(percent)
        elif "DONE" in state or state == "done":
            for s in [self.uvr, self.svc, self.mix, self.export_bar]:
                s.set_done()
